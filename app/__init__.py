"""
Fichier : app/__init__.py
Objectif : Initialiser l’application Flask, configurer les extensions (Base de données,
           authentification, CSRF, CORS) et démarrer le planificateur des collectes de
           capteurs. Fournit la fabrique `create_app` utilisée par les points d’entrée.
Principales responsabilités :
    - Création de l’objet Flask et chargement de la configuration.
    - Enregistrement des blueprints publics, d’authentification et d’administration.
    - Injection de variables globales Jinja (notifications, palettes d’avatar, etc.).
    - Gestion du scheduler APScheduler pour lancer `collect_sensor_readings`.
    - Migration légère de schéma SQLite lors du démarrage de l’application.
Dépendances critiques : SQLAlchemy, Flask-Login, APScheduler, configuration locale.
"""

import atexit
import hashlib
import os
from datetime import datetime

from flask import Flask, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect, generate_csrf
from sqlalchemy import text
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import Config


db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
scheduler = BackgroundScheduler(timezone=os.getenv("TZ", "UTC"))


def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(Config)

    cors_origins = os.getenv("CORS_ORIGINS")
    if cors_origins:
        origins = [origin.strip() for origin in cors_origins.split(",") if origin.strip()]
        CORS(app, resources={r"/*": {"origins": origins}}, supports_credentials=True)
    else:
        CORS(app, resources={r"/*": {"origins": "*"}})

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"
    app.jinja_env.globals["csrf_token"] = generate_csrf

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    from .routes import main_bp
    from .auth import auth_bp
    from .admin import admin_bp
    from .tasks import collect_sensor_readings

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp)

    from .models import Notification

    @app.context_processor
    def inject_globals():
        notifications = []
        unread_count = 0
        if current_user.is_authenticated:
            base_query = Notification.query.filter(
                (Notification.user_id == current_user.id)
                | (Notification.audience == "global")
                | (
                    (Notification.audience == "admin")
                    & (current_user.role == "admin")
                )
            ).order_by(Notification.created_at.desc())
            notifications = base_query.limit(10).all()
            unread_count = base_query.filter(Notification.read.is_(False)).count()
        return {
            "header_notifications": notifications,
            "header_unread_notifications": unread_count,
            "current_year": datetime.utcnow().year,
            "is_admin": current_user.is_authenticated and getattr(current_user, "role", None) == "admin",
        }

    def avatar_palette(name: str) -> dict[str, str]:
        palette = [
            ("#0ea5e9", "#0369a1"),
            ("#14b8a6", "#0f766e"),
            ("#22c55e", "#15803d"),
            ("#8b5cf6", "#6d28d9"),
            ("#f97316", "#ea580c"),
            ("#ec4899", "#be185d"),
        ]
        digest = int(hashlib.sha1(name.encode("utf-8")).hexdigest(), 16)
        base, accent = palette[digest % len(palette)]
        gradient = f"linear-gradient(135deg, {base}, {accent})"
        shadow = f"0 8px 18px -10px {accent}"
        return {"gradient": gradient, "accent": accent, "shadow": shadow}

    app.jinja_env.globals["avatar_palette"] = avatar_palette

    def _start_scheduler():
        if not app.config.get("SENSOR_POLL_ENABLED", True):
            app.logger.info("Scheduler désactivé par configuration.")
            return
        if app.config.get("SCHEDULER_STARTED"):
            return
        interval = int(app.config.get("SENSOR_POLL_INTERVAL_MINUTES", 5))
        job_id = "sensor_readings"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
        scheduler.add_job(
            func=lambda: collect_sensor_readings(app),
            trigger=IntervalTrigger(minutes=interval),
            id=job_id,
            replace_existing=True,
            max_instances=1,
        )
        if not scheduler.running:
            scheduler.start()
            atexit.register(lambda: scheduler.shutdown(wait=False))
        app.config["SCHEDULER_STARTED"] = True
        app.logger.info("Scheduler démarré (intervalle %s min).", interval)

    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        _start_scheduler()

    with app.app_context():
        from . import seed

        db.create_all()
        try:
            notif_cols = {
                row[1]
                for row in db.session.execute(text("PRAGMA table_info(notification)"))
            }
            if "persistent" not in notif_cols:
                db.session.execute(
                    text("ALTER TABLE notification ADD COLUMN persistent BOOLEAN DEFAULT 0")
                )
                db.session.commit()

            user_cols = {
                row[1]
                for row in db.session.execute(text("PRAGMA table_info(user)"))
            }
            if "last_login" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN last_login DATETIME")
                )
                db.session.commit()
            if "avatar_filename" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN avatar_filename VARCHAR(255)")
                )
                db.session.commit()
            if "twofa_enabled" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN twofa_enabled BOOLEAN DEFAULT 0")
                )
                db.session.commit()
            if "twofa_code_hash" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN twofa_code_hash VARCHAR(255)")
                )
                db.session.commit()
            if "twofa_code_sent_at" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN twofa_code_sent_at DATETIME")
                )
                db.session.commit()
            if "twofa_trusted_token_hash" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN twofa_trusted_token_hash VARCHAR(255)")
                )
                db.session.commit()
            if "twofa_trusted_created_at" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN twofa_trusted_created_at DATETIME")
                )
                db.session.commit()

            automation_cols = {
                row[1]
                for row in db.session.execute(text("PRAGMA table_info(automation_rule)"))
            }
            if "enabled" not in automation_cols:
                db.session.execute(
                    text("ALTER TABLE automation_rule ADD COLUMN enabled BOOLEAN DEFAULT 1")
                )
                db.session.commit()
            if "cooldown_seconds" not in automation_cols:
                db.session.execute(
                    text("ALTER TABLE automation_rule ADD COLUMN cooldown_seconds INTEGER DEFAULT 300")
                )
                db.session.commit()
            if "last_triggered_at" not in automation_cols:
                db.session.execute(
                    text("ALTER TABLE automation_rule ADD COLUMN last_triggered_at DATETIME")
                )
                db.session.commit()
        except Exception as exc:  # pragma: no cover - dépend de l'état SQLite
            app.logger.warning("Impossible de vérifier les schémas SQLite: %s", exc)
        seed.ensure_default_admin()

    return app
