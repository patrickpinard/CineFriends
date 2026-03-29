"""
Package de routes principales pour TemplateApp.

Blueprint : main_bp (sans préfixe d'URL)
Sous-modules :
  - dashboard   : pages du tableau de bord et journal
  - profile     : gestion du profil utilisateur
  - notifications : API notifications
  - pwa         : manifest, icônes, service-worker, health, erreurs
"""

from flask import Blueprint

main_bp = Blueprint("main", __name__)

# Les imports suivants enregistrent les routes sur main_bp — ordre sans importance
from . import dashboard, notifications, profile, pwa  # noqa: E402, F401
