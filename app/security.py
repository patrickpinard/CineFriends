"""
Configuration de la sécurité HTTP pour TemplateApp.

Ce module centralise la configuration de Flask-CORS et Flask-Talisman
(headers CSP, HSTS, etc.) qui était auparavant inline dans create_app().
"""

from flask import Flask
from flask_cors import CORS
from flask_talisman import Talisman

_CORS_SETTINGS = {
    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    "allow_headers": ["Content-Type", "Authorization", "X-CSRFToken", "X-Requested-With"],
    "supports_credentials": True,
}

_CSP = {
    "default-src": "'self'",
    "script-src": "'self' 'unsafe-inline'",
    "style-src": "'self' 'unsafe-inline'",
    "img-src": "'self' data: https:",
    "font-src": "'self' data:",
}


def configure_security(app: Flask) -> None:
    """Configure CORS et les headers de sécurité HTTP (Talisman)."""
    _configure_cors(app)
    _configure_talisman(app)


def _configure_cors(app: Flask) -> None:
    cors_origins = app.config.get("CORS_ORIGINS") or []
    origins = cors_origins if cors_origins else "*"
    CORS(app, resources={r"/*": {**_CORS_SETTINGS, "origins": origins}})


def _configure_talisman(app: Flask) -> None:
    Talisman(
        app,
        force_https=app.config.get("SESSION_COOKIE_SECURE", False),
        strict_transport_security=True,
        strict_transport_security_max_age=31536000,
        content_security_policy=_CSP,
        content_security_policy_nonce_in=["script-src", "style-src"],
    )
