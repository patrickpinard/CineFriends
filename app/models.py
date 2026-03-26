"""
Modèles de données SQLAlchemy pour l'application TemplateApp.

Ce module définit tous les modèles de données utilisés dans l'application,
incluant les utilisateurs, les paramètres et les notifications.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from . import db, login_manager


def utcnow() -> datetime:
    """Retourne la date/heure UTC actuelle (remplace datetime.utcnow() déprécié)."""
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    """
    Modèle représentant un utilisateur du système.
    
    Hérite de UserMixin pour la compatibilité avec Flask-Login.
    Gère l'authentification, les informations personnelles, l'adresse,
    et la double authentification (2FA).
    
    Attributes:
        id (int): Identifiant unique de l'utilisateur (clé primaire).
        title (str): Civilité de l'utilisateur (Monsieur/Madame), optionnel.
        first_name (str): Prénom de l'utilisateur, optionnel.
        last_name (str): Nom de famille de l'utilisateur, optionnel.
        username (str): Nom d'utilisateur unique, requis.
        email (str): Adresse email unique, optionnelle.
        role (str): Rôle de l'utilisateur ('admin' ou 'user'), défaut: 'user'.
        password_hash (str): Hash du mot de passe (PBKDF2-SHA256), requis.
        active (bool): Statut actif/inactif du compte, défaut: True.
        created_at (datetime): Date et heure de création du compte.
        last_login (datetime): Date et heure de la dernière connexion, optionnel.
        avatar_filename (str): Nom du fichier avatar, optionnel.
        address (str): Ancien champ d'adresse, conservé pour compatibilité.
        street (str): Rue de l'adresse, optionnel.
        postal_code (str): Code postal, optionnel.
        city_country (str): Ancien champ ville/pays, conservé pour compatibilité.
        city (str): Ville de l'adresse, optionnel.
        country (str): Pays de l'adresse, optionnel.
        phone (str): Numéro de téléphone, optionnel.
        twofa_enabled (bool): Double authentification activée, défaut: False.
        twofa_code_hash (str): Hash du code 2FA, optionnel.
        twofa_code_sent_at (datetime): Date d'envoi du code 2FA, optionnel.
        twofa_trusted_token_hash (str): Hash du token de confiance 2FA, optionnel.
        twofa_trusted_created_at (datetime): Date de création du token de confiance, optionnel.
        reset_token_hash (str): Hash du token de réinitialisation de mot de passe, optionnel.
        reset_token_expires (datetime): Date d'expiration du token de réinitialisation, optionnel.
    
    Methods:
        set_password(password: str): Hash et définit le mot de passe.
        check_password(password: str): Vérifie si le mot de passe correspond.
        is_active(): Retourne le statut actif du compte.
    """
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(20), nullable=True)  # Monsieur/Madame
    first_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    role = db.Column(db.String(20), default="user")
    password_hash = db.Column(db.String(255), nullable=False)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    last_login = db.Column(db.DateTime, nullable=True)
    avatar_filename = db.Column(db.String(255), nullable=True)
    address = db.Column(db.String(255), nullable=True)  # Ancien champ, conservé pour compatibilité
    street = db.Column(db.String(255), nullable=True)  # Adresse privée
    postal_code = db.Column(db.String(20), nullable=True)  # Adresse privée
    city_country = db.Column(db.String(255), nullable=True)  # Ancien champ, conservé pour compatibilité
    city = db.Column(db.String(255), nullable=True)  # Adresse privée
    country = db.Column(db.String(255), nullable=True)  # Adresse privée
    phone = db.Column(db.String(50), nullable=True)  # Téléphone fixe privé
    phone_mobile = db.Column(db.String(50), nullable=True)  # Téléphone mobile privé
    # Champs professionnels
    date_of_birth = db.Column(db.Date, nullable=True)
    bio = db.Column(db.Text, nullable=True)
    company = db.Column(db.String(255), nullable=True)
    job_title = db.Column(db.String(255), nullable=True)
    email_professional = db.Column(db.String(120), nullable=True)  # Email professionnel
    street_professional = db.Column(db.String(255), nullable=True)  # Adresse professionnelle
    postal_code_professional = db.Column(db.String(20), nullable=True)  # Code postal professionnel
    city_professional = db.Column(db.String(255), nullable=True)  # Ville professionnelle
    country_professional = db.Column(db.String(255), nullable=True)  # Pays professionnel
    phone_professional = db.Column(db.String(50), nullable=True)  # Téléphone professionnel
    website = db.Column(db.String(255), nullable=True)
    linkedin = db.Column(db.String(255), nullable=True)
    twofa_enabled = db.Column(db.Boolean, default=False)
    twofa_code_hash = db.Column(db.String(255), nullable=True)
    twofa_code_sent_at = db.Column(db.DateTime, nullable=True)
    twofa_trusted_token_hash = db.Column(db.String(255), nullable=True)
    twofa_trusted_created_at = db.Column(db.DateTime, nullable=True)
    reset_token_hash = db.Column(db.String(255), nullable=True)
    reset_token_expires = db.Column(db.DateTime, nullable=True)

    def set_password(self, password: str) -> None:
        """
        Hash et définit le mot de passe de l'utilisateur.
        
        Utilise PBKDF2-SHA256 pour le hachage sécurisé du mot de passe.
        
        Args:
            password: Mot de passe en clair à hasher.
        """
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password: str) -> bool:
        """
        Vérifie si le mot de passe fourni correspond au hash stocké.
        
        Args:
            password: Mot de passe en clair à vérifier.
        
        Returns:
            True si le mot de passe correspond, False sinon.
        """
        return check_password_hash(self.password_hash, password)

    def is_active(self) -> bool:  # type: ignore[override]
        """
        Vérifie si le compte utilisateur est actif.
        
        Nécessaire pour Flask-Login.
        
        Returns:
            True si le compte est actif, False sinon.
        """
        return self.active


@login_manager.user_loader
def load_user(user_id: str) -> Optional[User]:
    """
    Charge un utilisateur depuis la base de données pour Flask-Login.
    
    Args:
        user_id: Identifiant de l'utilisateur (chaîne).
    
    Returns:
        Instance User si trouvé, None sinon.
    """
    return User.query.get(int(user_id))


class Setting(db.Model):
    """
    Modèle représentant un paramètre de configuration du système.
    
    Permet de stocker des paramètres configurables de manière dynamique
    sans modifier le code.
    
    Attributes:
        id (int): Identifiant unique du paramètre (clé primaire).
        key (str): Clé unique du paramètre, requis.
        value (str): Valeur du paramètre, optionnelle.
        updated_at (datetime): Date et heure de dernière mise à jour.
    """
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(120), unique=True, nullable=False)
    value = db.Column(db.String(255), nullable=True)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)


class Notification(db.Model):
    """
    Modèle représentant une notification pour les utilisateurs.
    
    Permet d'afficher des notifications dans l'interface utilisateur.
    
    Attributes:
        id (int): Identifiant unique de la notification (clé primaire).
        user_id (int): Identifiant de l'utilisateur destinataire (FK vers User), optionnel.
        audience (str): Audience de la notification ('user', 'admin', 'global'), défaut: 'user'.
        level (str): Niveau de la notification ('info', 'warning', 'error'), défaut: 'info'.
        title (str): Titre de la notification, requis.
        message (str): Message de la notification, requis.
        action_url (str): URL d'action associée, optionnelle.
        created_at (datetime): Date et heure de création de la notification.
        read (bool): Notification lue/non lue, défaut: False.
        persistent (bool): Notification persistante (ne peut pas être supprimée), défaut: False.
        user (User): Relation vers l'utilisateur destinataire (via backref).
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    audience = db.Column(db.String(50), default="user")  # user, admin, global
    level = db.Column(db.String(20), default="info")
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    action_url = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    read = db.Column(db.Boolean, default=False)
    persistent = db.Column(db.Boolean, default=False)

    user = db.relationship("User", backref=db.backref("notifications", lazy=True))
