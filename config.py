"""
Fichier : config.py
Objectif : Centraliser la configuration Flask de l’application Dashboard via la
           classe `Config`.
Contenu principal :
    - Chargement des variables d’environnement (.env) et valeurs par défaut.
    - Définition des paramètres de sécurité, base de données, email, capteurs.
    - Exposition des chemins de travail (uploads, base SQLite locale).
"""

import os
from pathlib import Path

from dotenv import load_dotenv


class Config:
    BASE_DIR = Path(__file__).resolve().parent
    load_dotenv(BASE_DIR / ".env")

    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "change-this-secret-key")
    SQLALCHEMY_DATABASE_URI = (
        os.getenv("DATABASE_URL")
        or f"sqlite:///{BASE_DIR / 'dashboard.db'}"
    )
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

    SENSOR_POLL_INTERVAL_MINUTES = int(os.getenv("SENSOR_POLL_INTERVAL_MINUTES", "5"))
    SENSOR_POLL_ENABLED = os.getenv("SENSOR_POLL_ENABLED", "true").lower() == "true"
