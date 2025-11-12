"""
Fichier : app/services.py
Objectif : Fournir des helpers métiers partagés, principalement autour des
           notifications envoyées aux utilisateurs/administrateurs.
Fonctionnalités clés :
    - Création standardisée d’objets `Notification`.
    - Diffusion des notifications à tous les admins via `notify_admins`.
Dépendances critiques : modèles `Notification` et `User`, base de données.
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

