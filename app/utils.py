"""
Module d'utilitaires pour l'application TemplateApp.

Ce module fournit des fonctions utilitaires pour :
- Conversion de dates/heures (UTC vers local)
- Gestion des avatars utilisateurs
- Construction de changements pour l'audit
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import current_app
from werkzeug.datastructures import FileStorage


def utcnow() -> datetime:
    """Retourne la date/heure UTC actuelle (remplace datetime.utcnow() déprécié)."""
    return datetime.now(timezone.utc)


def utc_to_local(utc_dt: datetime) -> datetime:
    """
    Convertit un datetime UTC en datetime local du système.
    
    Calcule automatiquement l'offset entre UTC et l'heure locale du système,
    en tenant compte de l'heure d'été/hiver.
    
    Args:
        utc_dt: Datetime UTC à convertir. Peut être None.
    
    Returns:
        Datetime converti en heure locale, ou None si l'entrée est None.
    """
    if utc_dt is None:
        return utc_dt
    
    # Si le datetime est naive, on l'assume comme UTC
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    # Si le datetime a déjà un timezone, on le convertit en UTC d'abord
    elif utc_dt.tzinfo != timezone.utc:
        utc_dt = utc_dt.astimezone(timezone.utc)
    
    # Utiliser astimezone() sans argument pour convertir en heure locale du système
    # Cette méthode prend automatiquement en compte l'heure d'été/hiver
    local_dt = utc_dt.astimezone()
    return local_dt


def format_local_datetime(dt: datetime, format_str: str = "%d/%m/%Y %H:%M") -> str:
    """Formate un datetime UTC en heure locale du système
    
    Args:
        dt: datetime UTC à convertir
        format_str: Format de sortie (par défaut "%d/%m/%Y %H:%M")
    
    Returns:
        Chaîne formatée en heure locale
    """
    if dt is None:
        return ""
    local_dt = utc_to_local(dt)
    return local_dt.strftime(format_str)


def save_avatar(file: FileStorage) -> str:
    """
    Sauvegarde un fichier avatar uploadé par un utilisateur.
    
    Génère un nom de fichier unique avec un token aléatoire et conserve
    l'extension originale du fichier.
    
    Args:
        file: Fichier uploadé via Flask-WTF FileStorage.
    
    Returns:
        Nom du fichier sauvegardé (sans le chemin complet).
    
    Raises:
        OSError: Si le répertoire d'upload ne peut pas être créé ou
                 si le fichier ne peut pas être sauvegardé.
    """
    ext = Path(file.filename or "").suffix.lower()
    filename = f"avatar_{secrets.token_hex(8)}{ext}"
    upload_folder = Path(current_app.config["UPLOAD_FOLDER"])  # type: ignore[arg-type]
    upload_folder.mkdir(parents=True, exist_ok=True)
    destination = upload_folder / filename
    file.save(destination)
    return filename


def delete_avatar(filename: str | None) -> None:
    """
    Supprime un fichier avatar du système de fichiers.
    
    Args:
        filename: Nom du fichier avatar à supprimer. Si None, ne fait rien.
    
    Note:
        Les erreurs de suppression sont loggées mais n'interrompent pas l'exécution.
    """
    if not filename:
        return
    upload_folder = Path(current_app.config["UPLOAD_FOLDER"])
    filepath = upload_folder / filename
    try:
        if filepath.exists():
            filepath.unlink()
    except OSError:
        current_app.logger.warning("Impossible de supprimer l'avatar %s", filepath)


def serialize_value(value):
    """
    Sérialise une valeur Python en format JSON-compatible.
    
    Convertit les types spéciaux (datetime, date, bool, None) en formats
    sérialisables pour le stockage ou l'affichage.
    
    Args:
        value: Valeur à sérialiser (datetime, date, bool, None, ou autre).
    
    Returns:
        Valeur sérialisée (chaîne ISO pour dates, bool pour booléens,
        None pour None, str pour le reste).
    """
    from datetime import date
    
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return bool(value)
    if value is None:
        return None
    return str(value)


def build_changes(original: dict, updated: dict, fields: list[str]) -> dict:
    """
    Construit un dictionnaire des changements entre deux dictionnaires.
    
    Compare les valeurs des champs spécifiés entre deux dictionnaires
    et retourne uniquement les champs qui ont changé.
    
    Args:
        original: Dictionnaire avec les valeurs originales.
        updated: Dictionnaire avec les valeurs mises à jour.
        fields: Liste des noms de champs à comparer.
    
    Returns:
        Dictionnaire avec les champs modifiés, chaque entrée contenant :
        - 'before': Valeur avant modification
        - 'after': Valeur après modification
    """
    changes = {}
    for field in fields:
        before = serialize_value(original.get(field))
        after = serialize_value(updated.get(field))
        if before != after:
            changes[field] = {"before": before, "after": after}
    return changes
