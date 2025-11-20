import atexit
import hashlib
import os
from datetime import datetime
from pathlib import Path

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

from .tasks import collect_sensor_readings


def schedule_sensor_poll(app: Flask, minutes: int) -> None:
    minutes = max(1, int(minutes))
    job_id = "sensor_readings"
    trigger = IntervalTrigger(minutes=minutes)

    if scheduler.get_job(job_id):
        scheduler.reschedule_job(job_id, trigger=trigger)
    else:
        scheduler.add_job(
            func=lambda: collect_sensor_readings(app),
            trigger=trigger,
            id=job_id,
            replace_existing=True,
            max_instances=1,
        )

    if not scheduler.running:
        scheduler.start()
        if not app.config.get("SCHEDULER_SHUTDOWN_REGISTERED"):
            atexit.register(lambda: scheduler.shutdown(wait=False))
            app.config["SCHEDULER_SHUTDOWN_REGISTERED"] = True

    app.config["SCHEDULER_STARTED"] = True
    app.config["SENSOR_POLL_INTERVAL_MINUTES"] = minutes
    app.logger.info("Scheduler capteurs configuré (%s min).", minutes)


def schedule_lcd_auto_scroll(app: Flask) -> None:
    """Planifie le défilement automatique des pages LCD toutes les 3 secondes"""
    if not app.config.get("LCD_ENABLED", False):
        app.logger.info("Défilement LCD automatique désactivé (LCD_ENABLED=False).")
        return
    
    job_id = "lcd_auto_scroll"
    trigger = IntervalTrigger(seconds=3)
    
    if scheduler.get_job(job_id):
        scheduler.reschedule_job(job_id, trigger=trigger)
    else:
        scheduler.add_job(
            func=lambda: _run_lcd_auto_scroll(app),
            trigger=trigger,
            id=job_id,
            replace_existing=True,
            max_instances=1,
        )
    
    if not scheduler.running:
        scheduler.start()
        if not app.config.get("SCHEDULER_SHUTDOWN_REGISTERED"):
            atexit.register(lambda: scheduler.shutdown(wait=False))
            app.config["SCHEDULER_SHUTDOWN_REGISTERED"] = True
    
    app.logger.info("Défilement LCD automatique configuré (toutes les 3 secondes).")


def _run_lcd_auto_scroll(app: Flask) -> None:
    """Wrapper pour exécuter le défilement LCD dans le contexte de l'application"""
    with app.app_context():
        from .lcd_display import auto_scroll_lcd_pages
        auto_scroll_lcd_pages()


def create_app():
    import logging
    logger = logging.getLogger(__name__)
    
    app = Flask(__name__, static_folder="static", template_folder="templates")
    
    app.config.from_object(Config)
    
    # Vérifier et préparer la base de données AVANT d'initialiser SQLAlchemy
    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if app.debug:
        logger.debug(f"URI de la base de données: {db_uri}")
    
    if db_uri.startswith("sqlite:///"):
        db_file_path = db_uri.replace("sqlite:///", "")
        db_file = Path(db_file_path)
        db_file_abs = db_file.resolve()  # Chemin absolu du fichier
        db_file_parent_abs = db_file_abs.parent  # Parent du chemin absolu
        
        if app.debug:
            logger.debug(f"Chemin du fichier DB extrait: {db_file_path}")
            logger.debug(f"Chemin résolu (absolu): {db_file_abs}")
            logger.debug(f"Répertoire parent existe: {db_file_parent_abs.exists()}")
        
        # S'assurer que le répertoire parent existe (utiliser le chemin absolu)
        try:
            db_file_parent_abs.mkdir(parents=True, exist_ok=True)
            if app.debug:
                logger.debug(f"Répertoire parent créé/vérifié: {db_file_parent_abs}")
        except Exception as e:
            logger.error(f"ERREUR création répertoire: {e}", exc_info=True)
            raise
        
        # Vérifier les permissions (utiliser le chemin absolu)
        if not os.access(db_file_parent_abs, os.W_OK):
            logger.error(f"Pas de permission d'écriture sur {db_file_parent_abs}")
            logger.error(f"Propriétaire: {os.stat(db_file_parent_abs).st_uid}, UID actuel: {os.getuid()}")
            raise PermissionError(f"Pas de permission d'écriture sur {db_file_parent_abs}")
        
        # Tester la connexion SQLite directe AVANT SQLAlchemy (utiliser le chemin absolu)
        try:
            import sqlite3
            test_conn = sqlite3.connect(str(db_file_abs), timeout=10.0)
            test_conn.execute("SELECT 1")
            test_conn.close()
            if app.debug:
                logger.debug("Connexion SQLite directe réussie")
        except Exception as e:
            logger.error(f"ERREUR connexion SQLite directe: {e}", exc_info=True)
            raise

    cors_origins = os.getenv("CORS_ORIGINS")
    if cors_origins:
        origins = [origin.strip() for origin in cors_origins.split(",") if origin.strip()]
        CORS(app, resources={r"/*": {"origins": origins}}, supports_credentials=True)
    else:
        CORS(app, resources={r"/*": {"origins": "*"}})

    # Vérifier et corriger l'URI de la base de données avant d'initialiser SQLAlchemy
    final_db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    
    # Si l'URI utilise un chemin relatif (3 slashes), le convertir en absolu avec 4 slashes
    if final_db_uri.startswith("sqlite:///") and not final_db_uri.startswith("sqlite:////"):
        db_file_path = final_db_uri.replace("sqlite:///", "")
        db_file_abs = Path(db_file_path).resolve()
        final_db_uri = f"sqlite:////{str(db_file_abs).replace(chr(92), '/')}"
        app.config["SQLALCHEMY_DATABASE_URI"] = final_db_uri
        if app.debug:
            logger.debug(f"URI corrigée en absolu avec 4 slashes: {final_db_uri}")
    
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"
    app.jinja_env.globals["csrf_token"] = generate_csrf
    
    # Ajouter le filtre pour formater les dates en heure locale
    from .utils import format_local_datetime
    def local_datetime_filter(dt, format_str="%d/%m/%Y %H:%M"):
        """Filtre Jinja2 pour formater les dates UTC en heure locale"""
        return format_local_datetime(dt, format_str)
    app.jinja_env.filters["local_datetime"] = local_datetime_filter

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    from .routes import main_bp
    from .auth import auth_bp
    from .admin import admin_bp
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
        if app.config.get("SCHEDULER_STARTED"):
            return
        
        # Planifier le défilement automatique du LCD (indépendant de la collecte de capteurs)
        schedule_lcd_auto_scroll(app)
        
        # Planifier la collecte de capteurs si activée
        if not app.config.get("SENSOR_POLL_ENABLED", True):
            app.logger.info("Scheduler capteurs désactivé par configuration.")
            return
        
        interval = int(app.config.get("SENSOR_POLL_INTERVAL_MINUTES", 30))
        try:
            with app.app_context():
                from .models import Setting

                stored = Setting.query.filter_by(key="Sensor_Poll_Interval_Minutes").first()
                if stored and stored.value:
                    interval = int(str(stored.value).strip())
        except Exception as exc:  # pragma: no cover - lecture optionnelle
            app.logger.warning("Impossible de lire Sensor_Poll_Interval_Minutes: %s", exc)

        schedule_sensor_poll(app, interval)

    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        _start_scheduler()

    def _ensure_scheduler_once():
        _start_scheduler()

    if hasattr(app, "before_first_request"):
        app.before_first_request(_ensure_scheduler_once)
    else:  # compat Flask >=3.1
        app.before_request(_ensure_scheduler_once)

    with app.app_context():
        from . import seed
        
        # Vérifier que la base de données peut être créée/ouverte avant de continuer
        db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        app.logger.info(f"Tentative de connexion à la base de données avec URI: {db_uri}")
        
        if db_uri.startswith("sqlite:///"):
            db_file_path = db_uri.replace("sqlite:///", "")
            db_file = Path(db_file_path)
            
            app.logger.info(f"Chemin du fichier DB extrait: {db_file_path}")
            app.logger.info(f"Chemin Path object: {db_file}")
            app.logger.info(f"Répertoire parent: {db_file.parent}")
            app.logger.info(f"Répertoire parent existe: {db_file.parent.exists()}")
            
            # S'assurer que le répertoire parent existe
            try:
                db_file.parent.mkdir(parents=True, exist_ok=True)
                app.logger.info(f"Répertoire parent créé/vérifié: {db_file.parent}")
            except Exception as e:
                app.logger.error(f"ERREUR lors de la création du répertoire parent: {e}")
                raise
            
            # Vérifier les permissions
            if not os.access(db_file.parent, os.W_OK):
                app.logger.error(f"ERREUR: Pas de permission d'écriture sur {db_file.parent}")
                app.logger.error(f"Propriétaire du répertoire: {os.stat(db_file.parent).st_uid}")
                app.logger.error(f"UID actuel: {os.getuid()}")
                raise PermissionError(f"Pas de permission d'écriture sur {db_file.parent}")
            
            # Tester la création/ouverture du fichier directement avec sqlite3
            try:
                import sqlite3
                app.logger.info(f"Test de connexion SQLite directe à: {db_file}")
                test_conn = sqlite3.connect(str(db_file), timeout=10.0)
                test_conn.execute("SELECT 1")
                test_conn.close()
                app.logger.info(f"✓ Test de connexion SQLite réussi pour: {db_file}")
            except Exception as e:
                app.logger.error(f"ERREUR lors du test de connexion SQLite: {e}")
                app.logger.error(f"Type d'erreur: {type(e).__name__}")
                import traceback
                app.logger.error(traceback.format_exc())
                raise

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
