import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect, generate_csrf
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from flask_caching import Cache
from sqlalchemy import text
from flask_cors import CORS  # noqa: F401 — kept for possible direct use

from config import get_config
from .security import configure_security


def utcnow() -> datetime:
    """Retourne la date/heure UTC actuelle (remplace datetime.utcnow() déprécié)."""
    return datetime.now(timezone.utc)


db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
migrate = Migrate()
# Limiter : utilise le stockage en mémoire par défaut (dev)
# En production, configurer avec Redis pour un stockage persistant :
# limiter = Limiter(
#     key_func=get_remote_address,
#     default_limits=["200 per day", "50 per hour"],
#     storage_uri=os.getenv("RATELIMIT_STORAGE_URL", "memory://")
# )
limiter = Limiter(key_func=get_remote_address, default_limits=["2000 per day", "500 per hour"])
cache = Cache()


def create_app(config_name=None):
    """
    Factory function pour créer l'application Flask.
    
    Args:
        config_name: Nom de la configuration à utiliser ('development', 'testing', 'production').
                    Si None, utilise FLASK_ENV ou 'development' par défaut.
    
    Returns:
        Instance de l'application Flask configurée.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    app = Flask(__name__, static_folder="static", template_folder="templates")
    
    # Charger la configuration appropriée
    config_class = get_config() if config_name is None else config.get(config_name, get_config())
    app.config.from_object(config_class)
    
    # Évaluer la propriété SQLALCHEMY_DATABASE_URI (car c'est une @property)
    # Flask ne peut pas évaluer automatiquement les propriétés avec from_object()
    instance = config_class()
    app.config['SQLALCHEMY_DATABASE_URI'] = instance.SQLALCHEMY_DATABASE_URI
    
    config_class.init_app(app)
    
    # Vérifier et préparer la base de données AVANT d'initialiser SQLAlchemy
    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    
    if db_uri.startswith("sqlite:///"):
        db_file_path = db_uri.replace("sqlite:///", "")
        db_file = Path(db_file_path)
        db_file_abs = db_file.resolve()  # Chemin absolu du fichier
        db_file_parent_abs = db_file_abs.parent  # Parent du chemin absolu
        
        # S'assurer que le répertoire parent existe (utiliser le chemin absolu)
        try:
            db_file_parent_abs.mkdir(parents=True, exist_ok=True)
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
        except Exception as e:
            logger.error(f"ERREUR connexion SQLite directe: {e}", exc_info=True)
            raise

    # Configuration CORS + headers de sécurité (Talisman)
    configure_security(app)

    # Vérifier et corriger l'URI de la base de données avant d'initialiser SQLAlchemy
    final_db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    
    # Si l'URI utilise un chemin relatif (3 slashes), le convertir en absolu avec 4 slashes
    if final_db_uri.startswith("sqlite:///") and not final_db_uri.startswith("sqlite:////"):
        db_file_path = final_db_uri.replace("sqlite:///", "")
        # Résoudre le chemin relatif depuis le répertoire de base de l'application
        BASE_DIR = Path(__file__).parent.parent
        if not Path(db_file_path).is_absolute():
            db_file_abs = (BASE_DIR / db_file_path).resolve()
        else:
            db_file_abs = Path(db_file_path).resolve()
        
        # S'assurer que le répertoire parent existe et est accessible en écriture
        db_file_abs.parent.mkdir(parents=True, exist_ok=True)
        if not os.access(db_file_abs.parent, os.W_OK):
            logger.error(f"Pas de permission d'écriture sur {db_file_abs.parent}")
            raise PermissionError(f"Pas de permission d'écriture sur {db_file_abs.parent}")
        
        # Convertir en URI absolue avec 4 slashes
        final_db_uri = f"sqlite:////{str(db_file_abs).replace(chr(92), '/')}"
        app.config["SQLALCHEMY_DATABASE_URI"] = final_db_uri
        if app.debug:
            logger.debug(f"URI corrigée en absolu avec 4 slashes: {final_db_uri}")
    
    # Initialiser les extensions
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)
    
    # Configuration du cache
    cache_config = {'CACHE_TYPE': app.config.get('CACHE_TYPE', 'simple')}
    if app.config.get('CACHE_REDIS_URL'):
        cache_config['CACHE_REDIS_URL'] = app.config['CACHE_REDIS_URL']
    cache.init_app(app, config=cache_config)

    # Configuration du logging vers fichier
    # Supprimer tous les handlers existants pour éviter les formats par défaut de Flask
    app.logger.handlers.clear()
    
    # Créer le répertoire logs s'il n'existe pas
    logs_dir = Path(__file__).parent.parent / "logs"
    logs_dir.mkdir(exist_ok=True)
    
    # Configurer le handler de fichier
    from logging.handlers import RotatingFileHandler
    log_file = logs_dir / "app.log"
    file_handler = RotatingFileHandler(
        str(log_file),
        maxBytes=10240000,  # 10 MB
        backupCount=10
    )
    
    if not app.debug or os.getenv("FLASK_ENV") == "production":
        file_handler.setLevel(logging.INFO)
        app.logger.setLevel(logging.INFO)
    else:
        file_handler.setLevel(logging.DEBUG)
        app.logger.setLevel(logging.DEBUG)
    
    # Format simplifié sans détails techniques
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s'
    ))
    app.logger.addHandler(file_handler)

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

    from .routes import main_bp  # package app/routes/
    from .auth import auth_bp
    from .admin import admin_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp)

    from .models import Notification

    @app.context_processor
    def inject_globals():
        from .models import User as _User
        notifications = []
        unread_count = 0
        admin_pending_tasks = []
        broadcast_notifications = []

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

            if current_user.role == "admin":
                pending_users = _User.query.filter_by(active=False).count()
                if pending_users:
                    admin_pending_tasks.append({
                        "type": "pending_users",
                        "count": pending_users,
                        "label": (
                            f"{pending_users} utilisateur en attente de validation"
                            if pending_users == 1
                            else f"{pending_users} utilisateurs en attente de validation"
                        ),
                        "url": "/admin/utilisateurs?tab=pending",
                        "level": "warning",
                    })

            # Notifications broadcast globales des 30 derniers jours (localStorage gère le "vu" par utilisateur)
            from datetime import timedelta
            _cutoff = utcnow() - timedelta(days=30)
            _today     = utcnow().date()
            _yesterday = _today - timedelta(days=1)

            def _date_label(dt):
                if dt is None:
                    return None
                d = dt.date() if hasattr(dt, 'date') else dt
                if d == _today:
                    return "Aujourd'hui"
                if d == _yesterday:
                    return "Hier"
                if (_today - d).days <= 7:
                    return "Cette semaine"
                return d.strftime('%d/%m/%Y')

            broadcast_notifications = [
                {
                    "id": n.id,
                    "title": n.title,
                    "message": n.message,
                    "level": n.level or "info",
                    "created_at": n.created_at,
                    "date_label": _date_label(n.created_at),
                }
                for n in Notification.query.filter(
                    Notification.audience == "global",
                    Notification.created_at >= _cutoff,
                ).order_by(Notification.created_at.desc()).limit(20).all()
            ]

        return {
            "header_notifications": notifications,
            "header_unread_notifications": unread_count,
            "current_year": utcnow().year,
            "is_admin": current_user.is_authenticated and getattr(current_user, "role", None) == "admin",
            "admin_pending_tasks": admin_pending_tasks,
            "broadcast_notifications": broadcast_notifications,
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


    with app.app_context():
        from . import seed
        
        # Vérifier que la base de données peut être créée/ouverte avant de continuer
        db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        
        if db_uri.startswith("sqlite:///"):
            db_file_path = db_uri.replace("sqlite:///", "")
            db_file = Path(db_file_path)
            
            # S'assurer que le répertoire parent existe
            try:
                db_file.parent.mkdir(parents=True, exist_ok=True)
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
                # Utiliser le chemin absolu résolu pour le test
                db_file_abs = db_file.resolve()
                test_conn = sqlite3.connect(str(db_file_abs), timeout=10.0)
                # Tester une écriture pour vérifier les permissions
                test_conn.execute("CREATE TABLE IF NOT EXISTS _test_write (id INTEGER PRIMARY KEY)")
                test_conn.execute("DROP TABLE IF EXISTS _test_write")
                test_conn.commit()
                test_conn.close()
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

            # Migration de la table user
            user_cols = {
                row[1]
                for row in db.session.execute(text("PRAGMA table_info(user)"))
            }
            
            migrations_applied = []
            
            if "last_login" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN last_login DATETIME")
                )
                db.session.commit()
                migrations_applied.append("last_login")
            
            if "avatar_filename" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN avatar_filename VARCHAR(255)")
                )
                db.session.commit()
                migrations_applied.append("avatar_filename")
            
            if "twofa_enabled" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN twofa_enabled BOOLEAN DEFAULT 0")
                )
                db.session.commit()
                migrations_applied.append("twofa_enabled")
            
            if "twofa_code_hash" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN twofa_code_hash VARCHAR(255)")
                )
                db.session.commit()
                migrations_applied.append("twofa_code_hash")
            
            if "twofa_code_sent_at" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN twofa_code_sent_at DATETIME")
                )
                db.session.commit()
                migrations_applied.append("twofa_code_sent_at")
            
            if "twofa_trusted_token_hash" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN twofa_trusted_token_hash VARCHAR(255)")
                )
                db.session.commit()
                migrations_applied.append("twofa_trusted_token_hash")
            
            if "twofa_trusted_created_at" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN twofa_trusted_created_at DATETIME")
                )
                db.session.commit()
                migrations_applied.append("twofa_trusted_created_at")
            
            if "address" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN address VARCHAR(255)")
                )
                db.session.commit()
                migrations_applied.append("address")
            
            if "street" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN street VARCHAR(255)")
                )
                db.session.commit()
                migrations_applied.append("street")
            
            if "postal_code" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN postal_code VARCHAR(20)")
                )
                db.session.commit()
                migrations_applied.append("postal_code")
            
            if "city_country" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN city_country VARCHAR(255)")
                )
                db.session.commit()
                migrations_applied.append("city_country")
            
            if "city" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN city VARCHAR(255)")
                )
                db.session.commit()
                migrations_applied.append("city")
            
            if "country" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN country VARCHAR(255)")
                )
                db.session.commit()
                migrations_applied.append("country")
            
            if "phone" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN phone VARCHAR(50)")
                )
                db.session.commit()
                migrations_applied.append("phone")
            
            if "first_name" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN first_name VARCHAR(100)")
                )
                db.session.commit()
                migrations_applied.append("first_name")
            
            if "last_name" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN last_name VARCHAR(100)")
                )
                db.session.commit()
                migrations_applied.append("last_name")
            
            if "title" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN title VARCHAR(20)")
                )
                db.session.commit()
                migrations_applied.append("title")
            
            if "reset_token_hash" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN reset_token_hash VARCHAR(255)")
                )
                db.session.commit()
                migrations_applied.append("reset_token_hash")
            
            if "reset_token_expires" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN reset_token_expires DATETIME")
                )
                db.session.commit()
                migrations_applied.append("reset_token_expires")
            
            # Champs professionnels
            if "date_of_birth" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN date_of_birth DATE")
                )
                db.session.commit()
                migrations_applied.append("date_of_birth")
            
            if "bio" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN bio TEXT")
                )
                db.session.commit()
                migrations_applied.append("bio")
            
            if "company" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN company VARCHAR(255)")
                )
                db.session.commit()
                migrations_applied.append("company")
            
            if "job_title" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN job_title VARCHAR(255)")
                )
                db.session.commit()
                migrations_applied.append("job_title")
            
            if "website" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN website VARCHAR(255)")
                )
                db.session.commit()
                migrations_applied.append("website")
            
            if "linkedin" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN linkedin VARCHAR(255)")
                )
                db.session.commit()
                migrations_applied.append("linkedin")
            
            # Nouveaux champs pour séparation personnel/professionnel
            if "phone_mobile" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN phone_mobile VARCHAR(50)")
                )
                db.session.commit()
                migrations_applied.append("phone_mobile")
            
            if "email_professional" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN email_professional VARCHAR(120)")
                )
                db.session.commit()
                migrations_applied.append("email_professional")
            
            if "street_professional" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN street_professional VARCHAR(255)")
                )
                db.session.commit()
                migrations_applied.append("street_professional")
            
            if "postal_code_professional" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN postal_code_professional VARCHAR(20)")
                )
                db.session.commit()
                migrations_applied.append("postal_code_professional")
            
            if "city_professional" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN city_professional VARCHAR(255)")
                )
                db.session.commit()
                migrations_applied.append("city_professional")
            
            if "country_professional" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN country_professional VARCHAR(255)")
                )
                db.session.commit()
                migrations_applied.append("country_professional")
            
            if "phone_professional" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN phone_professional VARCHAR(50)")
                )
                db.session.commit()
                migrations_applied.append("phone_professional")
            
            # Migrations appliquées silencieusement (pas de log pour éviter le spam CLI)
        except Exception as exc:  # pragma: no cover - dépend de l'état SQLite
            app.logger.warning("Impossible de vérifier les schémas SQLite: %s", exc)
        seed.ensure_default_admin()
        
        # Enregistrer les commandes CLI
        from . import commands
        commands.register_commands(app)

    return app
