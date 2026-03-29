"""
Blueprint Médiathèque — partage et téléchargement de films.

Routes :
  GET  /films/              — liste des films (filtres genre/année/recherche)
  GET  /films/<id>          — fiche détaillée + bouton téléchargement
  GET  /films/ajouter       — formulaire d'ajout avec recherche TMDB
  POST /films/ajouter       — enregistrement du film
  GET  /films/api/search    — recherche TMDB (AJAX JSON)
  GET  /films/api/details/<tmdb_id> — détails TMDB (AJAX JSON)
  GET  /films/<id>/telecharger      — envoi du fichier
  POST /films/<id>/supprimer        — suppression (admin uniquement)
"""

import io
import os
import re
import zipfile

import requests as _http
from flask import (Blueprint, Response, abort, current_app, flash, jsonify,
                   redirect, render_template, request, send_file, stream_with_context, url_for)
from flask_login import current_user, login_required

from . import db, limiter
from .models import Movie

movies_bp = Blueprint('movies', __name__, url_prefix='/films')

_TMDB_BASE = 'https://api.themoviedb.org/3'
_TMDB_IMG  = 'https://image.tmdb.org/t/p/w500'
_ALLOWED_EXT = {'.mkv', '.mp4', '.avi', '.mov', '.wmv', '.m4v', '.webm', '.flv'}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _api_key():
    return current_app.config.get('TMDB_API_KEY', '').strip('"').strip("'")


def _language():
    return current_app.config.get('TMDB_LANGUAGE', 'fr-FR')


def _movies_folder():
    folder = current_app.config.get('MOVIES_FOLDER', '')
    os.makedirs(folder, exist_ok=True)
    return folder


def _safe_int(val):
    try:
        return int(val) if val else None
    except (ValueError, TypeError):
        return None


def _safe_float(val):
    try:
        return float(val) if val else None
    except (ValueError, TypeError):
        return None


def _tmdb_get(path, **params):
    """Appel TMDB — Bearer token (v4) ou api_key (v3) selon la valeur configurée."""
    key = _api_key().strip('"').strip("'")
    if not key:
        return None
    # JWT Bearer (TMDB v4 Read Access Token) si commence par "eyJ"
    if key.startswith('eyJ'):
        headers = {'Authorization': f'Bearer {key}', 'Accept': 'application/json'}
        req_params = {'language': _language(), **params}
    else:
        headers = {}
        req_params = {'api_key': key, 'language': _language(), **params}
    try:
        r = _http.get(
            f"{_TMDB_BASE}{path}",
            params=req_params,
            headers=headers,
            timeout=5,
        )
        return r.json() if r.status_code == 200 else None
    except Exception as exc:
        current_app.logger.warning("TMDB error: %s", exc)
        return None


def _poster(path):
    return f"{_TMDB_IMG}{path}" if path else None


def _human_size(n):
    for unit in ('o', 'Ko', 'Mo', 'Go', 'To'):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == 'o' else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} Po"


def _list_episodes(folder_path):
    """Liste les fichiers vidéo d'une série triés naturellement."""
    def _nat_key(s):
        return [int(p) if p.isdigit() else p.lower() for p in re.split(r'(\d+)', s)]

    episodes = []
    for root, _dirs, files in os.walk(folder_path):
        for f in files:
            if os.path.splitext(f)[1].lower() in _ALLOWED_EXT:
                rel = os.path.relpath(os.path.join(root, f), folder_path)
                size = os.path.getsize(os.path.join(root, f))
                # Nom d'affichage lisible : sans extension, points/underscores → espaces
                base = os.path.splitext(os.path.basename(f))[0]
                display = re.sub(r'[._]+', ' ', base).strip()
                episodes.append({'filename': rel, 'size': size, 'size_human': _human_size(size), 'display_name': display})
    episodes.sort(key=lambda e: _nat_key(e['filename']))
    return episodes


# ── Routes ───────────────────────────────────────────────────────────────────

_SORT_COLS = {
    'title':      Movie.title,
    'year':       Movie.year,
    'rating':     Movie.rating,
    'size':       Movie.file_size,
    'added':      Movie.created_at,
    'downloads':  Movie.download_count,
}
_PER_PAGE_OPTS = (5, 10, 20)


@movies_bp.route('/')
@login_required
def index():
    q            = request.args.get('q', '').strip()
    genre        = request.args.get('genre', '')
    year         = request.args.get('year', '')
    actor        = request.args.get('actor', '').strip()
    content_type = request.args.get('type', '')
    sort         = request.args.get('sort', 'added')
    order        = request.args.get('order', 'desc')
    page         = max(1, _safe_int(request.args.get('page', 1)) or 1)
    per_page     = _safe_int(request.args.get('per_page', 10)) or 10
    if per_page not in _PER_PAGE_OPTS:
        per_page = 10

    sort_col = _SORT_COLS.get(sort, Movie.created_at)
    sort_expr = sort_col.desc() if order == 'desc' else sort_col.asc()

    qry = Movie.query
    if q:
        qry = qry.filter(Movie.title.ilike(f'%{q}%'))
    if genre:
        qry = qry.filter(Movie.genres.ilike(f'%{genre}%'))
    if actor:
        qry = qry.filter(Movie.cast.ilike(f'%{actor}%'))
    if year:
        yr = _safe_int(year)
        if yr:
            qry = qry.filter(Movie.year == yr)
    if content_type in ('film', 'série'):
        qry = qry.filter(
            (Movie.content_type == content_type) |
            (Movie.content_type == None if content_type == 'film' else False)
        )

    total = qry.count()
    movies = qry.order_by(sort_expr).offset((page - 1) * per_page).limit(per_page).all()
    total_pages = max(1, (total + per_page - 1) // per_page)

    all_movies = Movie.query.with_entities(Movie.genres, Movie.year, Movie.cast).all()
    all_genres = sorted({
        g.strip()
        for row in all_movies if row.genres
        for g in row.genres.split(',') if g.strip()
    })
    all_years = sorted({row.year for row in all_movies if row.year}, reverse=True)
    all_actors = sorted({
        a.strip()
        for row in all_movies if row.cast
        for a in row.cast.split(',') if a.strip()
    })

    return render_template(
        'movies/index.html',
        movies=movies,
        all_genres=all_genres,
        all_years=all_years,
        all_actors=all_actors,
        genre_filter=genre,
        year_filter=year,
        actor_filter=actor,
        type_filter=content_type,
        search=q,
        sort=sort,
        order=order,
        page=page,
        per_page=per_page,
        per_page_opts=_PER_PAGE_OPTS,
        total=total,
        total_pages=total_pages,
        tmdb_configured=bool(_api_key()),
    )


def _apply_tmdb_data(movie, data):
    """Applique les données TMDB sur un objet Movie. Retourne True si modifié."""
    director = next(
        (c['name'] for c in data.get('credits', {}).get('crew', []) if c.get('job') == 'Director'),
        None,
    )
    genres = ', '.join(g['name'] for g in data.get('genres', [])) or None
    cast_list = [c['name'] for c in data.get('credits', {}).get('cast', [])[:3] if c.get('name')]
    cast = ', '.join(cast_list) or None
    changed = False
    for attr, val in [
        ('title',          data.get('title') or movie.title),
        ('original_title', data.get('original_title') or movie.original_title),
        ('year',           _safe_int((data.get('release_date') or '')[:4]) or movie.year),
        ('genres',         genres or movie.genres),
        ('director',       director or movie.director),
        ('cast',           cast or movie.cast),
        ('overview',       data.get('overview') or movie.overview),
        ('poster_url',     _poster(data.get('poster_path')) or movie.poster_url),
        ('language',       data.get('original_language') or movie.language),
        ('rating',         round(data.get('vote_average', 0) or 0, 1) or movie.rating),
        ('tmdb_id',        data.get('id') or movie.tmdb_id),
    ]:
        if val and getattr(movie, attr) != val:
            setattr(movie, attr, val)
            changed = True
    return changed


@movies_bp.route('/<int:movie_id>')
@login_required
def detail(movie_id):
    movie = Movie.query.get_or_404(movie_id)
    # Auto-sync TMDB si données incomplètes et tmdb_id connu
    if movie.tmdb_id and _api_key() and (not movie.poster_url or not movie.director or not movie.genres):
        tmdb_path = f'/tv/{movie.tmdb_id}' if movie.content_type == 'série' else f'/movie/{movie.tmdb_id}'
        data = _tmdb_get(tmdb_path, append_to_response='credits')
        if data and _apply_tmdb_data(movie, data):
            db.session.commit()
            current_app.logger.info("Fiche mise à jour depuis TMDB (auto) : %s", movie.title)
    episodes = []
    if movie.content_type == 'série' and movie.file_filename:
        serie_path = os.path.join(_movies_folder(), movie.file_filename)
        if os.path.isdir(serie_path):
            episodes = _list_episodes(serie_path)
    return render_template('movies/detail.html', movie=movie, tmdb_configured=bool(_api_key()), episodes=episodes)


@movies_bp.route('/<int:movie_id>/refresh-tmdb', methods=['POST'])
@login_required
def refresh_tmdb(movie_id):
    movie = Movie.query.get_or_404(movie_id)
    if not _api_key():
        flash('TMDB non configuré.', 'warning')
        return redirect(url_for('movies.detail', movie_id=movie_id))

    tmdb_id = movie.tmdb_id
    if not tmdb_id:
        # Chercher par titre si pas de tmdb_id
        data_search = _tmdb_get('/search/movie', query=movie.title, include_adult=False)
        results = (data_search or {}).get('results', [])
        if results:
            tmdb_id = results[0].get('id')

    if not tmdb_id:
        flash('Film introuvable sur TMDB.', 'warning')
        return redirect(url_for('movies.detail', movie_id=movie_id))

    data = _tmdb_get(f'/movie/{tmdb_id}', append_to_response='credits')
    if not data:
        flash('Erreur lors de la récupération des données TMDB.', 'error')
        return redirect(url_for('movies.detail', movie_id=movie_id))

    changed = _apply_tmdb_data(movie, data)
    if changed:
        db.session.commit()
        current_app.logger.info("Film mis à jour depuis TMDB : %s par %s", movie.title, current_user.username)
        flash(f'« {movie.title} » mis à jour depuis TMDB.', 'success')
    else:
        flash('Les données sont déjà à jour.', 'info')
    return redirect(url_for('movies.detail', movie_id=movie_id))


@movies_bp.route('/ajouter', methods=['GET', 'POST'])
@login_required
@limiter.limit("30 per hour")
def upload():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Le titre est obligatoire.', 'error')
            return redirect(url_for('movies.upload'))

        # Vérifier unicité tmdb_id si fourni
        tmdb_id = _safe_int(request.form.get('tmdb_id'))
        if tmdb_id and Movie.query.filter_by(tmdb_id=tmdb_id).first():
            flash('Ce film est déjà dans la médiathèque.', 'warning')
            return redirect(url_for('movies.index'))

        ct = request.form.get('content_type', 'film').strip()
        if ct not in ('film', 'série'):
            ct = 'film'
        movie = Movie(
            title=title,
            original_title=request.form.get('original_title', '').strip() or None,
            year=_safe_int(request.form.get('year')),
            genres=request.form.get('genres', '').strip() or None,
            director=request.form.get('director', '').strip() or None,
            cast=request.form.get('cast', '').strip() or None,
            overview=request.form.get('overview', '').strip() or None,
            poster_url=request.form.get('poster_url', '').strip() or None,
            tmdb_id=tmdb_id,
            language=request.form.get('language', '') or None,
            rating=_safe_float(request.form.get('rating')),
            content_type=ct,
            uploaded_by_id=current_user.id,
        )

        file = request.files.get('file')
        if file and file.filename:
            ext = os.path.splitext(file.filename)[1].lower()
            if ext not in _ALLOWED_EXT:
                flash(f'Format non supporté ({ext}).', 'error')
                return redirect(url_for('movies.upload'))

            safe = re.sub(r'[^\w\s.-]', '', title).strip().replace(' ', '.')
            filename = f"{safe}.{movie.year or 'nd'}{ext}"
            folder = _movies_folder()
            filepath = os.path.join(folder, filename)
            # Éviter les collisions de noms
            base, extension = os.path.splitext(filename)
            counter = 1
            while os.path.exists(filepath):
                filename = f"{base}_{counter}{extension}"
                filepath = os.path.join(folder, filename)
                counter += 1
            file.save(filepath)
            movie.file_filename = filename
            movie.file_size = os.path.getsize(filepath)
        elif ct == 'série':
            # Série : dossier existant dans MOVIES_FOLDER
            serie_folder = request.form.get('serie_folder', '').strip()
            if serie_folder and '/' not in serie_folder and '..' not in serie_folder:
                folder = _movies_folder()
                fp = os.path.join(folder, serie_folder)
                if os.path.isdir(fp):
                    movie.file_filename = serie_folder
                    ep_count = _safe_int(request.form.get('episode_count')) or sum(
                        1 for root, _, files in os.walk(fp)
                        for f in files if os.path.splitext(f)[1].lower() in _ALLOWED_EXT
                    )
                    movie.episode_count = ep_count
        else:
            # Fichier préexistant dans le dossier (seed)
            preexisting = request.form.get('existing_file', '').strip()
            if preexisting:
                folder = _movies_folder()
                fp = os.path.join(folder, preexisting)
                if os.path.isfile(fp):
                    movie.file_filename = preexisting
                    movie.file_size = os.path.getsize(fp)

        # Champs séries
        movie.seasons_count = _safe_int(request.form.get('seasons_count'))

        db.session.add(movie)
        db.session.commit()
        current_app.logger.info("Film ajouté : %s par %s", movie.title, current_user.username)
        flash(f'« {movie.title} » ajouté à la médiathèque.', 'success')
        return redirect(url_for('movies.detail', movie_id=movie.id))

    # Lister les fichiers non enregistrés et les dossiers non enregistrés
    folder = _movies_folder()
    registered_files = {m.file_filename for m in Movie.query.with_entities(Movie.file_filename).all() if m.file_filename}
    unregistered_files = sorted([
        f for f in os.listdir(folder)
        if os.path.splitext(f)[1].lower() in _ALLOWED_EXT and f not in registered_files
    ])
    registered_series = {
        m.file_filename
        for m in Movie.query.filter_by(content_type='série').with_entities(Movie.file_filename).all()
        if m.file_filename
    }
    unregistered_folders = sorted([
        {'name': name, 'episode_count': sum(
            1 for root, _, files in os.walk(os.path.join(folder, name))
            for f in files if os.path.splitext(f)[1].lower() in _ALLOWED_EXT
        )}
        for name in os.listdir(folder)
        if os.path.isdir(os.path.join(folder, name)) and name not in registered_series
    ], key=lambda x: x['name'])

    return render_template(
        'movies/upload.html',
        tmdb_configured=bool(_api_key()),
        unregistered_files=unregistered_files,
        unregistered_folders=unregistered_folders,
    )


@movies_bp.route('/api/search')
@login_required
def api_tmdb_search():
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    data = _tmdb_get('/search/movie', query=q, include_adult=False)
    if not data:
        return jsonify([])
    results = [
        {
            'id':             m.get('id'),
            'title':          m.get('title', ''),
            'original_title': m.get('original_title', ''),
            'year':           (m.get('release_date') or '')[:4] or None,
            'overview':       (m.get('overview') or '')[:200],
            'poster':         _poster(m.get('poster_path')),
            'rating':         round(m.get('vote_average', 0) or 0, 1),
            'language':       m.get('original_language', ''),
        }
        for m in data.get('results', [])[:8]
    ]
    return jsonify(results)


@movies_bp.route('/api/details/<int:tmdb_id>')
@login_required
def api_tmdb_details(tmdb_id):
    data = _tmdb_get(f'/movie/{tmdb_id}', append_to_response='credits')
    if not data:
        return jsonify({})

    director = next(
        (c['name'] for c in data.get('credits', {}).get('crew', []) if c.get('job') == 'Director'),
        '',
    )
    genres = ', '.join(g['name'] for g in data.get('genres', []))
    cast = ', '.join(c['name'] for c in data.get('credits', {}).get('cast', [])[:3] if c.get('name'))

    return jsonify({
        'id':             data.get('id'),
        'title':          data.get('title', ''),
        'original_title': data.get('original_title', ''),
        'year':           (data.get('release_date') or '')[:4] or None,
        'genres':         genres,
        'director':       director,
        'cast':           cast,
        'overview':       data.get('overview', ''),
        'poster':         _poster(data.get('poster_path')),
        'rating':         round(data.get('vote_average', 0) or 0, 1),
        'language':       data.get('original_language', ''),
    })


@movies_bp.route('/<int:movie_id>/telecharger')
@login_required
def download(movie_id):
    movie = Movie.query.get_or_404(movie_id)
    if not movie.file_filename:
        abort(404)
    folder = current_app.config.get('MOVIES_FOLDER', '')
    filepath = os.path.join(folder, movie.file_filename)
    if not os.path.isfile(filepath):
        abort(404)
    movie.download_count = (movie.download_count or 0) + 1
    movie.last_downloaded_by_id = current_user.id
    db.session.commit()
    current_app.logger.info("Téléchargement : %s par %s", movie.title, current_user.username)
    return send_file(filepath, as_attachment=True, download_name=movie.file_filename)


@movies_bp.route('/api/search/tv')
@login_required
def api_tmdb_search_tv():
    """Recherche TMDB de séries TV."""
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    data = _tmdb_get('/search/tv', query=q, include_adult=False)
    if not data:
        return jsonify([])
    results = [
        {
            'id':             m.get('id'),
            'title':          m.get('name', ''),
            'original_title': m.get('original_name', ''),
            'year':           (m.get('first_air_date') or '')[:4] or None,
            'overview':       (m.get('overview') or '')[:200],
            'poster':         _poster(m.get('poster_path')),
            'rating':         round(m.get('vote_average', 0) or 0, 1),
            'language':       m.get('original_language', ''),
        }
        for m in data.get('results', [])[:8]
    ]
    return jsonify(results)


@movies_bp.route('/api/details/tv/<int:tmdb_id>')
@login_required
def api_tmdb_details_tv(tmdb_id):
    """Détails TMDB d'une série TV."""
    data = _tmdb_get(f'/tv/{tmdb_id}', append_to_response='credits')
    if not data:
        return jsonify({})

    creator = next(
        (c['name'] for c in data.get('created_by', []) if c.get('name')),
        None,
    ) or next(
        (c['name'] for c in data.get('credits', {}).get('crew', []) if c.get('job') in ('Creator', 'Executive Producer')),
        '',
    )
    genres = ', '.join(g['name'] for g in data.get('genres', []))
    cast = ', '.join(c['name'] for c in data.get('credits', {}).get('cast', [])[:3] if c.get('name'))

    return jsonify({
        'id':             data.get('id'),
        'title':          data.get('name', ''),
        'original_title': data.get('original_name', ''),
        'year':           (data.get('first_air_date') or '')[:4] or None,
        'genres':         genres,
        'director':       creator,
        'cast':           cast,
        'overview':       data.get('overview', ''),
        'poster':         _poster(data.get('poster_path')),
        'rating':         round(data.get('vote_average', 0) or 0, 1),
        'language':       data.get('original_language', ''),
        'seasons_count':  data.get('number_of_seasons'),
        'episode_count':  data.get('number_of_episodes'),
    })


@movies_bp.route('/api/scan-folder')
@login_required
def api_scan_folder():
    """Retourne le nombre d'épisodes dans un sous-dossier de MOVIES_FOLDER."""
    if current_user.role != 'admin':
        return jsonify({'count': 0, 'error': 'forbidden'})
    name = request.args.get('name', '').strip()
    if not name or '/' in name or '..' in name:
        return jsonify({'count': 0})
    folder = current_app.config.get('MOVIES_FOLDER', '')
    fp = os.path.join(folder, name)
    if not os.path.isdir(fp):
        return jsonify({'count': 0, 'error': 'not_found'})
    count = sum(
        1 for f in os.listdir(fp)
        if os.path.splitext(f)[1].lower() in _ALLOWED_EXT
    )
    return jsonify({'count': count, 'name': name})


@movies_bp.route('/api/unregistered-folders')
@login_required
def api_unregistered_folders():
    """Liste les sous-dossiers de MOVIES_FOLDER non référencés comme séries."""
    if current_user.role != 'admin':
        return jsonify([])
    folder = current_app.config.get('MOVIES_FOLDER', '')
    if not folder or not os.path.isdir(folder):
        return jsonify([])
    registered = {
        m.file_filename
        for m in Movie.query.filter_by(content_type='série').with_entities(Movie.file_filename).all()
        if m.file_filename
    }
    result = []
    for name in sorted(os.listdir(folder)):
        fp = os.path.join(folder, name)
        if os.path.isdir(fp) and name not in registered:
            ep_count = sum(
                1 for root, _, files in os.walk(fp)
                for f in files if os.path.splitext(f)[1].lower() in _ALLOWED_EXT
            )
            result.append({'name': name, 'episode_count': ep_count})
    return jsonify(result)


@movies_bp.route('/api/unregistered-count')
@login_required
def api_unregistered_count():
    """Retourne le nombre de fichiers vidéo dans MOVIES_FOLDER non référencés en DB (admin)."""
    if current_user.role != 'admin':
        return jsonify({'count': 0})
    folder = current_app.config.get('MOVIES_FOLDER', '')
    if not folder or not os.path.isdir(folder):
        return jsonify({'count': 0})
    registered = {m.file_filename for m in Movie.query.with_entities(Movie.file_filename).all() if m.file_filename}
    count = sum(
        1 for f in os.listdir(folder)
        if os.path.splitext(f)[1].lower() in _ALLOWED_EXT and f not in registered
    )
    return jsonify({'count': count})


@movies_bp.route('/<int:movie_id>/telecharger/episode')
@login_required
def download_episode(movie_id):
    """Télécharge un épisode individuel d'une série."""
    movie = Movie.query.get_or_404(movie_id)
    if movie.content_type != 'série' or not movie.file_filename:
        abort(404)
    episode_file = request.args.get('f', '').strip()
    if not episode_file or '..' in episode_file:
        abort(400)
    folder = _movies_folder()
    serie_path = os.path.realpath(os.path.join(folder, movie.file_filename))
    episode_path = os.path.realpath(os.path.join(serie_path, episode_file))
    if not (episode_path.startswith(serie_path + os.sep) or episode_path.startswith(serie_path + '/')):
        abort(403)
    if not os.path.isfile(episode_path):
        abort(404)
    movie.download_count = (movie.download_count or 0) + 1
    movie.last_downloaded_by_id = current_user.id
    db.session.commit()
    current_app.logger.info("Épisode téléchargé : %s / %s par %s", movie.title, episode_file, current_user.username)
    return send_file(episode_path, as_attachment=True, download_name=os.path.basename(episode_path))


@movies_bp.route('/<int:movie_id>/telecharger/tous')
@login_required
def download_all_episodes(movie_id):
    """Télécharge tous les épisodes d'une série dans un zip."""
    movie = Movie.query.get_or_404(movie_id)
    if movie.content_type != 'série' or not movie.file_filename:
        abort(404)
    folder = _movies_folder()
    serie_path = os.path.join(folder, movie.file_filename)
    if not os.path.isdir(serie_path):
        abort(404)
    episodes = _list_episodes(serie_path)
    if not episodes:
        abort(404)
    safe_name = re.sub(r'[^\w\s.-]', '', movie.title).strip().replace(' ', '.')
    zip_name = f"{safe_name}.zip"
    movie.download_count = (movie.download_count or 0) + 1
    movie.last_downloaded_by_id = current_user.id
    db.session.commit()
    current_app.logger.info("Série téléchargée (zip) : %s par %s", movie.title, current_user.username)

    def _generate_zip():
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_STORED, allowZip64=True) as zf:
            for ep in episodes:
                ep_path = os.path.join(serie_path, ep['filename'])
                if os.path.isfile(ep_path):
                    zf.write(ep_path, ep['filename'])
                    buf.seek(0)
                    yield buf.read()
                    buf.seek(0)
                    buf.truncate(0)
        buf.seek(0)
        remaining = buf.read()
        if remaining:
            yield remaining

    response = Response(
        stream_with_context(_generate_zip()),
        mimetype='application/zip',
        headers={
            'Content-Disposition': f'attachment; filename="{zip_name}"',
        },
    )
    return response


@movies_bp.route('/<int:movie_id>/supprimer', methods=['POST'])
@login_required
def delete(movie_id):
    if current_user.role != 'admin':
        abort(403)
    movie = Movie.query.get_or_404(movie_id)
    title = movie.title
    if movie.file_filename:
        folder = current_app.config.get('MOVIES_FOLDER', '')
        fp = os.path.join(folder, movie.file_filename)
        if os.path.isfile(fp):
            os.remove(fp)
    db.session.delete(movie)
    db.session.commit()
    current_app.logger.info("Film supprimé : %s par %s", title, current_user.username)
    flash(f'« {title} » a été supprimé.', 'success')
    return redirect(url_for('movies.index'))
