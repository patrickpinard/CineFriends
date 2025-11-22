from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Tuple

from flask import current_app
from sqlalchemy import or_

from app import db
from app.constants import METRIC_LABELS, SENSOR_HIGHLIGHT_DEFINITIONS
from app.hardware.gpio_controller import get_relay_states
from app.models import Setting, SensorReading

# Cache pour les settings (invalidé à chaque modification)
_settings_cache: dict[str, str | None] = {}
_settings_cache_timestamp: datetime | None = None


def get_setting_value(key: str, default: str) -> str:
    """Récupère une valeur de setting avec cache pour optimiser les performances"""
    global _settings_cache, _settings_cache_timestamp

    # Si le cache est vide ou expiré (plus de 5 minutes), on le rafraîchit
    now = datetime.utcnow()
    if (
        _settings_cache_timestamp is None
        or (now - _settings_cache_timestamp) > timedelta(minutes=5)
        or key not in _settings_cache
    ):
        setting = Setting.query.filter_by(key=key).first()
        value = setting.value if setting else None
        _settings_cache[key] = value
        _settings_cache_timestamp = now
        if value is None:
            return default
        return value

    return _settings_cache[key] or default


def invalidate_settings_cache():
    """Invalide le cache des settings (à appeler après modification)"""
    global _settings_cache, _settings_cache_timestamp
    _settings_cache = {}
    _settings_cache_timestamp = None


def get_sensor_display_name(sensor_type: str) -> str:
    if sensor_type == "ds18b20":
        return "Sonde Intérieure"
    if sensor_type == "am2315":
        return "Sonde Extérieure"
    return sensor_type.title()


def _build_sensor_highlight(
    *,
    sensor_type: str,
    metric: str,
    title: str,
    default_unit: str,
    icon: str,
    subtitle_key: str | None = None,
    subtitle: str | None = None,
) -> dict[str, Any]:
    # Récupérer la dernière lecture
    reading = (
        SensorReading.query.filter_by(sensor_type=sensor_type, metric=metric)
        .order_by(SensorReading.created_at.desc())
        .first()
    )

    value_display = "--"
    trend = "neutral"
    last_update = "Jamais"

    if reading:
        val = float(reading.value)
        value_display = f"{val:.1f}"
        
        # Calcul de la tendance (comparaison avec la moyenne des 3 dernières heures)
        three_hours_ago = datetime.utcnow() - timedelta(hours=3)
        past_readings = (
            SensorReading.query.filter(
                SensorReading.sensor_type == sensor_type,
                SensorReading.metric == metric,
                SensorReading.created_at >= three_hours_ago,
            )
            .order_by(SensorReading.created_at.desc())
            .limit(20)
            .all()
        )
        
        if len(past_readings) > 1:
            # Moyenne des lectures passées (excluant la toute dernière pour comparer)
            past_values = [float(r.value) for r in past_readings[1:]]
            if past_values:
                avg_past = sum(past_values) / len(past_values)
                diff = val - avg_past
                if diff > 0.2:
                    trend = "up"
                elif diff < -0.2:
                    trend = "down"

        # Formatage du temps écoulé
        delta = datetime.utcnow() - reading.created_at
        if delta.total_seconds() < 60:
            last_update = "À l'instant"
        elif delta.total_seconds() < 3600:
            minutes = int(delta.total_seconds() / 60)
            last_update = f"Il y a {minutes} min"
        else:
            hours = int(delta.total_seconds() / 3600)
            last_update = f"Il y a {hours} h"

    # Gestion du sous-titre (soit une clé de config, soit une valeur directe)
    final_subtitle = subtitle
    if not final_subtitle and subtitle_key:
        # On pourrait récupérer ici un nom personnalisé depuis les settings si nécessaire
        # Pour l'instant on utilise le nom par défaut
        final_subtitle = get_sensor_display_name(sensor_type)

    return {
        "id": f"{sensor_type}_{metric}",
        "title": title,
        "subtitle": final_subtitle,
        "value": value_display,
        "unit": default_unit,
        "icon": icon,
        "trend": trend,
        "last_update": last_update,
        "sensor_type": sensor_type,
        "metric": metric,
    }


def _get_sensor_highlights() -> list[dict[str, Any]]:
    highlights = []
    for definition in SENSOR_HIGHLIGHT_DEFINITIONS:
        highlights.append(_build_sensor_highlight(**definition))
    return highlights


def _extract_relay_action_description(line: str) -> str:
    """Convertit une ligne de commande (ex: 'ch1:on') en description lisible."""
    line = line.strip().lower()
    parts = line.split(":")
    if len(parts) != 2:
        return line
    channel_part, command = parts
    try:
        channel = int(channel_part.replace("ch", ""))
    except ValueError:
        return line
    
    command_map = {"on": "Activer", "off": "Désactiver", "toggle": "Basculer"}
    action = command_map.get(command, command)
    return f"{action} Relais {channel}"


def _collect_relay_states_with_fallback(relay_pins: dict[int, int]) -> dict[int, str]:
    """Récupère l'état des relais, avec fallback sur la base de données si le matériel est inaccessible."""
    # 1. Essayer de lire le matériel
    hw_states = get_relay_states(relay_pins)
    
    # 2. Si le matériel répond, mettre à jour la DB (cache) et retourner
    # Note: get_relay_states retourne "unknown" si échec
    
    # Pour l'instant, on retourne simplement ce que le contrôleur nous donne.
    # Le contrôleur gère déjà la simulation si configuré.
    return hw_states


def _sync_runtime_device_flags(statuses: list[dict[str, Any]]):
    """Met à jour les statuts matériels avec les flags globaux de l'application (config)."""
    for status in statuses:
        if status["id"] == "lcd":
            if not current_app.config.get("LCD_ENABLED"):
                status["status"] = "warning"
                status["message"] = "Désactivé dans la configuration (LCD_ENABLED=False)."


def _build_sensor_registry() -> dict[str, dict[str, object]]:
    """Construit un registre des capteurs disponibles pour les formulaires."""
    registry = {}
    
    # DS18B20
    registry["ds18b20"] = {
        "label": "Sonde Intérieure (DS18B20)",
        "metrics": [{"value": "temperature", "label": "Température (°C)"}],
        "ids": [],  # À remplir dynamiquement si on gère plusieurs sondes
    }
    
    # AM2315
    registry["am2315"] = {
        "label": "Sonde Extérieure (AM2315)",
        "metrics": [
            {"value": "temperature", "label": "Température (°C)"},
            {"value": "humidity", "label": "Humidité (%)"},
        ],
        "ids": [],
    }
    
    return registry


def _hydrate_rule_form(form, sensor_registry: dict[str, dict[str, object]], relay_pins: dict[int, int]):
    """Remplit les choix dynamiques du formulaire de règles."""
    # Choix des capteurs
    sensor_choices = []
    for key, data in sensor_registry.items():
        sensor_choices.append((key, data["label"]))  # type: ignore
    form.sensor_type.choices = sensor_choices

    # Choix des métriques (union de toutes les métriques possibles)
    # Idéalement, cela devrait être dynamique via JS, mais on met tout pour le backend
    metric_choices = set()
    for data in sensor_registry.values():
        for m in data["metrics"]:  # type: ignore
            metric_choices.add((m["value"], m["label"]))
    form.sensor_metric.choices = list(metric_choices)

    # Choix des relais
    relay_choices = []
    for channel in sorted(relay_pins.keys()):
        relay_choices.append((channel, f"Relais {channel}"))
    form.relay_channel.choices = relay_choices


def build_trigger_expression(sensor_type: str, metric: str, sensor_id: str | None, operator: str, threshold) -> str:
    """Construit la chaîne de déclencheur stockée en base."""
    # Format: type:metric:id operator threshold
    # Ex: ds18b20:temperature:None > 25.5
    s_id = sensor_id if sensor_id else "any"
    return f"{sensor_type}:{metric}:{s_id} {operator} {threshold}"


def build_action_expression(
    channel: int | None,
    command: str | None,
    *,
    relay_enabled: bool,
    notify_user_id: int | None,
) -> str:
    """Construit la chaîne d'action stockée en base."""
    actions = []
    if relay_enabled and channel and command:
        actions.append(f"relay:{channel}:{command}")
    
    if notify_user_id:
        actions.append(f"email:{notify_user_id}")
        
    return ";".join(actions)


def parse_relay_action(action: str) -> Tuple[int | None, str | None]:
    """Extrait la commande relais d'une chaîne d'action."""
    if not action:
        return None, None
    parts = action.split(";")
    for part in parts:
        if part.startswith("relay:"):
            # relay:channel:command
            try:
                _, channel, command = part.split(":")
                return int(channel), command
            except ValueError:
                continue
    return None, None


def parse_email_action(action: str) -> int | None:
    """Extrait l'ID utilisateur pour notification d'une chaîne d'action."""
    if not action:
        return None
    parts = action.split(";")
    for part in parts:
        if part.startswith("email:"):
            try:
                _, user_id = part.split(":")
                return int(user_id)
            except ValueError:
                continue
    return None
