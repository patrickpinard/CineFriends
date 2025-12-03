from __future__ import annotations

from datetime import datetime
from pathlib import Path
from io import BytesIO

from flask import (Blueprint, current_app, flash, jsonify, redirect,
                   render_template, request, send_from_directory, url_for)
from flask_login import current_user, login_required

from . import db
from .forms import ProfileForm
from .models import Notification, User
from .utils import build_changes, delete_avatar, save_avatar

main_bp = Blueprint("main", __name__)


# Cache pour les settings (invalidé à chaque modification)
_settings_cache: dict[str, str | None] = {}
_settings_cache_timestamp: datetime | None = None


def invalidate_settings_cache() -> None:
    """Invalide le cache des settings (à appeler après modification)"""
    global _settings_cache, _settings_cache_timestamp
    _settings_cache.clear()
    _settings_cache_timestamp = None


@main_bp.route("/")
@login_required
def dashboard():
    """Page d'accueil vide"""
    return render_template("dashboard/index.html")


@main_bp.route("/graphiques")
@login_required
def charts():
    """Page graphiques vide"""
    return render_template("dashboard/charts.html")


@main_bp.route("/automatisation")
@login_required
def automation():
    """Page automatisation vide"""
    return render_template("dashboard/automation.html")


@main_bp.route("/camera")
@login_required
def camera():
    """Page caméra vide"""
    return render_template("dashboard/camera.html")


@main_bp.route("/parametres")
@login_required
def settings():
    """Page paramètres vide"""
    return render_template("dashboard/settings.html")


@main_bp.route("/journal")
@login_required
def journal():
    """Page journal vide"""
    return render_template("dashboard/journal.html")


@main_bp.route("/affichage-lcd")
@login_required
def lcd_preview():
    """Page affichage LCD vide"""
    return render_template("dashboard/lcd_preview.html")


@main_bp.route("/profil", methods=["GET", "POST"])
@login_required
def profile():
    """Gestion du profil utilisateur"""
    form = ProfileForm()
    if request.method == "GET":
        form.title.data = getattr(current_user, 'title', None)
        form.first_name.data = getattr(current_user, 'first_name', None)
        form.last_name.data = getattr(current_user, 'last_name', None)
        form.username.data = current_user.username
        form.email.data = current_user.email
        form.street.data = getattr(current_user, 'street', None)
        form.postal_code.data = getattr(current_user, 'postal_code', None)
        form.city.data = getattr(current_user, 'city', None)
        form.country.data = getattr(current_user, 'country', None)
        form.phone.data = getattr(current_user, 'phone', None)
        form.twofa_enabled.data = current_user.twofa_enabled

    if form.validate_on_submit():
        if (
            form.username.data != current_user.username
            and User.query.filter_by(username=form.username.data).first()
        ):
            flash("Ce nom d'utilisateur est déjà utilisé par un autre compte. Veuillez en choisir un autre.", "warning")
            return render_template("dashboard/profile.html", form=form)
        elif (
            form.email.data
            and form.email.data.strip()
            and form.email.data.strip() != (current_user.email or "").strip()
            and User.query.filter_by(email=form.email.data.strip()).first()
        ):
            flash(f"L'adresse email « {form.email.data.strip()} » est déjà utilisée par un autre compte. Veuillez utiliser une autre adresse email.", "warning")
            return render_template("dashboard/profile.html", form=form)
        else:
            if form.password.data and (not form.confirm_password.data or form.password.data != form.confirm_password.data):
                flash("Merci de confirmer le nouveau mot de passe.", "danger")
                return render_template("dashboard/profile.html", form=form)
            if form.twofa_enabled.data and not form.email.data and not current_user.email:
                flash("Un email valide est requis pour activer la 2FA.", "danger")
                return render_template("dashboard/profile.html", form=form)
            twofa_before = current_user.twofa_enabled
            original_state = {
                "username": current_user.username,
                "email": current_user.email,
                "twofa_enabled": current_user.twofa_enabled,
            }
            if form.remove_avatar.data:
                delete_avatar(current_user.avatar_filename)
                current_user.avatar_filename = None
            elif form.avatar.data:
                delete_avatar(current_user.avatar_filename)
                current_user.avatar_filename = save_avatar(form.avatar.data)
            current_user.title = form.title.data.strip() if form.title.data else None
            current_user.first_name = form.first_name.data.strip() if form.first_name.data else None
            current_user.last_name = form.last_name.data.strip() if form.last_name.data else None
            current_user.username = form.username.data
            current_user.email = form.email.data.strip() if form.email.data else None
            current_user.street = form.street.data.strip() if form.street.data else None
            current_user.postal_code = form.postal_code.data.strip() if form.postal_code.data else None
            current_user.city = form.city.data.strip() if form.city.data else None
            current_user.country = form.country.data.strip() if form.country.data else None
            current_user.phone = form.phone.data.strip() if form.phone.data else None
            if form.twofa_enabled.data:
                current_user.twofa_enabled = True
            else:
                current_user.twofa_enabled = False
                current_user.twofa_code_hash = None
                current_user.twofa_code_sent_at = None
                current_user.twofa_trusted_token_hash = None
                current_user.twofa_trusted_created_at = None
            if form.password.data:
                current_user.set_password(form.password.data)
            db.session.add(current_user)
            db.session.commit()
            if twofa_before != current_user.twofa_enabled:
                status = "activée" if current_user.twofa_enabled else "désactivée"
                flash(f"Double authentification {status}.", "success")
            else:
                flash("Profil mis à jour.", "success")
            return redirect(url_for("main.profile"))

    return render_template("dashboard/profile.html", form=form)


@main_bp.route("/notifications/read", methods=["POST"])
@login_required
def notifications_mark_read():
    """Marquer les notifications comme lues"""
    ids = request.json.get("ids") if request.is_json else None  # type: ignore[attr-defined]
    query = Notification.query.filter(
        (Notification.user_id == current_user.id)
        | (Notification.audience == "global")
        | ((Notification.audience == "admin") & (current_user.role == "admin"))
    )
    if ids:
        query = query.filter(Notification.id.in_(ids))
    for notif in query:
        notif.read = True
        db.session.add(notif)
    db.session.commit()
    return jsonify({"status": "ok"})


@main_bp.route("/notifications/clear", methods=["POST"])
@login_required
def notifications_clear():
    """Supprimer les notifications"""
    payload = request.get_json(silent=True) or {}
    ids = payload.get("ids")

    query = Notification.query.filter(
        (Notification.user_id == current_user.id)
        | (Notification.audience == "global")
        | ((Notification.audience == "admin") & (current_user.role == "admin"))
    )

    if ids:
        try:
            ids = [int(_id) for _id in ids]
        except (TypeError, ValueError):
            ids = []
        if ids:
            query = query.filter(Notification.id.in_(ids))

    notifications = query.all()
    cleared_ids: list[int] = []
    for notif in notifications:
        cleared_ids.append(notif.id)
        if notif.user_id == current_user.id:
            db.session.delete(notif)
        else:
            notif.read = True
            db.session.add(notif)

    db.session.commit()
    return jsonify({"status": "ok", "cleared": cleared_ids})


@main_bp.route("/icon/<int:size>.png", endpoint="generate_icon")
def generate_icon(size: int):
    """Génère une icône avec fond blanc pour iOS/iPad."""
    try:
        from PIL import Image
        
        logo_path = Path(current_app.static_folder) / "img" / "logo.png"
        if not logo_path.exists():
            return send_from_directory(current_app.static_folder, "img/logo.png"), 404
        
        # Ouvrir le logo
        logo = Image.open(logo_path)
        
        # Créer une image avec fond blanc
        icon = Image.new("RGB", (size, size), color="white")
        
        # Calculer la taille et position pour centrer le logo
        logo_size = min(size - 40, logo.width, logo.height)  # Marge de 20px de chaque côté
        logo_resized = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
        
        # Centrer le logo sur le fond blanc
        x = (size - logo_size) // 2
        y = (size - logo_size) // 2
        
        # Coller le logo sur le fond blanc (gérer la transparence)
        if logo.mode == "RGBA":
            icon.paste(logo_resized, (x, y), logo_resized)
        else:
            icon.paste(logo_resized, (x, y))
        
        # Retourner l'image
        output = BytesIO()
        icon.save(output, format="PNG")
        output.seek(0)
        
        return current_app.response_class(
            output.read(),
            mimetype="image/png",
            headers={"Cache-Control": "public, max-age=31536000"}
        )
    except ImportError:
        # Si PIL n'est pas disponible, servir le logo original
        return send_from_directory(current_app.static_folder, "img/logo.png")
    except Exception as exc:
        current_app.logger.error(f"Erreur génération icône {size}x{size}: {exc}")
        return send_from_directory(current_app.static_folder, "img/logo.png")


@main_bp.route("/manifest.json")
def manifest():
    """Manifest PWA"""
    manifest_data = {
        "name": "TemplateApp",
        "short_name": "TemplateApp",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#0f172a",
        "lang": "fr",
        "icons": [
            {
                "src": url_for("main.generate_icon", size=180, _external=True),
                "sizes": "180x180",
                "type": "image/png",
                "purpose": "any"
            },
            {
                "src": url_for("main.generate_icon", size=192, _external=True),
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any"
            },
            {
                "src": url_for("main.generate_icon", size=256, _external=True),
                "sizes": "256x256",
                "type": "image/png",
                "purpose": "any"
            },
            {
                "src": url_for("main.generate_icon", size=512, _external=True),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any"
            }
        ]
    }
    return jsonify(manifest_data)


@main_bp.route("/api/server-time")
@login_required
def server_time():
    """Retourne l'heure actuelle du serveur en heure locale"""
    server_now_local = datetime.now()
    server_now_utc = datetime.utcnow()
    
    return jsonify({
        "timestamp": server_now_local.isoformat(),
        "utc": server_now_utc.isoformat(),
        "local": server_now_local.strftime("%H:%M:%S"),
        "date": server_now_local.strftime("%d/%m/%Y"),
        "timezone_offset": (server_now_local - server_now_utc).total_seconds() / 3600,  # Offset en heures
    })


@main_bp.route("/service-worker.js")
def service_worker():
    """Service worker pour PWA"""
    response = current_app.response_class(
        current_app.open_resource("static/js/service-worker.js").read(),
        mimetype="application/javascript",
    )
    response.cache_control.max_age = 0
    return response


@main_bp.errorhandler(404)
def not_found(error):  # type: ignore[override]
    """Gestionnaire d'erreur 404"""
    return render_template("errors/404.html"), 404


@main_bp.errorhandler(500)
def internal_error(error):  # type: ignore[override]
    """Gestionnaire d'erreur 500"""
    db.session.rollback()
    return render_template("errors/500.html"), 500
