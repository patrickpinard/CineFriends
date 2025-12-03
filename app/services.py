"""
Module de services pour les notifications de l'application TemplateApp.

Ce module fournit des fonctions utilitaires pour créer et gérer les notifications
utilisateur dans l'application. Les notifications peuvent être adressées à un
utilisateur spécifique, à tous les utilisateurs, ou uniquement aux administrateurs.

Fonctionnalités :
- Création de notifications avec différents niveaux (info, warning, error)
- Notifications personnelles, globales ou admin
- Notifications persistantes ou temporaires
- Génération automatique d'URLs d'action
- Notification automatique des administrateurs

Les notifications sont affichées dans l'interface utilisateur et peuvent être
marquées comme lues ou supprimées via les routes API.
"""

from __future__ import annotations

from flask import url_for

from . import db
from .models import Notification, User


def create_notification(
    *,
    title: str,
    message: str,
    level: str = "info",
    user: User | None = None,
    audience: str = "user",
    action_endpoint: str | None = None,
    action_kwargs: dict | None = None,
    persistent: bool = False,
) -> Notification:
    """
    Crée une notification dans la base de données.
    
    Cette fonction crée une nouvelle notification avec les paramètres spécifiés
    et la sauvegarde dans la base de données. La notification peut être adressée
    à un utilisateur spécifique ou à une audience (user, admin, global).
    
    Args:
        title: Titre de la notification (requis, max 150 caractères).
        message: Message de la notification (requis, texte libre).
        level: Niveau de la notification. Valeurs possibles :
            - "info" : Information générale (défaut)
            - "warning" : Avertissement
            - "error" : Erreur
        user: Utilisateur destinataire spécifique (optionnel).
            Si fourni, la notification est personnelle à cet utilisateur.
            Si None, la notification est adressée selon l'audience.
        audience: Audience de la notification (défaut: "user"). Valeurs possibles :
            - "user" : Notification pour tous les utilisateurs
            - "admin" : Notification uniquement pour les administrateurs
            - "global" : Notification globale visible par tous
        action_endpoint: Endpoint Flask pour l'action associée (optionnel).
            Exemple: "main.profile", "admin.users"
        action_kwargs: Arguments pour l'URL d'action (optionnel).
            Dictionnaire passé à url_for() pour construire l'URL.
            Exemple: {"user_id": 123}
        persistent: Notification persistante (défaut: False).
            Si True, la notification ne peut pas être supprimée par l'utilisateur
            et reste visible jusqu'à suppression manuelle par un admin.
    
    Returns:
        Notification: Instance de la notification créée et sauvegardée.
    
    Raises:
        SQLAlchemyError: En cas d'erreur lors de la sauvegarde en base de données.
    
    Exemples:
        # Notification personnelle
        create_notification(
            title="Bienvenue",
            message="Votre compte a été créé.",
            user=user,
            level="info"
        )
        
        # Notification globale avec action
        create_notification(
            title="Maintenance",
            message="Maintenance prévue ce soir.",
            audience="global",
            action_endpoint="main.settings",
            persistent=True
        )
        
        # Notification admin avec paramètres d'URL
        create_notification(
            title="Nouvel utilisateur",
            message="Un nouvel utilisateur s'est inscrit.",
            audience="admin",
            action_endpoint="admin.users",
            action_kwargs={"q": "nouveau"},
            level="info"
        )
    
    Note:
        - Si `user` est fourni, `audience` est ignoré (notification personnelle)
        - L'URL d'action est générée automatiquement si `action_endpoint` est fourni
        - La notification est immédiatement sauvegardée en base de données
    """
    notification = Notification(
        user=user,
        audience=audience,
        level=level,
        title=title,
        message=message,
        persistent=persistent,
    )
    if action_endpoint:
        notification.action_url = url_for(action_endpoint, **(action_kwargs or {}))
    db.session.add(notification)
    db.session.commit()
    return notification


def notify_admins(
    *,
    title: str,
    message: str,
    level: str = "info",
    action_endpoint: str | None = None,
    action_kwargs: dict | None = None,
    persistent: bool = True,
) -> Notification:
    """
    Crée une notification adressée à tous les administrateurs.
    
    Cette fonction est un raccourci pour créer une notification avec l'audience
    "admin". Par défaut, les notifications admin sont persistantes pour garantir
    qu'elles soient vues par tous les administrateurs.
    
    Args:
        title: Titre de la notification (requis).
        message: Message de la notification (requis).
        level: Niveau de la notification (défaut: "info").
            Valeurs: "info", "warning", "error"
        action_endpoint: Endpoint Flask pour l'action associée (optionnel).
        action_kwargs: Arguments pour l'URL d'action (optionnel).
        persistent: Notification persistante (défaut: True).
            Les notifications admin sont persistantes par défaut pour garantir
            leur visibilité.
    
    Returns:
        Notification: Instance de la notification créée et sauvegardée.
    
    Usage:
        Cette fonction est typiquement utilisée pour notifier les administrateurs
        d'événements importants comme :
        - Création/suppression d'utilisateurs
        - Modifications de configuration
        - Événements de sécurité
        - Erreurs système
    
    Exemples:
        # Notification simple
        notify_admins(
            title="Nouvel utilisateur",
            message="Un nouvel utilisateur s'est inscrit."
        )
        
        # Notification avec action
        notify_admins(
            title="Compte activé",
            message="Le compte utilisateur123 a été activé.",
            action_endpoint="admin.users",
            action_kwargs={"q": "utilisateur123"},
            level="info"
        )
        
        # Notification d'erreur persistante
        notify_admins(
            title="Erreur système",
            message="Une erreur critique s'est produite.",
            level="error",
            persistent=True
        )
    
    Note:
        Cette fonction appelle `create_notification()` avec `audience="admin"`.
        Les notifications admin sont visibles uniquement par les utilisateurs
        ayant le rôle "admin".
    """
    return create_notification(
        title=title,
        message=message,
        level=level,
        audience="admin",
        action_endpoint=action_endpoint,
        action_kwargs=action_kwargs,
        persistent=persistent,
    )

