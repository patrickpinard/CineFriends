"""
Configuration de l'application avec support multi-environnements.

Ce module définit les classes de configuration pour différents environnements
(development, testing, production) et fournit une fonction pour obtenir
la configuration appropriée selon la variable d'environnement FLASK_ENV.
"""

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv


class Config:
    """
    Configuration de base partagée par tous les environnements.
    
    Cette classe contient les paramètres communs à tous les environnements.
    Les classes spécifiques (DevelopmentConfig, ProductionConfig, etc.)
    héritent de cette classe et peuvent surcharger ou ajouter des paramètres.
    """
    
    BASE_DIR = Path(__file__).resolve().parent
    load_dotenv(BASE_DIR / ".env")

    # Application
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "change-this-secret-key")
    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    
    # Base de données
    INSTANCE_DIR = BASE_DIR / "instance"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False  # Log des requêtes SQL (dev uniquement)
    
    # Sécurité
    WTF_CSRF_TIME_LIMIT = None
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    PREFERRED_URL_SCHEME = "https"
    
    # Uploads avatars
    UPLOAD_FOLDER = str(BASE_DIR / "app" / "static" / "uploads")
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 15 * 1024 * 1024 * 1024))  # 15 GB (films)
    MAX_AVATAR_SIZE = int(os.getenv("MAX_AVATAR_SIZE", 2 * 1024 * 1024))

    # Médiathèque (films)
    MOVIES_FOLDER = str(BASE_DIR / "films")

    # TMDB API
    TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
    TMDB_LANGUAGE = os.getenv("TMDB_LANGUAGE", "fr-FR")
    
    # 2FA
    TWOFA_CODE_LENGTH = int(os.getenv("TWOFA_CODE_LENGTH", "6"))
    TWOFA_CODE_TTL_SECONDS = int(os.getenv("TWOFA_CODE_TTL_SECONDS", "300"))
    TWOFA_RESEND_INTERVAL_SECONDS = int(os.getenv("TWOFA_RESEND_INTERVAL_SECONDS", "60"))
    TWOFA_REMEMBER_DAYS = int(os.getenv("TWOFA_REMEMBER_DAYS", "30"))
    TWOFA_REMEMBER_COOKIE = os.getenv("TWOFA_REMEMBER_COOKIE", "templateapp_trusted_device")
    
    # Email
    MAIL_SERVER = os.getenv("MAIL_SERVER", "")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USE_SSL = os.getenv("MAIL_USE_SSL", "false").lower() == "true"
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", MAIL_USERNAME)
    ADMIN_NOTIFICATION_EMAIL = os.getenv("ADMIN_NOTIFICATION_EMAIL", "")
    MAIL_MONITOR_ADDRESS = os.getenv("MAIL_MONITOR_ADDRESS", "")
    
    # CORS
    CORS_ORIGINS = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin.strip()]
    
    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", "logs/app.log")
    
    # Cache
    CACHE_TYPE = os.getenv("CACHE_TYPE", "simple")
    CACHE_REDIS_URL = os.getenv("CACHE_REDIS_URL", None)
    
    @property
    def SQLALCHEMY_DATABASE_URI(self):
        """
        Construit l'URI de la base de données.
        
        Si DATABASE_URL est défini dans .env, l'utilise.
        Sinon, utilise SQLite dans le dossier instance.
        """
        db_uri = os.getenv("DATABASE_URL")
        if db_uri:
            return db_uri
        
        # SQLite par défaut
        try:
            self.INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
            if not os.access(self.INSTANCE_DIR, os.W_OK):
                raise PermissionError(f"Le dossier {self.INSTANCE_DIR} n'est pas accessible en écriture")
        except Exception as e:
            import logging
            logging.warning(f"Impossible de créer le dossier instance: {e}. Utilisation du dossier de base.")
            self.INSTANCE_DIR = self.BASE_DIR
        
        db_path = self.INSTANCE_DIR / "database.db"
        db_path_absolute = db_path.resolve()
        db_path_str = str(db_path_absolute).replace("\\", "/")
        return f"sqlite:////{db_path_str}"
    
    @staticmethod
    def init_app(app):
        """Initialisation spécifique à l'application."""
        pass


class DevelopmentConfig(Config):
    """Configuration pour le développement."""
    DEBUG = True
    TESTING = False
    
    # Logs SQL en développement (désactivé pour réduire le bruit dans les logs)
    SQLALCHEMY_ECHO = False
    
    # Cookies non sécurisés en dev
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False


class TestingConfig(Config):
    """Configuration pour les tests."""
    TESTING = True
    DEBUG = True
    
    # Base de données en mémoire pour les tests
    @property
    def SQLALCHEMY_DATABASE_URI(self):
        return "sqlite:///:memory:"
    
    # Désactiver CSRF pour les tests
    WTF_CSRF_ENABLED = False
    
    # Pas de sécurité des cookies en test
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False


class ProductionConfig(Config):
    """Configuration pour la production."""
    DEBUG = False
    TESTING = False
    
    # Sécurité renforcée en production
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    
    # Pas de logs SQL en production
    SQLALCHEMY_ECHO = False
    
    @property
    def SQLALCHEMY_DATABASE_URI(self):
        """En production, DATABASE_URL doit être défini."""
        db_uri = os.getenv("DATABASE_URL")
        if not db_uri:
            raise ValueError("DATABASE_URL doit être défini en production")
        return db_uri
    
    @staticmethod
    def init_app(app):
        """Initialisation spécifique à la production."""
        Config.init_app(app)
        
        # Logging vers syslog en production (optionnel)
        import logging
        from logging.handlers import SysLogHandler
        
        if os.getenv("SYSLOG_ADDRESS"):
            syslog_handler = SysLogHandler(address=os.getenv("SYSLOG_ADDRESS"))
            syslog_handler.setLevel(logging.WARNING)
            app.logger.addHandler(syslog_handler)


# Dictionnaire de configuration
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}


def get_config():
    """
    Retourne la classe de configuration selon l'environnement.
    
    Returns:
        Classe de configuration (DevelopmentConfig, TestingConfig, ou ProductionConfig)
    """
    env = os.getenv("FLASK_ENV", "development")
    return config.get(env, config['default'])

