"""
Module de routes principales pour l'application TemplateApp.

Ce module définit toutes les routes principales de l'application incluant :
- Pages du tableau de bord (dashboard, graphiques, automatisation, etc.)
- Gestion du profil utilisateur
- Gestion des notifications
- Génération d'icônes PWA
- Manifest PWA
- API de temps serveur
- Service worker PWA
- Gestionnaires d'erreurs

Blueprint : main_bp (sans préfixe d'URL)

Toutes les routes (sauf celles liées à PWA et erreurs) nécessitent une authentification
via le décorateur @login_required.
"""

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
    """
    Invalide le cache des paramètres système.
    
    Cette fonction réinitialise le cache des settings utilisé pour optimiser
    les accès aux paramètres système. Elle doit être appelée après chaque
    modification d'un paramètre pour garantir la cohérence des données.
    
    Note:
        Le cache n'est actuellement pas utilisé dans l'application mais est
        conservé pour une utilisation future.
    
    Returns:
        None
    """
    global _settings_cache, _settings_cache_timestamp
    _settings_cache.clear()
    _settings_cache_timestamp = None


@main_bp.route("/")
@login_required
def dashboard():
    """
    Page d'accueil du tableau de bord.
    
    Route: GET /
    Authentification: Requise
    
    Description:
        Affiche la page d'accueil principale de l'application. Cette page
        est actuellement vide et sert de template de base pour le développement.
    
    Returns:
        Template HTML: dashboard/index.html
    
    Note:
        Cette route est protégée par @login_required. Les utilisateurs non
        authentifiés seront redirigés vers la page de connexion.
    """
    return render_template("dashboard/index.html")


@main_bp.route("/graphiques")
@login_required
def charts():
    """
    Page de graphiques.
    
    Route: GET /graphiques
    Authentification: Requise
    
    Description:
        Affiche la page des graphiques. Cette page est actuellement vide
        et sert de template de base pour l'implémentation de graphiques.
    
    Returns:
        Template HTML: dashboard/charts.html
    """
    return render_template("dashboard/charts.html")


@main_bp.route("/automatisation")
@login_required
def automation():
    """
    Page d'automatisation.
    
    Route: GET /automatisation
    Authentification: Requise
    
    Description:
        Affiche la page de gestion de l'automatisation. Cette page est
        actuellement vide et sert de template de base pour l'implémentation
        des règles d'automatisation.
    
    Returns:
        Template HTML: dashboard/automation.html
    """
    return render_template("dashboard/automation.html")


@main_bp.route("/camera")
@login_required
def camera():
    """
    Page de la caméra.
    
    Route: GET /camera
    Authentification: Requise
    
    Description:
        Affiche la page de visualisation de la caméra. Cette page est
        actuellement vide et sert de template de base pour l'implémentation
        du flux vidéo.
    
    Returns:
        Template HTML: dashboard/camera.html
    """
    return render_template("dashboard/camera.html")


@main_bp.route("/parametres")
@login_required
def settings():
    """
    Page des paramètres.
    
    Route: GET /parametres
    Authentification: Requise
    
    Description:
        Affiche la page de gestion des paramètres système. Cette page est
        actuellement vide et sert de template de base pour l'implémentation
        de la configuration.
    
    Returns:
        Template HTML: dashboard/settings.html
    """
    return render_template("dashboard/settings.html")


@main_bp.route("/journal")
@login_required
def journal():
    """
    Page du journal d'activité.
    
    Route: GET /journal
    Authentification: Requise
    
    Description:
        Affiche la page du journal d'activité. Cette page est actuellement
        vide et sert de template de base pour l'implémentation de l'historique
        des événements.
    
    Returns:
        Template HTML: dashboard/journal.html
    """
    return render_template("dashboard/journal.html")


@main_bp.route("/affichage-lcd")
@login_required
def lcd_preview():
    """
    Page de prévisualisation de l'affichage LCD.
    
    Route: GET /affichage-lcd
    Authentification: Requise
    
    Description:
        Affiche la page de prévisualisation de l'affichage LCD. Cette page
        est actuellement vide et sert de template de base pour l'implémentation
        de la visualisation LCD.
    
    Returns:
        Template HTML: dashboard/lcd_preview.html
    """
    return render_template("dashboard/lcd_preview.html")


@main_bp.route("/profil", methods=["GET", "POST"])
@login_required
def profile():
    """
    Gestion du profil utilisateur.
    
    Route: GET, POST /profil
    Authentification: Requise
    
    Description:
        Permet à l'utilisateur connecté de consulter et modifier son profil.
        Les modifications incluent :
        - Informations personnelles (civilité, prénom, nom)
        - Identifiants (username, email)
        - Mot de passe (optionnel)
        - Adresse (rue, code postal, ville, pays)
        - Téléphone
        - Avatar (upload/suppression)
        - Activation/désactivation de la 2FA
    
    Méthodes HTTP:
        GET: Affiche le formulaire pré-rempli avec les données de l'utilisateur
        POST: Traite la soumission du formulaire et met à jour le profil
    
    Validation:
        - Vérifie l'unicité du username (si modifié)
        - Vérifie l'unicité de l'email (si modifié)
        - Vérifie la correspondance des mots de passe (si changement)
        - Vérifie la présence d'un email pour activer la 2FA
    
    Fonctionnalités:
        - Upload d'avatar avec génération de nom unique
        - Suppression d'avatar existant
        - Gestion de la 2FA (activation/désactivation avec nettoyage des tokens)
        - Changement de mot de passe optionnel
        - Messages flash pour informer l'utilisateur des résultats
    
    Returns:
        GET: Template HTML avec formulaire pré-rempli
        POST (succès): Redirection vers /profil avec message de succès
        POST (erreur): Template HTML avec formulaire et messages d'erreur
    
    Flash Messages:
        - "warning": Username ou email déjà utilisé
        - "danger": Erreur de validation (mot de passe, 2FA)
        - "success": Profil mis à jour ou 2FA activée/désactivée
    """
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
    """
    Marque les notifications comme lues.
    
    Route: POST /notifications/read
    Authentification: Requise
    Content-Type: application/json
    
    Description:
        Marque une ou plusieurs notifications comme lues. Si aucun ID n'est
        fourni, toutes les notifications accessibles à l'utilisateur sont
        marquées comme lues.
    
    Body JSON (optionnel):
        {
            "ids": [1, 2, 3]  // Liste d'IDs de notifications à marquer comme lues
        }
    
    Logique de filtrage:
        Les notifications accessibles à l'utilisateur sont :
        - Notifications personnelles (user_id == current_user.id)
        - Notifications globales (audience == "global")
        - Notifications admin (audience == "admin" ET utilisateur est admin)
    
    Returns:
        JSON: {"status": "ok"}
    
    Exemple de requête:
        POST /notifications/read
        Content-Type: application/json
        {
            "ids": [1, 2, 3]
        }
    """
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
    """
    Supprime les notifications.
    
    Route: POST /notifications/clear
    Authentification: Requise
    Content-Type: application/json
    
    Description:
        Supprime les notifications personnelles de l'utilisateur ou marque
        comme lues les notifications globales/admin (qui ne peuvent pas être
        supprimées par l'utilisateur).
    
    Body JSON (optionnel):
        {
            "ids": [1, 2, 3]  // Liste d'IDs de notifications à supprimer
        }
    
    Comportement:
        - Notifications personnelles (user_id == current_user.id) : Suppression
        - Notifications globales/admin : Marquage comme lues (ne peuvent pas être supprimées)
        - Si aucun ID fourni : Traite toutes les notifications accessibles
    
    Validation:
        - Convertit les IDs en entiers (ignore les valeurs invalides)
        - Filtre uniquement les notifications accessibles à l'utilisateur
    
    Returns:
        JSON: {
            "status": "ok",
            "cleared": [1, 2, 3]  // Liste des IDs de notifications traitées
        }
    
    Exemple de requête:
        POST /notifications/clear
        Content-Type: application/json
        {
            "ids": [1, 2, 3]
        }
    """
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
    """
    Génère une icône PWA avec fond blanc.
    
    Route: GET /icon/<size>.png
    Authentification: Non requise (publique)
    
    Description:
        Génère dynamiquement une icône PNG de la taille spécifiée en centrant
        le logo de l'application sur un fond blanc. Utilisé pour les icônes
        PWA et les favicons.
    
    Paramètres URL:
        size (int): Taille de l'icône en pixels (ex: 180, 192, 256, 512)
    
    Fonctionnalités:
        - Ouvre le logo depuis app/static/img/logo.png
        - Crée une image carrée avec fond blanc
        - Redimensionne le logo avec marge de 20px de chaque côté
        - Centre le logo sur le fond blanc
        - Gère la transparence du logo (mode RGBA)
        - Utilise LANCZOS pour un redimensionnement de qualité
        - Cache l'icône générée pendant 1 an (max-age=31536000)
    
    Fallback:
        - Si PIL (Pillow) n'est pas disponible : sert le logo original
        - Si le logo n'existe pas : retourne 404
        - En cas d'erreur : sert le logo original
    
    Returns:
        Response: Image PNG avec headers de cache
        Status 404: Si le logo n'existe pas
    
    Headers:
        Content-Type: image/png
        Cache-Control: public, max-age=31536000
    
    Exemples:
        GET /icon/180.png  → Icône 180x180 pixels
        GET /icon/512.png  → Icône 512x512 pixels
    
    Note:
        Cette route est publique et ne nécessite pas d'authentification car
        les icônes PWA doivent être accessibles sans authentification.
    """
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
    """
    Retourne le manifest PWA (Progressive Web App).
    
    Route: GET /manifest.json
    Authentification: Non requise (publique)
    
    Description:
        Retourne le fichier manifest JSON requis pour installer l'application
        comme Progressive Web App (PWA) sur les appareils mobiles et desktop.
    
    Format JSON:
        {
            "name": "TemplateApp",
            "short_name": "TemplateApp",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#ffffff",
            "theme_color": "#0f172a",
            "lang": "fr",
            "icons": [
                {
                    "src": "URL de l'icône",
                    "sizes": "180x180",
                    "type": "image/png",
                    "purpose": "any"
                },
                ...
            ]
        }
    
    Icônes générées:
        - 180x180 : Pour iOS/iPad
        - 192x192 : Pour Android
        - 256x256 : Pour desktop
        - 512x512 : Pour splash screens
    
    Fonctionnalités PWA:
        - Installation sur l'écran d'accueil
        - Mode standalone (sans barre d'adresse)
        - Thème de couleur personnalisé
        - Icônes adaptatives
    
    Returns:
        JSON: Manifest PWA conforme au standard W3C
    
    Note:
        Cette route est publique et doit être accessible sans authentification
        pour permettre l'installation PWA.
    """
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
    """
    API retournant l'heure actuelle du serveur.
    
    Route: GET /api/server-time
    Authentification: Requise
    
    Description:
        Retourne l'heure actuelle du serveur en format JSON avec plusieurs
        représentations (locale, UTC, format lisible) et l'offset de timezone.
        Utile pour synchroniser l'heure côté client ou afficher l'heure serveur.
    
    Returns:
        JSON: {
            "timestamp": "2025-12-03T15:30:45.123456",  // ISO format (heure locale)
            "utc": "2025-12-03T14:30:45.123456",         // ISO format (UTC)
            "local": "15:30:45",                          // Format HH:MM:SS (heure locale)
            "date": "03/12/2025",                         // Format DD/MM/YYYY (heure locale)
            "timezone_offset": 1.0                        // Offset en heures (UTC+1)
        }
    
    Format des dates:
        - timestamp: Format ISO 8601 avec microsecondes (heure locale)
        - utc: Format ISO 8601 avec microsecondes (UTC)
        - local: Format HH:MM:SS (24 heures)
        - date: Format DD/MM/YYYY
    
    Calcul de l'offset:
        L'offset est calculé en comparant datetime.now() et datetime.utcnow()
        et converti en heures (décimal). Positif si local est à l'est de UTC.
    
    Exemple de réponse:
        {
            "timestamp": "2025-12-03T15:30:45.123456",
            "utc": "2025-12-03T14:30:45.123456",
            "local": "15:30:45",
            "date": "03/12/2025",
            "timezone_offset": 1.0
        }
    
    Usage:
        Cette API peut être utilisée pour :
        - Synchroniser l'heure côté client
        - Afficher l'heure serveur dans l'interface
        - Calculer les différences de timezone
        - Valider les timestamps côté client
    """
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
    """
    Sert le fichier service worker pour PWA.
    
    Route: GET /service-worker.js
    Authentification: Non requise (publique)
    
    Description:
        Sert le fichier JavaScript du service worker nécessaire pour le
        fonctionnement de l'application en mode PWA (mise en cache, fonctionnement
        hors ligne, notifications push, etc.).
    
    Fichier source:
        app/static/js/service-worker.js
    
    Headers:
        Content-Type: application/javascript
        Cache-Control: max-age=0 (pas de cache pour toujours servir la dernière version)
    
    Fonctionnalités du service worker:
        - Mise en cache des ressources statiques
        - Gestion du fonctionnement hors ligne
        - Mise à jour automatique des ressources
        - Gestion des notifications push (si implémenté)
    
    Returns:
        Response: Contenu du fichier service-worker.js
    
    Note:
        - Cette route est publique et doit être accessible sans authentification
        - Le cache est désactivé pour garantir que les mises à jour du service
          worker sont immédiatement prises en compte
        - Le service worker doit être enregistré côté client dans le JavaScript
    """
    response = current_app.response_class(
        current_app.open_resource("static/js/service-worker.js").read(),
        mimetype="application/javascript",
    )
    response.cache_control.max_age = 0
    return response


@main_bp.errorhandler(404)
def not_found(error):  # type: ignore[override]
    """
    Gestionnaire d'erreur 404 (Page non trouvée).
    
    Description:
        Gère les erreurs 404 lorsque une route n'est pas trouvée. Affiche
        une page d'erreur personnalisée au lieu de la page d'erreur par défaut
        de Flask.
    
    Args:
        error: Exception Flask générée pour l'erreur 404
    
    Returns:
        Tuple: (Template HTML, Status Code 404)
            - Template: errors/404.html
            - Status: 404
    
    Template:
        errors/404.html : Page d'erreur personnalisée avec message et
                          lien de retour vers l'accueil
    """
    return render_template("errors/404.html"), 404


@main_bp.errorhandler(500)
def internal_error(error):  # type: ignore[override]
    """
    Gestionnaire d'erreur 500 (Erreur interne du serveur).
    
    Description:
        Gère les erreurs 500 (erreurs internes du serveur). Effectue un
        rollback de la session de base de données pour éviter les états
        incohérents, puis affiche une page d'erreur personnalisée.
    
    Args:
        error: Exception Flask générée pour l'erreur 500
    
    Fonctionnalités:
        - Rollback de la session DB pour éviter la corruption des données
        - Log de l'erreur (géré automatiquement par Flask)
        - Affichage d'une page d'erreur conviviale
    
    Returns:
        Tuple: (Template HTML, Status Code 500)
            - Template: errors/500.html
            - Status: 500
    
    Template:
        errors/500.html : Page d'erreur personnalisée avec message d'excuse
                          et instructions pour l'utilisateur
    
    Note:
        Le rollback de la session DB est important pour éviter que les erreurs
        laissent la base de données dans un état incohérent.
    """
    db.session.rollback()
    return render_template("errors/500.html"), 500
