import os
from pathlib import Path

from dotenv import load_dotenv


class Config:
    BASE_DIR = Path(__file__).resolve().parent
    load_dotenv(BASE_DIR / ".env")

    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "change-this-secret-key")
    
    # Définir le chemin du dossier instance
    INSTANCE_DIR = BASE_DIR / "instance"
    
    # Construire l'URI de la base de données
    # Si DATABASE_URL est défini dans .env, l'utiliser, sinon utiliser instance/dashboard.db
    _db_uri = os.getenv("DATABASE_URL")
    if not _db_uri:
        # S'assurer que le dossier instance existe avec les bonnes permissions
        try:
            INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
            # Vérifier que le dossier est accessible en écriture
            if not os.access(INSTANCE_DIR, os.W_OK):
                raise PermissionError(f"Le dossier {INSTANCE_DIR} n'est pas accessible en écriture")
        except Exception as e:
            # En cas d'erreur, utiliser le dossier de base comme fallback
            import logging
            logging.warning(f"Impossible de créer le dossier instance: {e}. Utilisation du dossier de base.")
            INSTANCE_DIR = BASE_DIR
        
        # Utiliser un chemin absolu avec le format SQLite correct
        db_path = INSTANCE_DIR / "dashboard.db"
        db_path_absolute = db_path.resolve()
        db_path_str = str(db_path_absolute)
        
        # Normaliser les slashes pour Unix/Linux
        db_path_str = db_path_str.replace("\\", "/")
        
        # Pour SQLAlchemy avec SQLite, utiliser le format avec 4 slashes pour les chemins absolus
        # Format: sqlite:////chemin/absolu/vers/fichier.db
        # Alternative: utiliser sqlite+pysqlite3://// pour forcer l'utilisation de pysqlite3
        # Mais d'abord, essayons avec le format standard
        SQLALCHEMY_DATABASE_URI = f"sqlite:////{db_path_str}"
        
        # Si le format avec 4 slashes ne fonctionne pas, SQLAlchemy peut aussi accepter
        # le format avec 3 slashes si on utilise un chemin relatif depuis le répertoire de travail
        # Mais nous préférons le chemin absolu pour éviter les problèmes de répertoire de travail
    else:
        SQLALCHEMY_DATABASE_URI = _db_uri
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_TIME_LIMIT = None
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False
    PREFERRED_URL_SCHEME = "https"
    UPLOAD_FOLDER = str(BASE_DIR / "app" / "static" / "uploads")
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 5 * 1024 * 1024))
    TWOFA_CODE_LENGTH = int(os.getenv("TWOFA_CODE_LENGTH", "6"))
    TWOFA_CODE_TTL_SECONDS = int(os.getenv("TWOFA_CODE_TTL_SECONDS", "300"))
    TWOFA_RESEND_INTERVAL_SECONDS = int(os.getenv("TWOFA_RESEND_INTERVAL_SECONDS", "60"))
    TWOFA_REMEMBER_DAYS = int(os.getenv("TWOFA_REMEMBER_DAYS", "30"))
    TWOFA_REMEMBER_COOKIE = os.getenv("TWOFA_REMEMBER_COOKIE", "dashboard_trusted_device")

    MAIL_SERVER = os.getenv("MAIL_SERVER", "")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USE_SSL = os.getenv("MAIL_USE_SSL", "false").lower() == "true"
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", MAIL_USERNAME)
    ADMIN_NOTIFICATION_EMAIL = os.getenv("ADMIN_NOTIFICATION_EMAIL", "")
    MAIL_MONITOR_ADDRESS = os.getenv("MAIL_MONITOR_ADDRESS", "")

    SENSOR_POLL_INTERVAL_MINUTES = int(os.getenv("SENSOR_POLL_INTERVAL_MINUTES", "30"))
    SENSOR_POLL_ENABLED = os.getenv("SENSOR_POLL_ENABLED", "true").lower() == "true"
    LCD_ENABLED = os.getenv("LCD_ENABLED", "true").lower() == "true"
    CAMERA_DEVICE_INDEX = int(os.getenv("CAMERA_DEVICE_INDEX", "0"))
