"""
Fichier : app/seed.py
Objectif : Fournir des opérations d’amorçage de la base de données (création de
           l’administrateur par défaut).
Fonctionnalités clés :
    - `ensure_default_admin` : crée un compte admin si inexistant avec mot de passe initial.
Dépendances critiques : modèles `User`, session SQLAlchemy.
"""

from .models import User
from . import db


def ensure_default_admin() -> None:
    if not User.query.filter_by(username="admin").first():
        admin = User(username="admin", role="admin", active=True)
        admin.set_password("admin")
        db.session.add(admin)
        db.session.commit()
