from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Generator, Tuple, Optional, Union

from flask import (Blueprint, Response, current_app, flash, jsonify, redirect,
                   render_template, request, send_from_directory, url_for)
from flask_login import current_user, login_required
from sqlalchemy import func
from urllib.parse import urlencode

from . import db, schedule_sensor_poll, schedule_lcd_auto_scroll, invalidate_lcd_display_seconds_cache
from . import csrf
from .forms import AutomationRuleForm, ProfileForm, SettingForm
from .models import AutomationRule, JournalEntry, Notification, RelayState, SensorReading, Setting, User
from .services import create_notification
from .tasks import collect_sensor_readings
from .utils import build_changes, build_hardware_overview, delete_avatar, save_avatar, format_local_datetime, utc_to_local, utc_to_unix_ms_for_chart
from .automation_engine import parse_trigger
from .lcd_display import refresh_lcd_display
SENSOR_LABELS = {
    "ds18b20": "Sonde intérieure DS18B20",
    "am2315": "Sonde extérieure AM2315",
}

SENSOR_NAME_KEYS = {
    "ds18b20": "Sensor_Name_DS18B20",
    "am2315": "Sensor_Name_AM2315",
}

RELAY_NAME_KEYS = {
    1: "Relay_Name_Ch1",
    2: "Relay_Name_Ch2",
    3: "Relay_Name_Ch3",
}

METRIC_LABELS = {
    "temperature": "Température",
    "humidity": "Humidité",
}

SENSOR_HIGHLIGHT_DEFINITIONS = [
    {
        "sensor_type": "ds18b20",
        "metric": "temperature",
        "title": "Température DS18B20",
        "subtitle_key": "ds18b20",
        "default_unit": "°C",
        "icon": "temperature",
    },
    {
        "sensor_type": "am2315",
        "metric": "temperature",
        "title": "Température AM2315",
        "subtitle_key": "am2315",
        "default_unit": "°C",
        "icon": "temperature",
    },
    {
        "sensor_type": "am2315",
        "metric": "humidity",
        "title": "Humidité AM2315",
        "subtitle_key": "am2315",
        "default_unit": "%",
        "icon": "humidity",
    },
]


# Cache pour les settings (invalidé à chaque modification)
_settings_cache: dict[str, Optional[str]] = {}
_settings_cache_timestamp: Optional[datetime] = None

def get_setting_value(key: str, default: str) -> str:
    """Récupère une valeur de setting avec cache pour optimiser les performances"""
    global _settings_cache, _settings_cache_timestamp
    
    # Invalider le cache après 5 minutes ou au premier appel
    now = datetime.utcnow()
    if _settings_cache_timestamp is None or (now - _settings_cache_timestamp).total_seconds() > 300:
        _settings_cache.clear()
        _settings_cache_timestamp = now
    
    # Vérifier le cache
    if key in _settings_cache:
        cached_value = _settings_cache[key]
        return cached_value if cached_value is not None else default
    
    # Requête DB si pas en cache
    setting = Setting.query.filter_by(key=key).first()
    value = setting.value if setting and setting.value else None
    _settings_cache[key] = value
    return value if value is not None else default


def invalidate_settings_cache() -> None:
    """Invalide le cache des settings (à appeler après modification)"""
    global _settings_cache, _settings_cache_timestamp
    _settings_cache.clear()
    _settings_cache_timestamp = None


def get_sensor_display_name(sensor_type: str) -> str:
    key = SENSOR_NAME_KEYS.get(sensor_type)
    default = SENSOR_LABELS.get(sensor_type, sensor_type.upper())
    if not key:
        return default
    return get_setting_value(key, default)


def _build_sensor_highlight(
    *,
    sensor_type: str,
    metric: str,
    title: str,
    default_unit: str,
    icon: str,
    subtitle_key: Optional[str] = None,
    subtitle: Optional[str] = None,
) -> dict[str, object]:
    subtitle_value = subtitle
    if subtitle_value is None and subtitle_key:
        subtitle_value = get_sensor_display_name(subtitle_key)

    reading = (
        SensorReading.query.filter(
            SensorReading.sensor_type == sensor_type,
            SensorReading.metric == metric,
        )
        .order_by(SensorReading.created_at.desc())
        .first()
    )
    card: dict[str, object] = {
        "key": f"{sensor_type}_{metric}",
        "sensor_type": sensor_type,
        "metric": metric,
        "title": title,
        "subtitle": subtitle_value,
        "icon": icon,
        "value": None,
        "unit": default_unit,
        "status": "error",
        "message": "Sonde non détectée ou aucune mesure disponible.",
        "last_seen_text": None,
        "last_seen_iso": None,
        "min_value": None,
        "max_value": None,
    }
    if reading and reading.value is not None:
        value = round(float(reading.value), 2)
        card["value"] = value
        card["unit"] = reading.unit or default_unit
        card["status"] = "ok"
        card["message"] = None
        card["last_seen_text"] = format_local_datetime(reading.created_at)
        card["last_seen_iso"] = reading.created_at.isoformat()
        if reading.sensor_id and not subtitle_value:
            card["subtitle"] = f"ID {reading.sensor_id.upper()}"

        window_start = datetime.utcnow() - timedelta(hours=24)
        stats = (
            db.session.query(
                func.min(SensorReading.value),
                func.max(SensorReading.value),
            )
            .filter(
                SensorReading.sensor_type == sensor_type,
                SensorReading.metric == metric,
                SensorReading.value.isnot(None),
                SensorReading.created_at >= window_start,
            )
            .first()
        )
        if stats:
            min_value, max_value = stats
            if min_value is not None:
                card["min_value"] = round(float(min_value), 2)
            if max_value is not None:
                card["max_value"] = round(float(max_value), 2)
    return card


def _get_sensor_highlights() -> list[dict[str, object]]:
    cards: list[dict[str, object]] = []
    for definition in SENSOR_HIGHLIGHT_DEFINITIONS:
        cards.append(_build_sensor_highlight(**definition))
    return cards


def _extract_relay_action_description(line: str) -> str:
    try:
        _, command = line.split(":", 1)
        channel_part, state_part = command.split("=", 1)
        channel = int(channel_part.strip())
        state = state_part.strip().lower()
        state_map = {"on": "Allumer", "off": "Éteindre", "toggle": "Basculer"}
        label = state_map.get(state, state.upper())
        # Utiliser le nom du relais au lieu du numéro
        relay_labels = get_relay_labels()
        relay_name = relay_labels.get(channel, f"Relais {channel}")
        return f"{relay_name} → {label}"
    except Exception:
        return line.strip()


def _format_action_text(action: str) -> str:
    """Formate le texte d'action en remplaçant les références de relais par leurs noms."""
    if not action or action.strip() == "noop":
        return "Aucune action programmée"
    
    relay_labels = get_relay_labels()
    lines = []
    for line in action.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        
        if line.lower().startswith("relay:"):
            try:
                _, command = line.split(":", 1)
                channel_part, state_part = command.split("=", 1)
                channel = int(channel_part.strip())
                state = state_part.strip().lower()
                state_map = {"on": "Allumer", "off": "Éteindre", "toggle": "Basculer"}
                label = state_map.get(state, state.upper())
                relay_name = relay_labels.get(channel, f"Relais {channel}")
                lines.append(f"{relay_name} → {label}")
            except Exception:
                lines.append(line)
        elif line.lower().startswith("email:"):
            try:
                _, command = line.split(":", 1)
                if "=" in command:
                    user_part, user_id = command.split("=", 1)
                    if user_part.strip() == "user":
                        from .models import User
                        user = User.query.get(int(user_id.strip()))
                        if user:
                            lines.append(f"Email → {user.username}")
                        else:
                            lines.append(line)
                    else:
                        lines.append(line)
                else:
                    lines.append(line)
            except Exception:
                lines.append(line)
        else:
            lines.append(line)
    
    return "\n".join(lines) if lines else "Aucune action programmée"


def _format_trigger_text(trigger_str: str) -> dict[str, str]:
    """Formate le texte de déclencheur pour l'affichage."""
    trigger = parse_trigger(trigger_str)
    if not trigger:
        return {
            "formatted": trigger_str,
            "sensor_type": None,
            "metric": None,
            "operator": None,
            "threshold": None,
            "sensor_id": None,
        }
    
    sensor_name = get_sensor_display_name(trigger.sensor_type)
    metric_label = METRIC_LABELS.get(trigger.metric, trigger.metric.title())
    
    # Formater l'opérateur pour l'affichage
    operator_map = {
        ">=": "≥",
        "<=": "≤",
        ">": ">",
        "<": "<",
        "==": "=",
        "!=": "≠",
    }
    operator_display = operator_map.get(trigger.operator, trigger.operator)
    
    # Formater le seuil avec unité si nécessaire
    threshold_str = str(trigger.threshold)
    if trigger.metric == "temperature":
        threshold_str = f"{trigger.threshold}°C"
    elif trigger.metric == "humidity":
        threshold_str = f"{trigger.threshold}%"
    
    # Construire le texte formaté
    parts = [sensor_name, metric_label.lower()]
    if trigger.sensor_id:
        parts.append(f"({trigger.sensor_id.upper()})")
    formatted = f"{' '.join(parts)} {operator_display} {threshold_str}"
    
    return {
        "formatted": formatted,
        "sensor_type": trigger.sensor_type,
        "metric": trigger.metric,
        "operator": trigger.operator,
        "operator_display": operator_display,
        "threshold": trigger.threshold,
        "threshold_str": threshold_str,
        "sensor_id": trigger.sensor_id,
        "sensor_name": sensor_name,
        "metric_label": metric_label,
    }


def _collect_relay_states_with_fallback(relay_pins: dict[int, int]) -> dict[int, str]:
    hardware_states = get_relay_states() or {}
    normalized = {channel: (state or "unknown").lower() for channel, state in hardware_states.items()}
    missing_channels = [ch for ch in relay_pins.keys() if normalized.get(ch) not in {"on", "off"}]
    if not missing_channels:
        return normalized

    for channel in missing_channels:
        record = (
            RelayState.query.filter_by(channel=channel)
            .order_by(RelayState.created_at.desc())
            .first()
        )
        if record and record.state:
            normalized[channel] = (record.state or "unknown").lower()
        else:
            normalized[channel] = "unknown"
    return normalized


def _sync_runtime_device_flags(statuses: list[dict[str, Any]]) -> None:
    if not statuses:
        current_app.config["CAMERA_AVAILABLE"] = False
        current_app.config["LCD_PRESENT"] = False
        return

    camera_ok = any(status.get("id") == "usb_camera" and status.get("status") == "ok" for status in statuses)
    lcd_ok = any(status.get("id") == "lcd" and status.get("status") == "ok" for status in statuses)
    current_app.config["CAMERA_AVAILABLE"] = camera_ok
    current_app.config["LCD_PRESENT"] = lcd_ok


def _build_sensor_registry() -> dict[str, dict[str, object]]:
    registry: dict[str, dict[str, object]] = {}
    readings = (
        SensorReading.query.order_by(SensorReading.created_at.desc())
        .limit(500)
        .all()
    )
    for reading in readings:
        sensor_type = (reading.sensor_type or "").lower()
        if not sensor_type:
            continue
        display_name = get_sensor_display_name(sensor_type)
        entry = registry.setdefault(
            sensor_type,
            {
                "label": SENSOR_LABELS.get(sensor_type, sensor_type.upper()),
                "alias": display_name,
                "ids": set(),
                "metrics": set(),
            },
        )
        if reading.sensor_id:
            entry["ids"].add(reading.sensor_id)
        entry["metrics"].add(reading.metric)

    # Fallbacks pour offrir des options même sans mesures
    if "ds18b20" not in registry:
        display_name = get_sensor_display_name("ds18b20")
        registry["ds18b20"] = {
            "label": SENSOR_LABELS["ds18b20"],
            "alias": display_name,
            "ids": set(),
            "metrics": {"temperature"},
        }
    if "am2315" not in registry:
        display_name = get_sensor_display_name("am2315")
        registry["am2315"] = {
            "label": SENSOR_LABELS["am2315"],
            "alias": display_name,
            "ids": set(),
            "metrics": {"temperature", "humidity"},
        }

    # Conversion sets -> listes triées
    for entry in registry.values():
        entry["ids"] = sorted(entry["ids"])
        entry["metrics"] = sorted(entry["metrics"])
    return registry


def _hydrate_rule_form(form: AutomationRuleForm, sensor_registry: dict[str, dict[str, object]], relay_pins: dict[int, int]) -> None:
    sensor_choices = [
        (sensor_type, data.get("alias") or data["label"])  # type: ignore[index]
        for sensor_type, data in sensor_registry.items()
    ]
    sensor_choices.sort(key=lambda item: item[1])
    form.sensor_type.choices = sensor_choices or [("", "Aucun capteur disponible")]

    selected_sensor_type = form.sensor_type.data
    if not selected_sensor_type or selected_sensor_type not in sensor_registry:
        selected_sensor_type = sensor_choices[0][0] if sensor_choices else ""
        form.sensor_type.data = selected_sensor_type

    sensor_ids = []
    metrics = []
    if selected_sensor_type and selected_sensor_type in sensor_registry:
        registry_entry = sensor_registry[selected_sensor_type]
        sensor_ids = [("", "Tous les capteurs")] + [
            (sensor_id, sensor_id.upper()) for sensor_id in registry_entry["ids"]  # type: ignore[index]
        ]
        metrics = [
            (metric, METRIC_LABELS.get(metric, metric.title()))
            for metric in registry_entry["metrics"]  # type: ignore[index]
        ]
    else:
        sensor_ids = [("", "Tous les capteurs")]
        metrics = [("temperature", "Température")]

    form.sensor_id.choices = sensor_ids
    if form.sensor_id.data not in dict(sensor_ids):
        form.sensor_id.data = ""

    form.sensor_metric.choices = metrics
    if form.sensor_metric.data not in dict(metrics):
        form.sensor_metric.data = metrics[0][0] if metrics else ""

    relay_labels = get_relay_labels()
    relay_choices = [
        (channel, relay_labels.get(channel, f"Relais {channel}"))
        for channel, pin in sorted(relay_pins.items())
    ]
    if not relay_choices:
        relay_choices = [(0, "Aucun relais disponible")]
    form.relay_channel.choices = relay_choices
    if form.relay_channel.data not in dict(relay_choices):
        form.relay_channel.data = relay_choices[0][0]

    user_choices = [(0, "Ne pas envoyer d'email")]
    active_users = (
        User.query.filter_by(active=True)
        .order_by(User.username.asc())
        .all()
    )
    for user in active_users:
        label = f"{user.username} ({user.email})" if user.email else user.username
        user_choices.append((user.id, label))
    form.notify_user_id.choices = user_choices
    allowed_user_ids = {choice[0] for choice in user_choices}
    if form.notify_user_id.data not in allowed_user_ids:
        form.notify_user_id.data = 0


def build_trigger_expression(sensor_type: str, metric: str, sensor_id: Optional[str], operator: str, threshold) -> str:
    base = f"sensor:{sensor_type}.{metric}"
    if sensor_id:
        base += f"@{sensor_id}"
    return f"{base} {operator} {threshold}"


def build_action_expression(
    channel: Optional[int],
    command: Optional[str],
    *,
    relay_enabled: bool,
    notify_user_id: Optional[int],
) -> str:
    lines: list[str] = []
    if relay_enabled and channel is not None and command:
        lines.append(f"relay:{channel}={command}")
    if notify_user_id:
        lines.append(f"email:user={notify_user_id}")
    if not lines:
        return "noop"
    return "\n".join(lines)


def parse_relay_action(action: str) -> Tuple[Optional[int], Optional[str]]:
    for raw_line in action.splitlines():
        line = raw_line.strip()
        if not line or not line.lower().startswith("relay:"):
            continue
        try:
            command = line.split(":", 1)[1]
            channel_part, state_part = command.split("=", 1)
            channel = int(channel_part.strip())
            return channel, state_part.strip()
        except Exception:
            continue
    return None, None


def parse_email_action(action: str) -> Optional[int]:
    for raw_line in action.splitlines():
        line = raw_line.strip()
        if not line or not line.lower().startswith("email:"):
            continue
        try:
            payload = line.split(":", 1)[1]
            key, value = payload.split("=", 1)
            if key.strip().lower() != "user":
                continue
            user_id = int(value.strip())
            return user_id
        except Exception:
            continue
    return None

from .hardware.gpio_controller import (
    get_relay_states,
    get_configured_relay_pins,
    hardware_available,
    is_active_low,
    set_relay_state,
    get_relay_labels,
)

try:
    import cv2  # type: ignore
except ImportError:  # pragma: no cover - dépendance optionnelle
    cv2 = None  # type: ignore


main_bp = Blueprint("main", __name__)


HARDWARE_SETTING_GROUPS = [
    {
        "id": "actuators",
        "title": "Actionneurs • Carte relais",
        "subtitle": "Définissez les broches BCM utilisées par les trois relais pilotés via RPi.GPIO.",
        "items": [
            {
                "key": "Relay_Ch1",
                "label": "Relais canal 1 (GPIO BCM)",
                "default": "26",
                "description": "Broche BCM pour le premier relais (CH1).",
                "group": "relay_1",
                "group_title": "Relais 1",
                "group_subtitle": "Configurer la broche GPIO et le nom utilisé dans l’application.",
            },
            {
                "key": "Relay_Name_Ch1",
                "label": "Nom du relais 1",
                "default": "Relais 1",
                "description": "Nom affiché dans le dashboard et les règles.",
                "group": "relay_1",
            },
            {
                "key": "Relay_Ch2",
                "label": "Relais canal 2 (GPIO BCM)",
                "default": "20",
                "description": "Broche BCM pour le deuxième relais (CH2).",
                "group": "relay_2",
                "group_title": "Relais 2",
                "group_subtitle": "Configurer la broche GPIO et le nom utilisé dans l’application.",
            },
            {
                "key": "Relay_Name_Ch2",
                "label": "Nom du relais 2",
                "default": "Relais 2",
                "description": "Nom affiché dans le dashboard et les règles.",
                "group": "relay_2",
            },
            {
                "key": "Relay_Ch3",
                "label": "Relais canal 3 (GPIO BCM)",
                "default": "21",
                "description": "Broche BCM pour le troisième relais (CH3).",
                "group": "relay_3",
                "group_title": "Relais 3",
                "group_subtitle": "Configurer la broche GPIO et le nom utilisé dans l’application.",
            },
            {
                "key": "Relay_Name_Ch3",
                "label": "Nom du relais 3",
                "default": "Relais 3",
                "description": "Nom affiché dans le dashboard et les règles.",
                "group": "relay_3",
            },
        ],
    },
    {
        "id": "sensors",
        "title": "Capteurs • Température & humidité",
        "subtitle": "Paramétrez les sondes connectées au Raspberry Pi.",
        "items": [
            {
                "key": "Sensor_DS18B20_Interface",
                "label": "Sonde intérieure DS18B20",
                "default": "w1",
                "description": "Interface utilisée pour la sonde 1-Wire (DS18B20).",
                "group": "sensor_ds18b20",
                "group_title": "Sonde DS18B20",
                "group_subtitle": "Définissez l’interface et le nom convivial.",
            },
            {
                "key": "Sensor_Name_DS18B20",
                "label": "Nom de la sonde DS18B20",
                "default": "Sonde intérieure",
                "description": "Alias utilisé dans l’interface et les règles.",
                "group": "sensor_ds18b20",
            },
            {
                "key": "Sensor_AM2315_Type",
                "label": "Sonde extérieure AM2315",
                "default": "AM2315",
                "description": "Identifiant du capteur I²C pour la température et l’humidité extérieures.",
                "group": "sensor_am2315",
                "group_title": "Sonde AM2315",
                "group_subtitle": "Définissez l’identifiant I²C, l’adresse et le nom convivial.",
            },
            {
                "key": "Sensor_AM2315_Address",
                "label": "Adresse I²C AM2315",
                "default": "0x5C",
                "description": "Adresse I²C par défaut du capteur AM2315.",
                "group": "sensor_am2315",
            },
            {
                "key": "Sensor_Name_AM2315",
                "label": "Nom de la sonde AM2315",
                "default": "Sonde extérieure",
                "description": "Alias utilisé dans l’interface et les règles.",
                "group": "sensor_am2315",
            },
            {
                "key": "Sensor_Poll_Interval_Minutes",
                "label": "Intervalle de collecte (minutes)",
                "default": "30",
                "description": "Fréquence d'échantillonnage des capteurs (1 à 1440 minutes).",
            },
        ],
    },
    {
        "id": "display",
        "title": "Affichage • Écran LCD",
        "subtitle": "Paramétrez l'affichage sur l'écran LCD Grove RGB 16x2.",
        "items": [
            {
                "key": "LCD_Page_Display_Seconds",
                "label": "Temps d'affichage par page (secondes)",
                "default": "3",
                "description": "Durée d'affichage de chaque page d'informations sur l'écran LCD (1 à 60 secondes).",
            },
        ],
    },
]


def _generate_error_image(message: str = "Caméra indisponible") -> bytes:
    """Génère une image JPEG d'erreur avec un message texte"""
    if cv2 is None or np is None:
        # Retourner une image JPEG minimale si OpenCV n'est pas disponible
        return b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x01\x01\x11\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xaa\xff\xd9'
    
    try:
        # Créer une image noire 640x480
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # Ajouter le texte d'erreur
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.7
        color = (255, 255, 255)  # Blanc
        thickness = 2
        
        # Centrer le texte
        text = message
        text_size = cv2.getTextSize(text, font, font_scale, thickness)[0]
        text_x = (640 - text_size[0]) // 2
        text_y = (480 + text_size[1]) // 2
        
        cv2.putText(img, text, (text_x, text_y), font, font_scale, color, thickness)
        
        # Encoder en JPEG
        ret, buffer = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if ret:
            return buffer.tobytes()
    except Exception:
        pass
    
    # En cas d'erreur, retourner l'image JPEG minimale
    return b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x01\x01\x11\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xaa\xff\xd9'


def _camera_stream(device_index: int = 0) -> Generator[bytes, None, None]:
    """Générateur pour le flux vidéo de la caméra USB avec reconnexion automatique
    
    Args:
        device_index: Index du périphérique caméra (défaut: 0)
    """
    if cv2 is None:
        try:
            current_app.logger.error("OpenCV n'est pas installé pour le streaming caméra.")
        except RuntimeError:
            print("OpenCV n'est pas installé pour le streaming caméra.")
        # Générer une image d'erreur au lieu de lever une exception
        error_image = _generate_error_image("OpenCV non disponible")
        while True:
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + error_image + b"\r\n")
            import time
            time.sleep(2.0)
        return

    import time
    global _shared_camera_frame
    
    capture = None
    consecutive_failures = 0
    max_consecutive_failures = 5  # Nombre d'échecs avant reconnexion (réduit pour réagir plus vite)
    reconnect_delay = 0.5  # Délai avant reconnexion (secondes) - réduit pour reconnexion plus rapide
    check_interval = 15  # Vérifier la connexion toutes les 15 frames (plus fréquent)
    last_successful_frame = time.time()  # Timestamp de la dernière frame réussie
    max_time_without_frame = 5.0  # Maximum 5 secondes sans frame avant reconnexion
    
    def open_camera():
        """Ouvre la caméra avec plusieurs tentatives et détection automatique de l'index"""
        nonlocal capture
        max_attempts = 3
        
        # Essayer d'abord l'index configuré, puis d'autres indices (0, 1, 2)
        indices_to_try = [device_index]
        if device_index != 0:
            indices_to_try.append(0)
        for i in range(1, 4):
            if i not in indices_to_try:
                indices_to_try.append(i)
        
        for camera_idx in indices_to_try:
            for attempt in range(max_attempts):
                try:
                    if capture is not None:
                        try:
                            capture.release()
                        except:
                            pass
                        capture = None
                    
                    capture = cv2.VideoCapture(camera_idx)
                    if capture.isOpened():
                        # Attendre un peu pour que la caméra soit prête
                        time.sleep(0.3)
                        # Lire quelques frames pour initialiser et vérifier que ça fonctionne
                        success_count = 0
                        for _ in range(5):
                            ret, _ = capture.read()
                            if ret:
                                success_count += 1
                            time.sleep(0.1)
                        
                        if success_count > 0:
                            try:
                                current_app.logger.info(f"Caméra ouverte avec succès sur l'index {camera_idx}")
                            except RuntimeError:
                                pass
                            return True
                        else:
                            # La caméra est ouverte mais ne peut pas lire de frames
                            try:
                                current_app.logger.warning(f"Caméra index {camera_idx} ouverte mais ne peut pas lire de frames")
                            except RuntimeError:
                                pass
                            if capture:
                                try:
                                    capture.release()
                                except:
                                    pass
                                capture = None
                except Exception as e:
                    try:
                        current_app.logger.warning(f"Tentative d'ouverture caméra index {camera_idx} échouée: {e}")
                    except RuntimeError:
                        pass
                    if capture:
                        try:
                            capture.release()
                        except:
                            pass
                        capture = None
                
                if attempt < max_attempts - 1:
                    time.sleep(0.5)
        
        return False
    
    # Ouvrir la caméra initialement
    if not open_camera():
        try:
            current_app.logger.error("Impossible d'ouvrir la caméra USB. Vérifiez que la caméra est connectée et accessible.")
        except RuntimeError:
            print("Impossible d'ouvrir la caméra USB. Vérifiez que la caméra est connectée et accessible.")
        # Retourner une image d'erreur au lieu de lever une exception
        error_image = _generate_error_image("Caméra indisponible")
        retry_count = 0
        max_retries = 30  # Réessayer pendant 30 secondes avant d'abandonner
        while retry_count < max_retries:
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + error_image + b"\r\n")
            time.sleep(1.0)  # Attendre 1 seconde avant de réessayer
            retry_count += 1
            # Réessayer d'ouvrir la caméra périodiquement
            if open_camera():
                try:
                    current_app.logger.info("Caméra reconnectée avec succès après tentative de réouverture")
                except RuntimeError:
                    pass
                break
        
        # Si toujours pas de caméra après les tentatives, continuer à envoyer l'image d'erreur
        if not (capture and capture.isOpened()):
            while True:
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" + error_image + b"\r\n")
                time.sleep(2.0)  # Attendre 2 secondes entre les tentatives
                if open_camera():
                    break
            # Une fois la caméra ouverte, continuer avec le flux normal
            if not (capture and capture.isOpened()):
                return  # Sortir si toujours pas de caméra
    
    try:
        frame_count = 0
        while True:
            # Vérifier périodiquement que la caméra est toujours ouverte
            if frame_count % check_interval == 0:
                if capture is None or not capture.isOpened():
                    try:
                        current_app.logger.warning("Caméra fermée, tentative de reconnexion...")
                    except RuntimeError:
                        pass
                    if not open_camera():
                        consecutive_failures += 1
                        if consecutive_failures >= max_consecutive_failures:
                            try:
                                current_app.logger.error("Trop d'échecs de connexion à la caméra. Envoi d'image d'erreur.")
                            except RuntimeError:
                                pass
                            # Envoyer une image d'erreur au lieu de lever une exception
                            error_image = _generate_error_image("Caméra déconnectée")
                            for _ in range(10):  # Envoyer l'image d'erreur pendant 10 secondes
                                yield (b"--frame\r\n"
                                       b"Content-Type: image/jpeg\r\n\r\n" + error_image + b"\r\n")
                                time.sleep(1.0)
                            # Réessayer d'ouvrir la caméra
                            if open_camera():
                                consecutive_failures = 0
                                continue
                            else:
                                # Si toujours pas de caméra, continuer à envoyer l'image d'erreur
                                while True:
                                    yield (b"--frame\r\n"
                                           b"Content-Type: image/jpeg\r\n\r\n" + error_image + b"\r\n")
                                    time.sleep(2.0)
                                    if open_camera():
                                        consecutive_failures = 0
                                        break
                        time.sleep(reconnect_delay)
                        continue
                    consecutive_failures = 0
            
            # Lire la frame
            success, frame = capture.read()
            
            if not success:
                consecutive_failures += 1
                # Si trop d'échecs consécutifs, réessayer d'ouvrir la caméra
                if consecutive_failures >= max_consecutive_failures:
                    try:
                        current_app.logger.warning(f"{consecutive_failures} échecs consécutifs, reconnexion à la caméra...")
                    except RuntimeError:
                        pass
                    if not open_camera():
                        try:
                            current_app.logger.error("Impossible de reconnecter la caméra. Envoi d'image d'erreur.")
                        except RuntimeError:
                            pass
                        # Envoyer une image d'erreur au lieu de lever une exception
                        error_image = _generate_error_image("Caméra déconnectée")
                        for _ in range(10):  # Envoyer l'image d'erreur pendant 10 secondes
                            yield (b"--frame\r\n"
                                   b"Content-Type: image/jpeg\r\n\r\n" + error_image + b"\r\n")
                            time.sleep(1.0)
                        # Réessayer d'ouvrir la caméra
                        if open_camera():
                            consecutive_failures = 0
                            continue
                        else:
                            # Si toujours pas de caméra, continuer à envoyer l'image d'erreur
                            while True:
                                yield (b"--frame\r\n"
                                       b"Content-Type: image/jpeg\r\n\r\n" + error_image + b"\r\n")
                                time.sleep(2.0)
                                if open_camera():
                                    consecutive_failures = 0
                                    break
                    consecutive_failures = 0
                    continue
                
                time.sleep(0.1)  # Petite pause avant de réessayer
                continue

            # Réinitialiser le compteur d'échecs en cas de succès
            consecutive_failures = 0
            last_successful_frame = time.time()  # Mettre à jour le timestamp de la dernière frame réussie
            frame_count += 1
            
            # Stocker la dernière frame pour la capture photo
            with _shared_frame_lock:
                _shared_camera_frame = frame.copy() if frame is not None else None
            
            # Encoder l'image en JPEG avec une qualité raisonnable
            ret, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not ret:
                continue

            frame_bytes = buffer.tobytes()
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
            
            # Petite pause pour éviter de surcharger le CPU (~30 FPS)
            time.sleep(0.033)
    finally:
        if capture is not None:
            try:
                capture.release()
            except:
                pass
        with _shared_frame_lock:
            _shared_camera_frame = None


@main_bp.route("/")
@login_required
def dashboard():
    now = datetime.utcnow()
    rules_count = AutomationRule.query.count()
    active_rules = AutomationRule.query.filter_by(enabled=True).count()
    journal_count = JournalEntry.query.count()
    journal_last_24h = JournalEntry.query.filter(JournalEntry.created_at >= now - timedelta(days=1)).count()
    last_automation_event = (
        JournalEntry.query.filter(JournalEntry.message == "Automatisation déclenchée")
        .order_by(JournalEntry.created_at.desc())
        .first()
    )

    sensor_highlights = _get_sensor_highlights()

    # Relais
    relay_pins = get_configured_relay_pins()
    relay_labels = get_relay_labels()
    relay_states = _collect_relay_states_with_fallback(relay_pins)
    relays_available = hardware_available() and bool(relay_pins)
    relays_active_low = is_active_low()
    relay_cards = []
    channel_rule_map: dict[int, list[dict[str, str]]] = {}
    for rule in AutomationRule.query.filter(AutomationRule.enabled.is_(True)).all():
        trigger = parse_trigger(rule.trigger)
        if not trigger:
            continue
        lines = [line.strip() for line in rule.action.splitlines() if line.strip()]
        for line in lines:
            if not line.lower().startswith("relay:"):
                continue
            try:
                command = line.split(":", 1)[1]
                channel_part = command.split("=", 1)[0]
                channel_value = int(channel_part.strip())
            except Exception:
                continue
            condition = None
            if trigger:
                metric_label = METRIC_LABELS.get(trigger.metric, trigger.metric.title())
                sensor_name = get_sensor_display_name(trigger.sensor_type)
                condition = f"{sensor_name} {metric_label.lower()} {trigger.operator} {trigger.threshold}"
            action_label = _extract_relay_action_description(line)
            channel_rule_map.setdefault(channel_value, []).append(
                {
                    "name": rule.name,
                    "condition": condition,
                    "action": action_label,
                }
            )

    for channel in sorted(relay_pins.keys()):
        relay_cards.append(
            {
                "channel": channel,
                "label": relay_labels.get(channel, f"Relais #{channel}"),
                "pin": relay_pins[channel],
                "state": relay_states.get(channel, "unknown"),
                "locked": channel in channel_rule_map,
                "rules": channel_rule_map.get(channel, []),
            }
        )

    return render_template(
        "dashboard/index.html",
        rules_count=rules_count,
        active_rules=active_rules,
        journal_count=journal_count,
        journal_last_24h=journal_last_24h,
        last_automation_event=last_automation_event,
        sensor_highlights=sensor_highlights,
        relay_cards=relay_cards,
        relays_available=relays_available,
        relays_active_low=relays_active_low,
        relay_manual_disabled=not relays_available,
    )


@main_bp.route("/api/dashboard/highlights")
@login_required
def dashboard_highlights_api():
    cards = _get_sensor_highlights()
    return jsonify({"cards": cards})


@main_bp.route("/api/relays/states", methods=["GET", "OPTIONS"])
@login_required
def relays_states_api():
    # Gérer les requêtes OPTIONS (preflight CORS)
    if request.method == "OPTIONS":
        response = Response()
        origin = request.headers.get('Origin', '*')
        response.headers.add('Access-Control-Allow-Origin', origin)
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        response.headers.add('Access-Control-Allow-Methods', 'GET, OPTIONS')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-CSRFToken, X-Requested-With')
        response.headers.add('Access-Control-Max-Age', '3600')
        return response
    
    relay_pins = get_configured_relay_pins()
    states = _collect_relay_states_with_fallback(relay_pins)
    response = jsonify({"states": states, "timestamp": datetime.utcnow().isoformat()})
    # Ajouter les headers CORS explicitement pour cette route
    origin = request.headers.get('Origin', '*')
    response.headers.add('Access-Control-Allow-Origin', origin)
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    response.headers.add('Access-Control-Allow-Methods', 'GET, OPTIONS')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-CSRFToken, X-Requested-With')
    return response


@main_bp.route("/graphiques", methods=["GET"])
@login_required
def charts():
    now = datetime.utcnow()

    period_definitions = [
        ("1h", "1h", timedelta(hours=1)),
        ("24h", "24h", timedelta(hours=24)),
        ("48h", "48h", timedelta(hours=48)),
        ("7d", "7j", timedelta(days=7)),
        ("30d", "30j", timedelta(days=30)),
    ]
    period_map = {key: {"label": label, "delta": delta} for key, label, delta in period_definitions}
    selected_period = request.args.get("period", "24h")
    if selected_period not in period_map:
        selected_period = "24h"
    period_delta = period_map[selected_period]["delta"]
    period_start = now - period_delta

    base_color_map = {
        ("ds18b20", "temperature"): "#0284c7",  # sky-600
        ("am2315", "temperature"): "#38bdf8",  # sky-300
        ("am2315", "humidity"): "#0f766e",     # teal-600
    }

    # Determine aggregation level based on period
    # SQLite strftime format:
    # %Y-%m-%d %H:%M:%S (raw - no grouping needed usually, but we can group by minute)
    # %Y-%m-%d %H:00:00 (hourly)
    # %Y-%m-%d (daily)
    
    group_format = None
    if selected_period in ["7d"]:
        group_format = "%Y-%m-%d %H:00:00"  # Hourly
    elif selected_period in ["30d"]:
        group_format = "%Y-%m-%d"  # Daily (or maybe 6h? Daily is safe for 30d)
    
    # If group_format is None, we fetch raw data (or group by minute if needed, but raw is fine for short periods)
    
    from sqlalchemy import func
    
    if group_format:
        # Aggregated query avec optimisation
        # We need to group by sensor_type, metric, and the time bucket
        time_bucket = func.strftime(group_format, SensorReading.created_at).label("bucket")
        
        query = (
            db.session.query(
                SensorReading.sensor_type,
                SensorReading.metric,
                func.avg(SensorReading.value).label("avg_value"),
                func.min(SensorReading.created_at).label("min_time"),
                time_bucket
            )
            .filter(
                SensorReading.metric.in_(["temperature", "humidity"]),
                SensorReading.created_at >= period_start,
            )
            .group_by(SensorReading.sensor_type, SensorReading.metric, time_bucket)
            .order_by(time_bucket.asc())
        )
        # Limiter les résultats même pour les agrégations (sécurité)
        max_points = 2000
        results = query.limit(max_points).all()
        
        # Transform results to match the expected structure
        # Result tuples: (sensor_type, metric, avg_value, bucket)
        # Convertir les timestamps SQLite en datetime UTC puis en heure locale
        processed_readings = []
        for r in results:
            # Parser le timestamp SQLite (format: "%Y-%m-%d %H:00:00" ou "%Y-%m-%d")
            bucket_str = r.bucket
            try:
                # Parser selon le format utilisé pour l'agrégation
                # IMPORTANT: Les timestamps dans la DB sont en UTC, donc on doit les traiter comme UTC
                naive_dt = datetime.strptime(bucket_str, group_format)
                # Si le format ne contient pas d'heure (format "%Y-%m-%d"), utiliser midi comme heure par défaut
                if group_format == "%Y-%m-%d":
                    naive_dt = naive_dt.replace(hour=12, minute=0, second=0)
                # Utiliser min_time si disponible pour un timestamp plus précis
                if hasattr(r, 'min_time') and r.min_time:
                    timestamp_utc = r.min_time
                    timestamp_iso = timestamp_utc.isoformat()
                else:
                    # Fallback : traiter le datetime comme UTC
                    timestamp_utc = datetime(naive_dt.year, naive_dt.month, naive_dt.day, 
                                            naive_dt.hour, naive_dt.minute, naive_dt.second)
                    timestamp_iso = timestamp_utc.isoformat()
            except (ValueError, TypeError) as e:
                # En cas d'erreur de parsing, logger l'erreur et utiliser la chaîne telle quelle
                logger = get_app_logger()
                logger.warning(
                    "Erreur parsing timestamp SQLite",
                    error=str(e),
                    bucket=bucket_str,
                    format=group_format,
                    period=selected_period
                )
                timestamp_iso = bucket_str
                # En cas d'erreur, essayer de parser le bucket_str comme UTC
                try:
                    timestamp_utc = datetime.strptime(bucket_str, group_format)
                except:
                    timestamp_utc = None
            
            # S'assurer que timestamp_utc est défini
            if timestamp_utc is None:
                # Fallback : utiliser min_time si disponible
                if hasattr(r, 'min_time') and r.min_time:
                    timestamp_utc = r.min_time
                else:
                    # Dernier recours : utiliser maintenant
                    timestamp_utc = datetime.utcnow()
            
            processed_readings.append({
                "sensor_type": r.sensor_type,
                "metric": r.metric,
                "value": r.avg_value,
                "timestamp": timestamp_iso,
                "timestamp_utc": timestamp_utc  # Garder le datetime UTC pour la conversion
            })
            
    else:
        # Raw query avec optimisation : échantillonnage pour les périodes courtes
        # Pour les périodes de 1h, 24h, 48h, on peut échantillonner toutes les N minutes
        # pour réduire le nombre de points tout en gardant la précision visuelle
        sample_interval_minutes = None
        if selected_period == "1h":
            sample_interval_minutes = 1  # 1 point par minute max (60 points max)
        elif selected_period == "24h":
            sample_interval_minutes = 5  # 1 point par 5 minutes max (288 points max)
        elif selected_period == "48h":
            sample_interval_minutes = 10  # 1 point par 10 minutes max (288 points max)
        
        if sample_interval_minutes:
            # Utiliser une agrégation par intervalle de temps pour réduire les points
            time_bucket_format = f"%Y-%m-%d %H:%M"
            time_bucket = func.strftime(time_bucket_format, SensorReading.created_at).label("bucket")
            
            query = (
                db.session.query(
                    SensorReading.sensor_type,
                    SensorReading.metric,
                    func.avg(SensorReading.value).label("avg_value"),
                    func.min(SensorReading.created_at).label("min_time"),
                    time_bucket
                )
                .filter(
                    SensorReading.metric.in_(["temperature", "humidity"]),
                    SensorReading.created_at >= period_start,
                )
                .group_by(
                    SensorReading.sensor_type,
                    SensorReading.metric,
                    func.strftime(f"%Y-%m-%d %H:%M", SensorReading.created_at)
                )
                .order_by(time_bucket.asc())
            )
            # Limiter le nombre de résultats pour éviter les surcharges
            max_points = 1000
            results = query.limit(max_points).all()
            
            processed_readings = []
            for r in results:
                # Garder le timestamp UTC pour la conversion en timestamp Unix
                # JavaScript affichera dans le fuseau horaire du navigateur
                processed_readings.append({
                    "sensor_type": r.sensor_type,
                    "metric": r.metric,
                    "value": r.avg_value,
                    "timestamp": r.min_time.isoformat() if r.min_time else None,
                    "timestamp_utc": r.min_time  # Garder le datetime UTC pour la conversion
                })
        else:
            # Requête brute avec limite de sécurité
            query = (
                db.session.query(
                    SensorReading.sensor_type,
                    SensorReading.metric,
                    SensorReading.value,
                    SensorReading.created_at
                )
                .filter(
                    SensorReading.metric.in_(["temperature", "humidity"]),
                    SensorReading.created_at >= period_start,
                )
                .order_by(SensorReading.created_at.asc())
            )
            # Limiter à 5000 points maximum pour éviter les surcharges
            max_points = 5000
            results = query.limit(max_points).all()
            
            processed_readings = []
            for r in results:
                # Garder le timestamp UTC pour la conversion en timestamp Unix
                # JavaScript affichera dans le fuseau horaire du navigateur
                processed_readings.append({
                    "sensor_type": r.sensor_type,
                    "metric": r.metric,
                    "value": r.value,
                    "timestamp": r.created_at.isoformat() if r.created_at else None,
                    "timestamp_utc": r.created_at  # Garder le datetime UTC pour la conversion
                })

    series_map: dict[str, dict[str, object]] = {}
    for reading in processed_readings:
        if reading["value"] is None:
            continue
            
        timestamp_str = reading["timestamp"]
        value = round(float(reading["value"]), 2)
        sensor_type = reading["sensor_type"]
        metric = reading["metric"]
        
        # Convertir le timestamp UTC en millisecondes Unix pour JavaScript
        # Utiliser la fonction unique utc_to_unix_ms_for_chart pour garantir
        # que toutes les mesures utilisent la même conversion et affichent l'heure locale du Raspberry Pi
        try:
            # Utiliser timestamp_utc si disponible (datetime UTC original)
            if "timestamp_utc" in reading and reading["timestamp_utc"]:
                timestamp_utc = reading["timestamp_utc"]
                if isinstance(timestamp_utc, datetime):
                    timestamp_ms = utc_to_unix_ms_for_chart(timestamp_utc)
                else:
                    timestamp_ms = timestamp_str
            elif isinstance(timestamp_str, str):
                # Parser le timestamp ISO (devrait être UTC)
                if 'T' in timestamp_str:
                    if '+' in timestamp_str or timestamp_str.endswith('Z'):
                        dt_utc = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    else:
                        # Timestamp sans timezone, supposer UTC
                        dt_utc = datetime.fromisoformat(timestamp_str)
                    timestamp_ms = utc_to_unix_ms_for_chart(dt_utc)
                else:
                    # Format SQLite simple, supposer UTC
                    dt_utc = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                    timestamp_ms = utc_to_unix_ms_for_chart(dt_utc)
            else:
                timestamp_ms = timestamp_str
        except (ValueError, AttributeError, TypeError) as e:
            logger = get_app_logger()
            logger.warning(
                "Erreur conversion timestamp",
                error=str(e),
                timestamp=timestamp_str,
                sensor_type=sensor_type,
                metric=metric
            )
            timestamp_ms = timestamp_str
        
        if sensor_type == "ds18b20":
            alias = get_sensor_display_name("ds18b20")
            series_name = alias or "Température DS18B20"
            unit = "°C"
            axis = "temperature"
        elif sensor_type == "am2315":
            if metric == "temperature":
                alias = get_sensor_display_name("am2315")
                series_name = alias or "Température AM2315"
                unit = "°C"
                axis = "temperature"
            elif metric == "humidity":
                alias = get_sensor_display_name("am2315")
                series_name = f"Humidité {alias}" if alias else "Humidité AM2315"
                unit = "%"
                axis = "humidity"
            else:
                continue
        else:
            continue
            
        key = (sensor_type, metric)
        base_color = base_color_map.get(key)
        series_entry = series_map.setdefault(
            series_name,
            {
                "name": series_name,
                "unit": unit,
                "axis": axis,
                "data": [],
                "color": base_color,
                "meta": {"sensor_type": sensor_type, "metric": metric},
            },
        )
        series_entry["data"].append({"x": timestamp_ms, "y": value})

    # Ajouter la dernière valeur brute de chaque capteur pour garantir la cohérence avec le dashboard
    # Cela évite les différences dues à l'agrégation des données
    latest_readings = {}
    for sensor_type in ["ds18b20", "am2315"]:
        for metric in ["temperature", "humidity"]:
            if sensor_type == "ds18b20" and metric == "humidity":
                continue  # DS18B20 ne mesure que la température
            latest = (
                SensorReading.query.filter(
                    SensorReading.sensor_type == sensor_type,
                    SensorReading.metric == metric,
                    SensorReading.value.isnot(None),
                )
                .order_by(SensorReading.created_at.desc())
                .first()
            )
            if latest:
                key = (sensor_type, metric)
                latest_readings[key] = {
                    "value": float(latest.value),
                    "timestamp_utc": latest.created_at,
                }
    
    # Ajouter les dernières valeurs brutes aux séries correspondantes
    for key, latest_data in latest_readings.items():
        sensor_type, metric = key
        
        # Déterminer le nom de la série comme dans le code précédent
        if sensor_type == "ds18b20":
            alias = get_sensor_display_name("ds18b20")
            series_name = alias or "Température DS18B20"
        elif sensor_type == "am2315":
            if metric == "temperature":
                alias = get_sensor_display_name("am2315")
                series_name = alias or "Température AM2315"
            elif metric == "humidity":
                alias = get_sensor_display_name("am2315")
                series_name = f"Humidité {alias}" if alias else "Humidité AM2315"
            else:
                continue
        else:
            continue
        
        # Trouver la série correspondante
        series_entry = None
        for series in series_map.values():
            meta = series.get("meta", {})
            if meta.get("sensor_type") == sensor_type and meta.get("metric") == metric:
                series_entry = series
                break
        
        if series_entry:
            # Convertir le timestamp UTC en millisecondes Unix
            timestamp_ms = utc_to_unix_ms_for_chart(latest_data["timestamp_utc"])
            value = round(latest_data["value"], 2)
            
            data_points = series_entry.get("data", [])
            
            # Trouver le dernier point existant (le plus récent)
            last_point_index = None
            last_point_timestamp = None
            if data_points:
                # Les points sont déjà triés par timestamp croissant
                for i, point in enumerate(data_points):
                    point_ts = point.get("x", 0)
                    if last_point_timestamp is None or point_ts > last_point_timestamp:
                        last_point_timestamp = point_ts
                        last_point_index = i
            
            # Si la dernière valeur brute est plus récente que le dernier point agrégé, la remplacer
            # Sinon, l'ajouter seulement si elle n'existe pas déjà
            if last_point_index is not None and timestamp_ms >= last_point_timestamp:
                # Remplacer le dernier point par la valeur brute la plus récente
                data_points[last_point_index] = {"x": timestamp_ms, "y": value}
            else:
                # Vérifier si cette valeur n'est pas déjà présente (pour éviter les doublons)
                is_duplicate = False
                for point in data_points:
                    if point.get("x") == timestamp_ms and point.get("y") == value:
                        is_duplicate = True
                        break
                
                # Ajouter seulement si ce n'est pas un doublon
                if not is_duplicate:
                    data_points.append({"x": timestamp_ms, "y": value})
                    # Trier par timestamp pour maintenir l'ordre chronologique
                    data_points.sort(key=lambda p: p.get("x", 0))

    chart_series: list[dict[str, object]] = list(series_map.values())
    
    def _split_series_by_axis(target_axis: str) -> Tuple[list[dict[str, object]], list[str]]:
        subset: list[dict[str, object]] = []
        colors: list[str] = []
        for series in chart_series:
            axis = series.get("axis")
            if axis != target_axis:
                continue
            subset.append(series)
            color_value = series.get("color")
            if isinstance(color_value, str) and color_value:
                colors.append(color_value)
            else:
                fallback = "#0284c7" if target_axis == "temperature" else "#0f766e"
                colors.append(fallback)
        return subset, colors

    def _summarize_series(series_subset: list[dict[str, object]], unit: str, title: str) -> dict[str, object]:
        values: list[float] = []
        last_point: Optional[Tuple[str, float]] = None
        for series in series_subset:
            for point in series.get("data", []):
                y_value = point.get("y")
                if y_value is None:
                    continue
                try:
                    numeric_value = float(y_value)
                except (TypeError, ValueError):
                    continue
                values.append(numeric_value)
                x_value = point.get("x")
                if x_value:
                    if last_point is None or x_value > last_point[0]:
                        last_point = (x_value, numeric_value)
        decimals = 1
        if not values:
            return {
                "title": title,
                "unit": unit,
                "min": None,
                "max": None,
                "avg": None,
                "last": last_point[1] if last_point else None,
                "last_at": last_point[0] if last_point else None,
                "count": 0,
                "decimals": decimals,
            }
        avg_value = sum(values) / len(values)
        if last_point is None:
            last_point = ("", values[-1])
        return {
            "title": title,
            "unit": unit,
            "min": min(values),
            "max": max(values),
            "avg": avg_value,
            "last": last_point[1],
            "last_at": last_point[0],
            "count": len(values),
            "decimals": decimals,
        }

    temperature_series, temperature_colors = _split_series_by_axis("temperature")
    humidity_series, humidity_colors = _split_series_by_axis("humidity")
    temperature_summary = _summarize_series(temperature_series, "°C", "Température")
    humidity_summary = _summarize_series(humidity_series, "%", "Humidité")
    temperature_has_data = temperature_summary["count"] > 0
    humidity_has_data = humidity_summary["count"] > 0
    temperature_summary["count_display"] = int(temperature_summary["count"] / max(len([s for s in temperature_series if s.get("axis") == "temperature"]), 1))
    humidity_summary["count_display"] = humidity_summary["count"]
    chart_has_data = bool(temperature_has_data or humidity_has_data)

    current_query = request.args.to_dict()
    chart_period_links: list[dict[str, object]] = []
    for key, label, _ in period_definitions:
        params = current_query.copy()
        params["period"] = key
        chart_period_links.append(
            {
                "value": key,
                "label": label,
                "active": key == selected_period,
            }
        )

    relay_history = (
        RelayState.query.filter(RelayState.created_at >= period_start)
        .order_by(RelayState.created_at.asc())
        .all()
    )

    relay_channel_colors = {
        1: {"border": "#f97316", "background": "rgba(249, 115, 22, 0.15)"},
        2: {"border": "#8b5cf6", "background": "rgba(139, 92, 246, 0.18)"},
        3: {"border": "#14b8a6", "background": "rgba(20, 184, 166, 0.18)"},
    }
    relay_labels_map = get_relay_labels()
    relay_annotations = []
    relay_legend_map: dict[int, dict[str, object]] = {}

    for entry in relay_history:
        channel = entry.channel
        colors = relay_channel_colors.get(
            channel,
            {"border": "#f97316", "background": "rgba(249, 115, 22, 0.15)"},
        )
        relay_name = relay_labels_map.get(channel, f"Relais {channel}")
        state_lower = (entry.state or "").lower()
        if state_lower == "on":
            label_text = f"▲ {relay_name} ON"
        elif state_lower == "off":
            label_text = f"▼ {relay_name} OFF"
        else:
            label_text = f"{relay_name} → {entry.state}"
        details_text = [f"Source : {entry.source or 'N/A'}"]
        # Utiliser la fonction unique de conversion pour garantir la cohérence avec les autres mesures
        timestamp_ms = utc_to_unix_ms_for_chart(entry.created_at)
        relay_annotations.append(
            {
                "timestamp": timestamp_ms,
                "label": label_text,
                "color": colors["border"],
                "background": colors["background"],
                "data": {"channel": channel, "state": state_lower, "details": details_text},
            }
        )
        if channel not in relay_legend_map:
            relay_legend_map[channel] = {
                "channel": channel,
                "name": relay_name,
                "color": colors["border"],
            }

    relay_legend = sorted(relay_legend_map.values(), key=lambda item: item["name"])

    relay_state_series_map: dict[int, dict[str, object]] = {}
    relay_state_colors = []
    relay_state_counts = len(relay_history)

    relay_series_entries: dict[int, list[dict[str, object]]] = {}
    for entry in relay_history:
        channel = entry.channel
        state_lower = (entry.state or "").lower()
        target_state = 1 if state_lower == "on" else 0
        # Utiliser la fonction unique de conversion pour garantir la cohérence avec les autres mesures
        timestamp_ms = utc_to_unix_ms_for_chart(entry.created_at)
        relay_series_entries.setdefault(channel, []).append(
            {"x": timestamp_ms, "y": target_state}
        )

    for channel, series_data in relay_series_entries.items():
        relay_name = relay_labels_map.get(channel, f"Relais {channel}")
        color = relay_channel_colors.get(channel, {"border": "#f97316"})["border"]
        relay_state_colors.append(color)
        relay_state_series_map[channel] = {
            "name": relay_name,
            "data": series_data,
        }

    relay_state_series = list(relay_state_series_map.values())

    measurements_total = (temperature_summary["count"] or 0) + (humidity_summary["count"] or 0)

    return render_template(
        "dashboard/charts.html",
        chart_has_data=chart_has_data,
        chart_period_links=chart_period_links,
        chart_selected_period=selected_period,
        temperature_series=temperature_series,
        temperature_colors=temperature_colors,
        temperature_summary=temperature_summary,
        humidity_series=humidity_series,
        humidity_colors=humidity_colors,
        humidity_summary=humidity_summary,
        temperature_has_data=temperature_has_data,
        humidity_has_data=humidity_has_data,
        relay_legend=relay_legend,
        relay_state_series=relay_state_series,
        relay_state_colors=relay_state_colors,
        relay_event_count=relay_state_counts,
        measurements_total=measurements_total,
    )

    return render_template(
        "dashboard/charts.html",
        chart_has_data=chart_has_data,
        chart_period_links=chart_period_links,
        chart_selected_period=selected_period,
    )


@main_bp.route("/relays/<int:channel>/command", methods=["POST"])
@login_required
def relay_command(channel: int):
    if current_user.role != "admin":
        flash("Accès réservé à l'administrateur.", "danger")
        return redirect(url_for("main.dashboard"))
    command = (request.form.get("command") or "").strip().lower()
    wants_json = (
        request.accept_mimetypes["application/json"] >= request.accept_mimetypes["text/html"]
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
    )
    if not command:
        message = "Commande invalide."
        if wants_json:
            return jsonify({"status": "error", "message": message, "channel": channel}), 400
        flash(message, "danger")
        return redirect(url_for("main.dashboard"))

    result = set_relay_state(channel, command)
    status = result.get("status")
    message = result.get("message", "Commande exécutée.")
    final_state = result.get("state") or command if status == "ok" else None

    # Pour les requêtes JSON, répondre immédiatement et traiter le journal/notifications en arrière-plan
    if wants_json and status == "ok":
        from .automation_engine import _notify_relay_change
        
        # Préparer les données pour le thread
        username = current_user.username
        app_instance = current_app._get_current_object()
        
        def background_tasks():
            """Exécute les tâches lourdes en arrière-plan"""
            with app_instance.app_context():
                try:
                    # Journal
                    db.session.add(
                        JournalEntry(
                            level="info",
                            message=f"Commande relais ch{channel}",
                            details={
                                "channel": channel,
                                "command": command,
                                "result": result,
                                "issued_by": username,
                                "timestamp": datetime.utcnow().isoformat(),
                            },
                        )
                    )
                    db.session.commit()
                    
                    # Notification (peut être lent à cause de l'email)
                    _notify_relay_change(channel=channel, state=final_state, source=f"Manuel ({username})")
                except Exception as exc:
                    current_app.logger.error("Erreur dans les tâches en arrière-plan pour relais %s: %s", channel, exc)
        
        # Démarrer les tâches en arrière-plan
        thread = threading.Thread(target=background_tasks, daemon=True)
        thread.start()
        
        # Répondre immédiatement
        return (
            jsonify(
                {
                    "status": "ok",
                    "message": message,
                    "channel": channel,
                    "state": final_state,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            ),
            200,
        )
    
    # Pour les requêtes non-JSON (formulaires classiques), garder le comportement synchrone
    db.session.add(
        JournalEntry(
            level="info" if status == "ok" else "warning",
            message=f"Commande relais ch{channel}",
            details={
                "channel": channel,
                "command": command,
                "result": result,
                "issued_by": current_user.username,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
    )
    db.session.commit()

    if status == "ok":
        from .automation_engine import _notify_relay_change
        _notify_relay_change(channel=channel, state=final_state, source=f"Manuel ({current_user.username})")

    if wants_json and status != "ok":
        return (
            jsonify(
                {
                    "status": status or "error",
                    "message": message,
                    "channel": channel,
                    "state": result.get("state"),
                }
            ),
            400,
        )

    if status == "ok":
        flash(message, "success")
    elif status == "unavailable":
        flash("Contrôle des relais indisponible sur cette plateforme.", "warning")
    else:
        flash(message, "danger")
    return redirect(url_for("main.dashboard"))


@main_bp.route("/automatisation", methods=["GET", "POST"])
@login_required
def automation():
    if current_user.role != "admin":
        flash("Accès réservé à l'administrateur.", "danger")
        return redirect(url_for("main.dashboard"))
    form = AutomationRuleForm()
    if request.method == "GET":
        form.relay_action_enabled.data = True
        form.notify_user_id.data = 0

    sensor_registry = _build_sensor_registry()
    relay_pins = get_configured_relay_pins()
    relay_labels = get_relay_labels()
    _hydrate_rule_form(form, sensor_registry, relay_pins)

    search = request.args.get("q", "").strip()
    owner_id = request.args.get("owner", "")
    sort = request.args.get("sort", "")

    query = AutomationRule.query.join(User)

    if search:
        like = f"%{search}%"
        query = query.filter(
            db.or_(
                AutomationRule.name.ilike(like),
                AutomationRule.trigger.ilike(like),
                AutomationRule.action.ilike(like),
            )
        )

    if owner_id.isdigit():
        query = query.filter(AutomationRule.owner_id == int(owner_id))

    if sort == "name":
        query = query.order_by(AutomationRule.name.asc())
    else:
        query = query.order_by(AutomationRule.created_at.desc())

    filters = {"q": search, "owner": owner_id, "sort": sort}
    filters_query = urlencode({k: v for k, v in filters.items() if v})

    if form.validate_on_submit():
        # Validation personnalisée : au moins une action doit être configurée
        relay_enabled = bool(form.relay_action_enabled.data)
        notify_user = form.notify_user_id.data or None
        
        if relay_enabled:
            if not form.relay_channel.data or not form.relay_action.data:
                flash("Si la commande relais est activée, le relais et l'action doivent être sélectionnés.", "warning")
                _hydrate_rule_form(form, sensor_registry, relay_pins)
                rules = query.all()
                formatted_rules = []
                for r in rules:
                    trigger_formatted = _format_trigger_text(r.trigger)
                    rule_dict = {
                        'id': r.id,
                        'name': r.name,
                        'trigger': r.trigger,
                        'trigger_formatted': trigger_formatted,
                        'action': r.action,
                        'action_formatted': _format_action_text(r.action),
                        'enabled': r.enabled,
                        'cooldown_seconds': r.cooldown_seconds,
                        'created_at': r.created_at,
                        'updated_at': r.updated_at,
                        'last_triggered_at': r.last_triggered_at,
                        'owner': r.owner,
                    }
                    formatted_rules.append(rule_dict)
                return render_template(
                    "dashboard/automation.html",
                    form=form,
                    rules=formatted_rules,
                    filters=filters,
                    filters_query=filters_query,
                    form_action=url_for("main.automation") + ("?" + filters_query if filters_query else ""),
                    form_title="Créer une règle",
                    form_subtitle="Définissez les déclencheurs et actions pour automatiser vos scénarios.",
                    submit_label="Enregistrer",
                    cancel_url=None,
                    editing_rule_id=None,
                    sensor_registry_json=json.dumps(sensor_registry),
                    relay_labels_json=json.dumps(relay_labels),
                )
        
        if not relay_enabled and (not notify_user or notify_user == 0):
            flash("Au moins une action doit être configurée : commande relais ou notification par email.", "warning")
            _hydrate_rule_form(form, sensor_registry, relay_pins)
            rules = query.all()
            formatted_rules = []
            for r in rules:
                trigger_formatted = _format_trigger_text(r.trigger)
                rule_dict = {
                    'id': r.id,
                    'name': r.name,
                    'trigger': r.trigger,
                    'trigger_formatted': trigger_formatted,
                    'action': r.action,
                    'action_formatted': _format_action_text(r.action),
                    'enabled': r.enabled,
                    'cooldown_seconds': r.cooldown_seconds,
                    'created_at': r.created_at,
                    'updated_at': r.updated_at,
                    'last_triggered_at': r.last_triggered_at,
                    'owner': r.owner,
                }
                formatted_rules.append(rule_dict)
            return render_template(
                "dashboard/automation.html",
                form=form,
                rules=formatted_rules,
                filters=filters,
                filters_query=filters_query,
                form_action=url_for("main.automation") + ("?" + filters_query if filters_query else ""),
                form_title="Créer une règle",
                form_subtitle="Définissez les déclencheurs et actions pour automatiser vos scénarios.",
                submit_label="Enregistrer",
                cancel_url=None,
                editing_rule_id=None,
                sensor_registry_json=json.dumps(sensor_registry),
                relay_labels_json=json.dumps(relay_labels),
            )
        
        cooldown = form.cooldown_seconds.data if form.cooldown_seconds.data is not None else 300
        trigger_str = build_trigger_expression(
            sensor_type=form.sensor_type.data,
            metric=form.sensor_metric.data,
            sensor_id=form.sensor_id.data,
            operator=form.operator.data,
            threshold=form.threshold.data,
        )
        action_str = build_action_expression(
            channel=form.relay_channel.data,
            command=form.relay_action.data,
            relay_enabled=relay_enabled,
            notify_user_id=notify_user,
        )
        rule = AutomationRule(
            name=form.name.data,
            trigger=trigger_str,
            action=action_str,
            cooldown_seconds=cooldown,
            enabled=form.enabled.data,
            owner=current_user,
        )
        db.session.add(rule)
        db.session.add(JournalEntry(level="info", message=f"Nouvelle règle créée: {rule.name}"))
        db.session.commit()
        flash("Règle enregistrée.", "success")
        redirect_url = url_for("main.automation") + ("?" + filters_query if filters_query else "")
        return redirect(redirect_url)

    rules = query.all()
    # Formater les actions et déclencheurs pour l'affichage
    formatted_rules = []
    for rule in rules:
        trigger_formatted = _format_trigger_text(rule.trigger)
        rule_dict = {
            'id': rule.id,
            'name': rule.name,
            'trigger': rule.trigger,
            'trigger_formatted': trigger_formatted,
            'action': rule.action,
            'action_formatted': _format_action_text(rule.action),
            'enabled': rule.enabled,
            'cooldown_seconds': rule.cooldown_seconds,
            'created_at': rule.created_at,
            'updated_at': rule.updated_at,
            'last_triggered_at': rule.last_triggered_at,
            'owner': rule.owner,
        }
        formatted_rules.append(rule_dict)
    
    # S'assurer que relay_labels est défini
    if 'relay_labels' not in locals():
        relay_labels = get_relay_labels()
    
    return render_template(
        "dashboard/automation.html",
        form=form,
        rules=formatted_rules,
        filters=filters,
        filters_query=filters_query,
        form_action=url_for("main.automation") + ("?" + filters_query if filters_query else ""),
        form_title="Créer une règle",
        form_subtitle="Définissez les déclencheurs et actions pour automatiser vos scénarios.",
        submit_label="Enregistrer",
        cancel_url=None,
        editing_rule_id=None,
        sensor_registry_json=json.dumps(sensor_registry),
        relay_labels_json=json.dumps(relay_labels),
    )


@main_bp.route("/automatisation/<int:rule_id>/modifier", methods=["GET", "POST"])
@login_required
def edit_rule(rule_id: int):
    if current_user.role != "admin":
        flash("Accès réservé à l'administrateur.", "danger")
        return redirect(url_for("main.dashboard"))
    rule = AutomationRule.query.get_or_404(rule_id)
    if rule.owner != current_user and current_user.role != "admin":
        flash("Accès refusé.", "danger")
        return redirect(url_for("main.automation"))

    form = AutomationRuleForm()

    sensor_registry = _build_sensor_registry()
    relay_pins = get_configured_relay_pins()
    relay_labels = get_relay_labels()

    if request.method == "GET":
        form.name.data = rule.name
        form.cooldown_seconds.data = rule.cooldown_seconds
        form.enabled.data = rule.enabled
        trigger = parse_trigger(rule.trigger)
        if trigger:
            form.sensor_type.data = trigger.sensor_type
            form.sensor_metric.data = trigger.metric
            form.operator.data = trigger.operator
            form.threshold.data = trigger.threshold
            form.sensor_id.data = trigger.sensor_id or ""
        action_channel, action_command = parse_relay_action(rule.action)
        if action_channel is not None:
            form.relay_channel.data = action_channel
            form.relay_action_enabled.data = True
        else:
            form.relay_action_enabled.data = False
        if action_command:
            form.relay_action.data = action_command
        notify_user = parse_email_action(rule.action)
        form.notify_user_id.data = notify_user or 0

    _hydrate_rule_form(form, sensor_registry, relay_pins)

    search = request.args.get("q", "").strip()
    owner_id = request.args.get("owner", "")
    sort = request.args.get("sort", "")
    query = AutomationRule.query.join(User)

    if search:
        like = f"%{search}%"
        query = query.filter(
            db.or_(
                AutomationRule.name.ilike(like),
                AutomationRule.trigger.ilike(like),
                AutomationRule.action.ilike(like),
            )
        )

    if owner_id.isdigit():
        query = query.filter(AutomationRule.owner_id == int(owner_id))

    if sort == "name":
        query = query.order_by(AutomationRule.name.asc())
    else:
        query = query.order_by(AutomationRule.created_at.desc())

    filters = {"q": search, "owner": owner_id, "sort": sort}
    filters_query = urlencode({k: v for k, v in filters.items() if v})

    if form.validate_on_submit():
        # Validation personnalisée : au moins une action doit être configurée
        relay_enabled = bool(form.relay_action_enabled.data)
        notify_user = form.notify_user_id.data or None
        
        if relay_enabled:
            if not form.relay_channel.data or not form.relay_action.data:
                flash("Si la commande relais est activée, le relais et l'action doivent être sélectionnés.", "warning")
                _hydrate_rule_form(form, sensor_registry, relay_pins)
                rules = query.all()
                formatted_rules = []
                for r in rules:
                    trigger_formatted = _format_trigger_text(r.trigger)
                    rule_dict = {
                        'id': r.id,
                        'name': r.name,
                        'trigger': r.trigger,
                        'trigger_formatted': trigger_formatted,
                        'action': r.action,
                        'action_formatted': _format_action_text(r.action),
                        'enabled': r.enabled,
                        'cooldown_seconds': r.cooldown_seconds,
                        'created_at': r.created_at,
                        'updated_at': r.updated_at,
                        'last_triggered_at': r.last_triggered_at,
                        'owner': r.owner,
                    }
                    formatted_rules.append(rule_dict)
                form_action = url_for("main.edit_rule", rule_id=rule.id)
                cancel_url = url_for("main.automation")
                if filters_query:
                    form_action = f"{form_action}?{filters_query}"
                    cancel_url = f"{cancel_url}?{filters_query}"
                if 'relay_labels' not in locals():
                    relay_labels = get_relay_labels()
                return render_template(
                    "dashboard/automation.html",
                    form=form,
                    rules=formatted_rules,
                    filters=filters,
                    filters_query=filters_query,
                    form_action=form_action,
                    form_title="Modifier la règle",
                    form_subtitle=f"Dernière mise à jour le {format_local_datetime(rule.updated_at if rule.updated_at else rule.created_at)}",
                    submit_label="Mettre à jour",
                    cancel_url=cancel_url,
                    editing_rule_id=rule.id,
                    sensor_registry_json=json.dumps(sensor_registry),
                    relay_labels_json=json.dumps(relay_labels),
                )
        
        if not relay_enabled and (not notify_user or notify_user == 0):
            flash("Au moins une action doit être configurée : commande relais ou notification par email.", "warning")
            _hydrate_rule_form(form, sensor_registry, relay_pins)
            rules = query.all()
            formatted_rules = []
            for r in rules:
                trigger_formatted = _format_trigger_text(r.trigger)
                rule_dict = {
                    'id': r.id,
                    'name': r.name,
                    'trigger': r.trigger,
                    'trigger_formatted': trigger_formatted,
                    'action': r.action,
                    'action_formatted': _format_action_text(r.action),
                    'enabled': r.enabled,
                    'cooldown_seconds': r.cooldown_seconds,
                    'created_at': r.created_at,
                    'updated_at': r.updated_at,
                    'last_triggered_at': r.last_triggered_at,
                    'owner': r.owner,
                }
                formatted_rules.append(rule_dict)
            form_action = url_for("main.edit_rule", rule_id=rule.id)
            cancel_url = url_for("main.automation")
            if filters_query:
                form_action = f"{form_action}?{filters_query}"
                cancel_url = f"{cancel_url}?{filters_query}"
            if 'relay_labels' not in locals():
                relay_labels = get_relay_labels()
            return render_template(
                "dashboard/automation.html",
                form=form,
                rules=formatted_rules,
                filters=filters,
                filters_query=filters_query,
                form_action=form_action,
                form_title="Modifier la règle",
                form_subtitle=f"Dernière mise à jour le {format_local_datetime(rule.updated_at if rule.updated_at else rule.created_at)}",
                submit_label="Mettre à jour",
                cancel_url=cancel_url,
                editing_rule_id=rule.id,
                sensor_registry_json=json.dumps(sensor_registry),
                relay_labels_json=json.dumps(relay_labels),
            )
        
        cooldown = form.cooldown_seconds.data if form.cooldown_seconds.data is not None else 300
        trigger_str = build_trigger_expression(
            sensor_type=form.sensor_type.data,
            metric=form.sensor_metric.data,
            sensor_id=form.sensor_id.data,
            operator=form.operator.data,
            threshold=form.threshold.data,
        )
        action_str = build_action_expression(
            channel=form.relay_channel.data,
            command=form.relay_action.data,
            relay_enabled=relay_enabled,
            notify_user_id=notify_user,
        )
        original = {
            "name": rule.name,
            "trigger": rule.trigger,
            "action": rule.action,
            "cooldown_seconds": rule.cooldown_seconds,
            "enabled": rule.enabled,
        }
        updated = {
            "name": form.name.data,
            "trigger": trigger_str,
            "action": action_str,
            "cooldown_seconds": cooldown,
            "enabled": form.enabled.data,
        }
        changes = build_changes(original, updated, ["name", "trigger", "action", "cooldown_seconds", "enabled"])

        rule.name = updated["name"]
        rule.trigger = updated["trigger"]
        rule.action = updated["action"]
        rule.cooldown_seconds = updated["cooldown_seconds"]
        rule.enabled = updated["enabled"]

        if changes:
            db.session.add(
                JournalEntry(
                    level="info",
                    message=f"Règle modifiée: {rule.name}",
                    details={
                        "entity": "automation_rule",
                        "rule_id": rule.id,
                        "changes": changes,
                        "updated_by": current_user.username,
                    },
                )
            )

        db.session.commit()
        flash("Règle mise à jour.", "success")
        redirect_url = url_for("main.automation") + ("?" + filters_query if filters_query else "")
        return redirect(redirect_url)

    rules = query.all()
    # Formater les actions et déclencheurs pour l'affichage
    formatted_rules = []
    for r in rules:
        trigger_formatted = _format_trigger_text(r.trigger)
        rule_dict = {
            'id': r.id,
            'name': r.name,
            'trigger': r.trigger,
            'trigger_formatted': trigger_formatted,
            'action': r.action,
            'action_formatted': _format_action_text(r.action),
            'enabled': r.enabled,
            'cooldown_seconds': r.cooldown_seconds,
            'created_at': r.created_at,
            'updated_at': r.updated_at,
            'last_triggered_at': r.last_triggered_at,
            'owner': r.owner,
        }
        formatted_rules.append(rule_dict)

    # S'assurer que relay_labels est défini
    if 'relay_labels' not in locals():
        relay_labels = get_relay_labels()

    form_action = url_for("main.edit_rule", rule_id=rule.id)
    cancel_url = url_for("main.automation")
    if filters_query:
        form_action = f"{form_action}?{filters_query}"
        cancel_url = f"{cancel_url}?{filters_query}"

    return render_template(
        "dashboard/automation.html",
        form=form,
        rules=formatted_rules,
        filters=filters,
        filters_query=filters_query,
        form_action=form_action,
        form_title="Modifier la règle",
        form_subtitle=f"Dernière mise à jour le {format_local_datetime(rule.updated_at if rule.updated_at else rule.created_at)}",
        submit_label="Mettre à jour",
        cancel_url=cancel_url,
        editing_rule_id=rule.id,
        sensor_registry_json=json.dumps(sensor_registry),
        relay_labels_json=json.dumps(relay_labels),
    )


@main_bp.route("/automatisation/<int:rule_id>/supprimer", methods=["POST"])
@login_required
def delete_rule(rule_id: int):
    if current_user.role != "admin":
        flash("Accès réservé à l'administrateur.", "danger")
        return redirect(url_for("main.dashboard"))
    rule = AutomationRule.query.get_or_404(rule_id)
    if rule.owner != current_user and current_user.role != "admin":
        flash("Accès refusé.", "danger")
        return redirect(url_for("main.automation"))
    db.session.delete(rule)
    db.session.add(JournalEntry(level="warning", message=f"Règle supprimée: {rule.name}"))
    db.session.commit()
    flash("Règle supprimée.", "info")
    return redirect(url_for("main.automation"))


@main_bp.route("/camera")
@login_required
def camera():
    camera_available = current_app.config.get("CAMERA_AVAILABLE", False)
    
    # Récupérer les captures récentes
    captures_folder = current_app.config.get("CAPTURES_FOLDER")
    if captures_folder:
        captures_dir = Path(captures_folder)
    else:
        static_folder = current_app.static_folder or "app/static"
        captures_dir = Path(static_folder) / "captures"
    captures_dir.mkdir(parents=True, exist_ok=True)
    
    captures = []
    if captures_dir.exists():
        for file_path in sorted(captures_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)[:20]:
            if file_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".mp4", ".avi", ".mov"}:
                captures.append({
                    "filename": file_path.name,
                    "type": "video" if file_path.suffix.lower() in {".mp4", ".avi", ".mov"} else "photo",
                    "size": file_path.stat().st_size,
                    "created_at": datetime.fromtimestamp(file_path.stat().st_mtime),
                    "filepath": str(file_path),
                })
    
    return render_template("dashboard/camera.html", camera_available=bool(camera_available), captures=captures)


@main_bp.route("/camera/flux")
@login_required
def camera_feed():
    # Vérifier si la caméra est connectée
    global _camera_connected
    if not _camera_connected:
        # Retourner une image placeholder quand le flux est désactivé
        def placeholder_stream():
            placeholder_image = _generate_error_image("Flux vidéo désactivé")
            while True:
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" + placeholder_image + b"\r\n")
                import time
                time.sleep(2.0)
        response = Response(
            placeholder_stream(),
            mimetype="multipart/x-mixed-replace; boundary=frame"
        )
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        response.headers['Connection'] = 'keep-alive'
        return response
    
    try:
        # Vérifier que cv2 est disponible
        if cv2 is None:
            current_app.logger.error("OpenCV n'est pas disponible pour le streaming caméra.")
            # Retourner un stream d'erreur au lieu de 503
            def error_stream():
                error_image = _generate_error_image("OpenCV non disponible")
                while True:
                    yield (b"--frame\r\n"
                           b"Content-Type: image/jpeg\r\n\r\n" + error_image + b"\r\n")
                    import time
                    time.sleep(2.0)
            response = Response(
                error_stream(),
                mimetype="multipart/x-mixed-replace; boundary=frame"
            )
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            response.headers['Connection'] = 'keep-alive'
            return response
        
        # Capturer l'index du périphérique avant de créer le générateur pour éviter les problèmes de contexte
        device_index = current_app.config.get("CAMERA_DEVICE_INDEX", 0)
        
        # Créer la réponse avec les bons headers pour le streaming MJPEG
        response = Response(
            _camera_stream(device_index=device_index),
            mimetype="multipart/x-mixed-replace; boundary=frame"
        )
        # Ajouter des headers pour éviter la mise en cache et permettre la reconnexion
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        response.headers['Connection'] = 'keep-alive'
        return response
    except RuntimeError as e:
        current_app.logger.error(f"Erreur lors du streaming caméra: {e}")
        # Générer une image d'erreur et la retourner en streaming
        error_image = _generate_error_image("Caméra indisponible")
        def error_stream():
            while True:
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" + error_image + b"\r\n")
                import time
                time.sleep(2.0)
        response = Response(
            error_stream(),
            mimetype="multipart/x-mixed-replace; boundary=frame"
        )
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        response.headers['Connection'] = 'keep-alive'
        return response
    except Exception as e:
        current_app.logger.error(f"Erreur inattendue lors du streaming caméra: {e}", exc_info=True)
        # Retourner un stream d'erreur au lieu de 500
        error_image = _generate_error_image("Erreur caméra")
        def error_stream():
            while True:
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" + error_image + b"\r\n")
                import time
                time.sleep(2.0)
        response = Response(
            error_stream(),
            mimetype="multipart/x-mixed-replace; boundary=frame"
        )
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        response.headers['Connection'] = 'keep-alive'
        return response


# Verrou pour partager l'accès à la caméra entre le flux MJPEG et les captures
_camera_lock = threading.Lock()
# Dernière frame capturée pour permettre la capture photo sans ouvrir une nouvelle instance
_shared_camera_frame: Optional[Any] = None
_shared_frame_lock = threading.Lock()
# État du flux vidéo (True = flux actif, False = flux désactivé)
_camera_connected = False  # Par défaut, le flux vidéo est désactivé pour économiser les ressources


@main_bp.route("/camera/capture/photo", methods=["POST"])
@login_required
def capture_photo():
    """Capture une photo depuis la caméra"""
    try:
        import cv2  # type: ignore
        import time
        
        device_index = current_app.config.get("CAMERA_DEVICE_INDEX", 0)
        
        # Essayer d'abord d'utiliser la frame partagée du flux MJPEG
        frame = None
        with _shared_frame_lock:
            if _shared_camera_frame is not None:
                frame = _shared_camera_frame.copy()
        
        # Si pas de frame partagée disponible, essayer d'ouvrir la caméra directement
        if frame is None:
            # Utiliser un verrou pour éviter les conflits avec le flux MJPEG
            # Attendre jusqu'à 2 secondes pour obtenir le verrou
            if not _camera_lock.acquire(timeout=2.0):
                return jsonify({"error": "Caméra temporairement indisponible (utilisée par le flux vidéo)"}), 503
            
            try:
                # Essayer d'ouvrir la caméra avec plusieurs tentatives
                capture = None
                max_attempts = 3
                for attempt in range(max_attempts):
                    capture = cv2.VideoCapture(device_index)
                    if capture.isOpened():
                        # Attendre un peu pour que la caméra soit prête
                        time.sleep(0.2)
                        break
                    if capture:
                        capture.release()
                    if attempt < max_attempts - 1:
                        time.sleep(0.3)  # Attendre avant de réessayer
                
                if capture is None or not capture.isOpened():
                    return jsonify({"error": "Caméra indisponible"}), 500
                
                # Lire plusieurs frames pour s'assurer d'avoir une image valide
                success = False
                for _ in range(3):
                    ret, test_frame = capture.read()
                    if ret:
                        success = True
                        frame = test_frame
                        time.sleep(0.1)  # Petite pause entre les frames
                
                capture.release()
                
                if not success or frame is None:
                    return jsonify({"error": "Impossible de capturer l'image depuis la caméra"}), 500
            finally:
                _camera_lock.release()
        
        # Créer le dossier de captures s'il n'existe pas
        captures_folder = current_app.config.get("CAPTURES_FOLDER")
        if captures_folder:
            captures_dir = Path(captures_folder)
        else:
            static_folder = current_app.static_folder or "app/static"
            captures_dir = Path(static_folder) / "captures"
        captures_dir.mkdir(parents=True, exist_ok=True)
        
        # Générer un nom de fichier avec timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"photo_{timestamp}.jpg"
        filepath = captures_dir / filename
        
        # Sauvegarder l'image
        cv2.imwrite(str(filepath), frame)
        
        # Enregistrer dans le journal
        filepath_str = str(filepath)
        db.session.add(JournalEntry(
            level="info",
            message=f"📷 Photo capturée : {filename}",
            details={
                "filename": filename,
                "filepath": filepath_str,
                "directory": str(captures_dir),
                "type": "photo",
                "captured_by": current_user.username,
                "action": "photo_captured"
            }
        ))
        db.session.commit()
        
        return jsonify({
            "success": True,
            "filename": filename,
            "filepath": filepath_str,
            "url": url_for("main.serve_capture", filename=filename)
        })
    except Exception as e:
        current_app.logger.error(f"Erreur lors de la capture photo: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


_recording_threads: dict[str, threading.Thread] = {}
_recording_stop_flags: dict[str, bool] = {}


def _record_video_thread(recording_id: str, device_index: int, filepath: Path, filename: str, username: str):
    """Thread pour enregistrer la vidéo en continu"""
    try:
        import cv2  # type: ignore
        import time
        
        # Utiliser le verrou pour éviter les conflits avec le flux MJPEG
        # Attendre jusqu'à 5 secondes pour obtenir le verrou
        if not _camera_lock.acquire(timeout=5.0):
            _recording_stop_flags[recording_id] = True
            return
        
        try:
            capture = cv2.VideoCapture(device_index)
            if not capture.isOpened():
                _recording_stop_flags[recording_id] = True
                return
            
            # Obtenir les dimensions de la caméra
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = int(capture.get(cv2.CAP_PROP_FPS)) or 30
            
            # Créer le writer vidéo
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(str(filepath), fourcc, fps, (width, height))
            
            while not _recording_stop_flags.get(recording_id, False):
                success, frame = capture.read()
                if not success:
                    continue
                out.write(frame)
            
            # Libérer les ressources
            out.release()
            capture.release()
        finally:
            _camera_lock.release()
        
        # Enregistrer dans le journal
        from flask import current_app
        with current_app.app_context():
            filepath_str = str(filepath)
            captures_dir = filepath.parent
            db.session.add(JournalEntry(
                level="info",
                message=f"🎬 Vidéo enregistrée : {filename}",
                details={
                    "filename": filename,
                    "filepath": filepath_str,
                    "directory": str(captures_dir),
                    "type": "video",
                    "recorded_by": username,
                    "action": "video_recording_completed"
                }
            ))
            db.session.commit()
        
        # Nettoyer
        if recording_id in _recording_threads:
            del _recording_threads[recording_id]
        if recording_id in _recording_stop_flags:
            del _recording_stop_flags[recording_id]
    except Exception as e:
        from flask import current_app
        try:
            current_app.logger.error(f"Erreur dans le thread d'enregistrement: {e}", exc_info=True)
        except RuntimeError:
            print(f"Erreur dans le thread d'enregistrement: {e}")
        if recording_id in _recording_threads:
            del _recording_threads[recording_id]
        if recording_id in _recording_stop_flags:
            del _recording_stop_flags[recording_id]


@main_bp.route("/camera/capture/video/start", methods=["POST"])
@login_required
def start_video_recording():
    """Démarre l'enregistrement vidéo"""
    try:
        import cv2  # type: ignore
        
        device_index = current_app.config.get("CAMERA_DEVICE_INDEX", 0)
        
        # Vérifier rapidement que la caméra est disponible (sans verrou pour ne pas bloquer)
        import time
        test_capture = cv2.VideoCapture(device_index)
        if not test_capture.isOpened():
            test_capture.release()
            return jsonify({"error": "Caméra indisponible"}), 500
        test_capture.release()
        
        # Créer le dossier de captures s'il n'existe pas
        captures_folder = current_app.config.get("CAPTURES_FOLDER")
        if captures_folder:
            captures_dir = Path(captures_folder)
        else:
            static_folder = current_app.static_folder or "app/static"
            captures_dir = Path(static_folder) / "captures"
        captures_dir.mkdir(parents=True, exist_ok=True)
        
        # Générer un nom de fichier avec timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"video_{timestamp}.mp4"
        filepath = captures_dir / filename
        
        # Créer un ID unique pour cet enregistrement
        recording_id = f"recording_{timestamp}_{current_user.id}"
        
        # Initialiser le flag d'arrêt
        _recording_stop_flags[recording_id] = False
        
        # Démarrer le thread d'enregistrement
        thread = threading.Thread(
            target=_record_video_thread,
            args=(recording_id, device_index, filepath, filename, current_user.username),
            daemon=True
        )
        thread.start()
        _recording_threads[recording_id] = thread
        
        filepath_str = str(filepath)
        
        # Enregistrer le démarrage dans le journal
        db.session.add(JournalEntry(
            level="info",
            message=f"🎥 Démarrage enregistrement vidéo : {filename}",
            details={
                "filename": filename,
                "filepath": filepath_str,
                "directory": str(captures_dir),
                "type": "video",
                "status": "started",
                "recorded_by": current_user.username,
                "action": "video_recording_started"
            }
        ))
        db.session.commit()
        
        return jsonify({
            "success": True,
            "recording_id": recording_id,
            "filename": filename,
            "filepath": filepath_str
        })
    except Exception as e:
        current_app.logger.error(f"Erreur lors du démarrage de l'enregistrement: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@main_bp.route("/camera/capture/video/stop", methods=["POST"])
@login_required
def stop_video_recording():
    """Arrête l'enregistrement vidéo"""
    try:
        data = request.get_json()
        recording_id = data.get("recording_id")
        
        if not recording_id or recording_id not in _recording_stop_flags:
            return jsonify({"error": "Aucun enregistrement actif"}), 400
        
        # Signaler l'arrêt
        _recording_stop_flags[recording_id] = True
        
        # Attendre que le thread se termine (max 5 secondes)
        if recording_id in _recording_threads:
            _recording_threads[recording_id].join(timeout=5)
        
        # Enregistrer l'arrêt dans le journal
        # Le nom du fichier est dans le recording_id (format: recording_TIMESTAMP_userid)
        # On peut extraire le timestamp pour reconstruire le nom de fichier
        filename = None
        filepath_str = None
        try:
            parts = recording_id.split('_')
            if len(parts) >= 2:
                timestamp = '_'.join(parts[1:-1])  # Exclure 'recording' et l'userid
                filename = f"video_{timestamp}.mp4"
                captures_folder = current_app.config.get("CAPTURES_FOLDER")
                if captures_folder:
                    captures_dir = Path(captures_folder)
                else:
                    static_folder = current_app.static_folder or "app/static"
                    captures_dir = Path(static_folder) / "captures"
                filepath = captures_dir / filename
                filepath_str = str(filepath)
                
                db.session.add(JournalEntry(
                    level="info",
                    message=f"⏹️ Arrêt enregistrement vidéo : {filename}",
                    details={
                        "filename": filename,
                        "filepath": filepath_str,
                        "directory": str(captures_dir),
                        "type": "video",
                        "status": "stopped",
                        "recorded_by": current_user.username,
                        "action": "video_recording_stopped"
                    }
                ))
                db.session.commit()
        except Exception as e:
            current_app.logger.warning(f"Impossible d'enregistrer l'arrêt dans le journal: {e}")
        
        return jsonify({
            "success": True,
            "filename": filename,
            "filepath": filepath_str
        })
    except Exception as e:
        current_app.logger.error(f"Erreur lors de l'arrêt de l'enregistrement: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@main_bp.route("/camera/capture/delete/<path:filename>", methods=["POST"])
@login_required
def delete_capture(filename: str):
    """Supprime une capture (photo ou vidéo)"""
    try:
        import os
        
        captures_folder = current_app.config.get("CAPTURES_FOLDER")
        if captures_folder:
            captures_dir = Path(captures_folder)
        else:
            static_folder = current_app.static_folder or "app/static"
            captures_dir = Path(static_folder) / "captures"
        
        # Sécuriser le nom de fichier pour éviter les accès en dehors du dossier
        safe_filename = os.path.basename(filename)
        filepath = captures_dir / safe_filename
        
        if not filepath.exists():
            return jsonify({"error": "Fichier introuvable"}), 404
        
        # Vérifier que le fichier est bien dans le dossier de captures
        try:
            filepath.resolve().relative_to(captures_dir.resolve())
        except ValueError:
            return jsonify({"error": "Accès non autorisé"}), 403
        
        # Supprimer le fichier
        filepath.unlink()
        
        # Enregistrer dans le journal
        db.session.add(JournalEntry(
            level="info",
            message=f"🗑️ Capture supprimée : {safe_filename}",
            details={
                "filename": safe_filename,
                "filepath": str(filepath),
                "deleted_by": current_user.username,
                "action": "capture_deleted"
            }
        ))
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Capture supprimée avec succès"
        })
    except Exception as e:
        current_app.logger.error(f"Erreur lors de la suppression de la capture: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@main_bp.route("/camera/captures/<path:filename>")
@login_required
def serve_capture(filename: str):
    """Sert les fichiers de capture depuis le dossier de captures"""
    try:
        import os
        
        captures_folder = current_app.config.get("CAPTURES_FOLDER")
        if captures_folder:
            captures_dir = Path(captures_folder)
        else:
            static_folder = current_app.static_folder or "app/static"
            captures_dir = Path(static_folder) / "captures"
        
        # Sécuriser le nom de fichier pour éviter les accès en dehors du dossier
        safe_filename = os.path.basename(filename)
        filepath = captures_dir / safe_filename
        
        if not filepath.exists():
            return "Fichier introuvable", 404
        
        # Vérifier que le fichier est bien dans le dossier de captures
        try:
            filepath.resolve().relative_to(captures_dir.resolve())
        except ValueError:
            return "Accès non autorisé", 403
        
        return send_from_directory(captures_dir, safe_filename)
    except Exception as e:
        current_app.logger.error(f"Erreur lors du service de la capture: {e}", exc_info=True)
        return "Erreur", 500


@main_bp.route("/camera/stream/toggle", methods=["POST"])
@login_required
def camera_stream_toggle():
    """Active ou désactive le flux vidéo de la caméra"""
    global _camera_connected
    
    try:
        # Le token CSRF est validé automatiquement par Flask-WTF via le header X-CSRFToken
        data = request.get_json() or {}
        action = data.get("action", "toggle")
        
        if action == "start":
            _camera_connected = True
            message = "Flux vidéo activé"
        elif action == "stop":
            _camera_connected = False
            # Libérer la frame partagée si elle existe
            with _shared_frame_lock:
                _shared_camera_frame = None
            message = "Flux vidéo désactivé"
        else:  # toggle
            _camera_connected = not _camera_connected
            if not _camera_connected:
                # Libérer la frame partagée si elle existe
                with _shared_frame_lock:
                    _shared_camera_frame = None
            message = "Flux vidéo activé" if _camera_connected else "Flux vidéo désactivé"
        
        current_app.logger.info(f"État flux vidéo modifié: {message} (utilisateur: {current_user.username})")
        
        return jsonify({
            "success": True,
            "streaming": _camera_connected,
            "message": message
        })
    except Exception as e:
        current_app.logger.error(f"Erreur lors de l'activation/désactivation du flux vidéo: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@main_bp.route("/camera/status", methods=["GET"])
@login_required
def camera_status():
    """Récupère l'état du flux vidéo de la caméra"""
    global _camera_connected
    return jsonify({
        "streaming": _camera_connected,
        "available": current_app.config.get("CAMERA_AVAILABLE", False)
    })


@main_bp.route("/parametres", methods=["GET", "POST"])
@login_required
def settings():
    if current_user.role != "admin":
        flash("Accès réservé à l'administrateur.", "danger")
        return redirect(url_for("main.dashboard"))
    form = SettingForm()
    form.key.validators = []
    form.value.validators = []
    settings_list = Setting.query.order_by(Setting.key.asc()).all()
    settings_map = {setting.key: setting for setting in settings_list}

    initialized = False
    for key, default_value in ((item["key"], item["default"]) for group in HARDWARE_SETTING_GROUPS for item in group["items"]):
        if key not in settings_map:
            new_setting = Setting(key=key, value=default_value)
            db.session.add(new_setting)
            db.session.add(
                JournalEntry(
                    level="info",
                    message=f"Paramètre initialisé : {key}",
                    details={"value": default_value, "source": "default", "category": "hardware"},
                )
            )
            initialized = True

    if initialized:
        db.session.commit()
        settings_list = Setting.query.order_by(Setting.key.asc()).all()
        settings_map = {setting.key: setting for setting in settings_list}

    if request.method == "POST" and request.form.get("refresh_hardware") == "1":
        flash("Diagnostic matériel relancé.", "info")
        return redirect(url_for("main.settings"))

    if form.validate_on_submit():
        submitted = request.form.to_dict(flat=True)
        updated_items = []
        new_poll_interval = None
        lcd_display_seconds_updated = False
        for key, value in submitted.items():
            if key in {"csrf_token", "refresh_hardware", "submit"} or not key.startswith("setting__"):
                continue
            setting_key = key.split("setting__", 1)[1]
            setting = Setting.query.filter_by(key=setting_key).first()
            before_value = setting.value if setting else None
            if not setting:
                setting = Setting(key=setting_key)
                db.session.add(setting)
            cleaned_value = value
            if setting_key == "Sensor_Poll_Interval_Minutes":
                try:
                    interval_candidate = int(str(value).strip())
                    if interval_candidate < 1 or interval_candidate > 1440:
                        raise ValueError
                    cleaned_value = str(interval_candidate)
                    new_poll_interval = interval_candidate
                except ValueError:
                    flash("Intervalle de collecte invalide (entier entre 1 et 1440 minutes).", "danger")
                    return redirect(url_for("main.settings"))
            elif setting_key == "LCD_Page_Display_Seconds":
                try:
                    seconds_candidate = float(str(value).strip())
                    if seconds_candidate < 1 or seconds_candidate > 60:
                        raise ValueError
                    cleaned_value = str(seconds_candidate)
                    lcd_display_seconds_updated = True
                except ValueError:
                    flash("Temps d'affichage LCD invalide (nombre entre 1 et 60 secondes).", "danger")
                    return redirect(url_for("main.settings"))
            setting.value = cleaned_value
            updated_items.append((setting_key, before_value, cleaned_value))

        if updated_items:
            for setting_key, before_value, after_value in updated_items:
                db.session.add(
                    JournalEntry(
                        level="info",
                        message=f"Paramètre mis à jour : {setting_key}",
                        details={"before": before_value, "after": after_value},
                    )
                )
        db.session.commit()
        # Invalider le cache des settings après modification
        invalidate_settings_cache()
        app_obj = current_app._get_current_object()
        if new_poll_interval is not None:
            if app_obj.config.get("SENSOR_POLL_ENABLED", True):
                schedule_sensor_poll(app_obj, new_poll_interval)
            else:
                app_obj.config["SENSOR_POLL_INTERVAL_MINUTES"] = new_poll_interval
        if lcd_display_seconds_updated:
            # Invalider le cache et mettre à jour le scheduler LCD avec le nouveau délai
            invalidate_lcd_display_seconds_cache()
            schedule_lcd_auto_scroll(app_obj, force_refresh=True)
        flash("Paramètres enregistrés.", "success")
        return redirect(url_for("main.settings"))

    hardware_groups = []
    hardware_keys = set()
    for group in HARDWARE_SETTING_GROUPS:
        items = []
        grouped_entries: dict[str, dict[str, object]] = {}
        for item in group["items"]:
            setting_obj = settings_map.get(item["key"])
            payload = {
                **item,
                "value": setting_obj.value if setting_obj else item["default"],
                "updated_at": setting_obj.updated_at if setting_obj else None,
            }
            group_id = item.get("group")
            if group_id:
                bucket = grouped_entries.setdefault(
                    group_id,
                    {
                        "group_id": group_id,
                        "is_group": True,
                        "title": item.get("group_title"),
                        "subtitle": item.get("group_subtitle"),
                        "entries": [],
                    },
                )
                if not bucket.get("title") and item.get("group_title"):
                    bucket["title"] = item.get("group_title")
                if not bucket.get("subtitle") and item.get("group_subtitle"):
                    bucket["subtitle"] = item.get("group_subtitle")
                bucket["entries"].append(payload)
            else:
                items.append(payload)
            hardware_keys.add(item["key"])
        items.extend(grouped_entries.values())
        hardware_groups.append(
            {
                "id": group["id"],
                "title": group["title"],
                "subtitle": group["subtitle"],
                "parameters": items,
            }
        )

    def _get_int_value(key: str, fallback: int) -> int:
        value = settings_map.get(key).value if settings_map.get(key) else fallback
        try:
            return int(str(value).strip())
        except (ValueError, TypeError, AttributeError):
            return fallback

    relay_pins = [
        _get_int_value("Relay_Ch1", 26),
        _get_int_value("Relay_Ch2", 20),
        _get_int_value("Relay_Ch3", 21),
    ]

    hardware_status = build_hardware_overview(
        relay_pins,
        lcd_enabled=current_app.config.get("LCD_ENABLED", False),
    )
    _sync_runtime_device_flags(hardware_status)
    configured_values = {
        "relays": ", ".join(str(pin) for pin in relay_pins),
        "ds18b20": settings_map.get("Sensor_DS18B20_Interface").value if settings_map.get("Sensor_DS18B20_Interface") else "—",
        "am2315": settings_map.get("Sensor_AM2315_Type").value if settings_map.get("Sensor_AM2315_Type") else "—",
        "am2315_address": settings_map.get("Sensor_AM2315_Address").value if settings_map.get("Sensor_AM2315_Address") else "—",
    }

    for status in hardware_status:
        if status["id"] == "relays":
            status["configured"] = f"GPIO configurés : {configured_values['relays']}"
        elif status["id"] == "ds18b20":
            status["configured"] = f"Interface actuelle : {configured_values['ds18b20']}"
        elif status["id"] == "am2315":
            status["configured"] = f"Capteur : {configured_values['am2315']} @ {configured_values['am2315_address']}"
        elif status["id"] == "lcd":
            lcd_flag = "activé" if current_app.config.get("LCD_ENABLED", False) else "désactivé"
            status["configured"] = f"LCD {lcd_flag}"

    return render_template(
        "dashboard/settings.html",
        form=form,
        hardware_groups=hardware_groups,
        hardware_status=hardware_status,
    )


@main_bp.route("/journal")
@login_required
def journal():
    if current_user.role != "admin":
        flash("Accès réservé à l'administrateur.", "danger")
        return redirect(url_for("main.dashboard"))
    search = request.args.get("q", "").strip()
    level = request.args.get("level", "")
    sort = request.args.get("sort", "recent")
    
    # Récupérer la date sélectionnée (par défaut aujourd'hui)
    now_local = datetime.now()
    today = now_local.date()
    selected_date_str = request.args.get("date", today.isoformat())
    try:
        selected_date = datetime.fromisoformat(selected_date_str).date()
    except (ValueError, AttributeError):
        selected_date = today
    
    page = max(int(request.args.get("page", 1)), 1)
    per_page = max(min(int(request.args.get("per_page", 100)), 100), 5)

    query = JournalEntry.query

    if search:
        like = f"%{search}%"
        query = query.filter(JournalEntry.message.ilike(like))

    if level in {"info", "warning", "danger"}:
        query = query.filter_by(level=level)

    if sort == "oldest":
        query = query.order_by(JournalEntry.created_at.asc())
    else:
        query = query.order_by(JournalEntry.created_at.desc())

    # Filtrer pour le jour sélectionné uniquement (de 00:00:00 à 23:59:59 en heure locale)
    # Convertir la date locale en UTC pour le filtrage
    # Calculer l'offset entre UTC et l'heure locale
    now_utc = datetime.utcnow()
    now_local = datetime.now()
    offset_seconds = (now_local - now_utc).total_seconds()
    
    # Créer les limites du jour en heure locale
    start_of_day_local = datetime.combine(selected_date, datetime.min.time())
    end_of_day_local = datetime.combine(selected_date, datetime.max.time())
    
    # Convertir en UTC en soustrayant l'offset
    start_of_day_utc = start_of_day_local - timedelta(seconds=offset_seconds)
    end_of_day_utc = end_of_day_local - timedelta(seconds=offset_seconds)
    
    query = query.filter(JournalEntry.created_at >= start_of_day_utc)
    query = query.filter(JournalEntry.created_at <= end_of_day_utc)
    
    # Récupérer tous les événements du jour (sans pagination)
    entries = query.all()
    
    # Créer une pagination factice pour la compatibilité
    class FakePagination:
        def __init__(self, items, total):
            self.items = items
            self.total = total
            self.page = 1
            self.pages = 1
            self.per_page = len(items)
            self.has_prev = False
            self.has_next = False
            self.prev_num = None
            self.next_num = None
    pagination = FakePagination(entries, len(entries))
    query_args = request.args.to_dict()
    relay_label_map = get_relay_labels()
    sensor_alias_cache: dict[str, str] = {}
    detailed_entries = []
    for entry in entries:
        detail = entry.details or {}

        message = entry.message
        if message.lower().startswith("commande relais ch"):
            channel = detail.get("channel")
            relay_name = relay_label_map.get(channel, f"Relais {channel}") if channel else "Relais"
            state = detail.get("command") or detail.get("result", {}).get("state")
            state_label = state.upper() if isinstance(state, str) else None
            parts = ["Commande", relay_name]
            if state_label:
                parts.append(state_label)
            message = " • ".join(parts)

        formatted = {
            "level": entry.level,
            "message": message,
            "timestamp": entry.created_at,
            "detail": detail,
            "actors": detail.get("actors") if isinstance(detail.get("actors"), list) else None,
            "metadata": None,
            "compact_summary": message,
        }

        metadata_items = []
        if isinstance(detail, dict):
            for key, value in detail.items():
                if key == "actors":
                    continue
                label = key.replace("_", " ").title()
                display_value = value
                if key == "channel":
                    try:
                        channel_int = int(value)
                    except (TypeError, ValueError):
                        channel_int = None
                    if channel_int is not None:
                        display_value = relay_label_map.get(channel_int, f"Relais {channel_int}")
                    label = "Relais"
                elif key == "sensor_type":
                    sensor_key = str(value).lower()
                    if sensor_key not in sensor_alias_cache:
                        sensor_alias_cache[sensor_key] = get_sensor_display_name(sensor_key)
                    alias = sensor_alias_cache.get(sensor_key) or sensor_key.upper()
                    display_value = alias
                    label = "Capteur"
                elif key == "sensor_id":
                    display_value = str(value).upper()
                    label = "Identifiant Capteur"
                elif key == "sensor_metric":
                    display_value = METRIC_LABELS.get(str(value), str(value).title())
                    label = "Mesure"
                elif key == "result" and isinstance(value, dict):
                    status = value.get("status")
                    info_parts = []
                    if status:
                        info_parts.append(f"Statut : {status}")
                    message_result = value.get("message")
                    if message_result:
                        info_parts.append(message_result)
                    display_value = " | ".join(info_parts) if info_parts else json.dumps(value, ensure_ascii=False)
                    label = "Résultat"
                elif isinstance(value, dict):
                    display_value = json.dumps(value, ensure_ascii=False)

                metadata_items.append({
                    "label": label,
                    "value": display_value,
                })
        if metadata_items:
            formatted["metadata"] = metadata_items

        detailed_entries.append(formatted)

    # Formater les timestamps en heure locale pour chaque entrée
    for entry in detailed_entries:
        local_timestamp = utc_to_local(entry["timestamp"])
        entry["time_label"] = local_timestamp.strftime("%H:%M")

    # Utiliser l'heure locale pour déterminer aujourd'hui et hier
    yesterday = today - timedelta(days=1)
    
    # Créer le label du jour sélectionné
    day_label = selected_date.strftime("%A %d %B %Y").capitalize()
    if selected_date == today:
        day_label = "Aujourd'hui"
    elif selected_date == yesterday:
        day_label = "Hier"

    # Créer les URLs pour la pagination jour précédent/suivant
    prev_day = selected_date - timedelta(days=1)
    next_day = selected_date + timedelta(days=1)
    
    # Vérifier si le jour suivant est dans le futur
    if next_day > today:
        next_day = None
    
    query_args = request.args.to_dict()
    prev_day_url = None
    next_day_url = None
    
    if prev_day:
        prev_params = {k: v for k, v in query_args.items() if k not in {"date", "page"}}
        prev_params["date"] = prev_day.isoformat()
        prev_day_url = url_for("main.journal", **prev_params)
    
    if next_day:
        next_params = {k: v for k, v in query_args.items() if k not in {"date", "page"}}
        next_params["date"] = next_day.isoformat()
        next_day_url = url_for("main.journal", **next_params)

    compact = request.args.get("compact", "0") == "1"
    filters_active = bool(search or level)
    reset_filters_url = url_for("main.journal", date=selected_date.isoformat())
    toggle_args = query_args.copy()
    toggle_args["compact"] = "0" if compact else "1"
    toggle_compact_url = url_for("main.journal", **toggle_args)
    today_view_url = url_for("main.journal", date=today.isoformat())

    return render_template(
        "dashboard/journal.html",
        entries=detailed_entries,
        selected_date=selected_date.isoformat(),
        day_label=day_label,
        filters={
            "q": search,
            "level": level,
            "compact": compact,
        },
        filters_active=filters_active,
        stats={
            "page_count": len(detailed_entries),
            "total": pagination.total,
        },
        compact=compact,
        reset_filters_url=reset_filters_url,
        toggle_compact_url=toggle_compact_url,
        today_view_url=today_view_url,
        prev_day_url=prev_day_url,
        next_day_url=next_day_url,
    )


@main_bp.route("/journal/purge", methods=["POST"])
@login_required
def journal_purge():
    if current_user.role != "admin":
        flash("Accès réservé à l'administrateur.", "danger")
        return redirect(url_for("main.dashboard"))

    before_str = request.form.get("before")
    if not before_str:
        flash("Merci de sélectionner une date avant suppression.", "warning")
        return redirect(url_for("main.journal"))

    try:
        before_date = datetime.fromisoformat(before_str)
        threshold = datetime.combine(before_date.date(), datetime.max.time())
    except ValueError:
        flash("Date invalide.", "danger")
        return redirect(url_for("main.journal"))

    query = JournalEntry.query.filter(JournalEntry.created_at <= threshold)
    count = query.count()
    if count == 0:
        flash("Aucune entrée à supprimer pour cette date.", "info")
        return redirect(url_for("main.journal"))

    query.delete(synchronize_session=False)
    db.session.add(
        JournalEntry(
            level="warning",
            message="Purge du journal",
            details={
                "deleted_before": before_str,
                "deleted_count": count,
                "performed_by": current_user.username,
            },
        )
    )
    db.session.commit()
    flash(f"{count} entrée(s) supprimée(s) du journal.", "success")
    return redirect(url_for("main.journal"))


@main_bp.route("/actions/purge-mesures", methods=["POST"])
@login_required
def purge_sensor_readings():
    if current_user.role != "admin":
        flash("Accès réservé à l'administrateur.", "danger")
        return redirect(url_for("main.dashboard"))

    # Supprimer toutes les mesures jusqu'à aujourd'hui (avant minuit aujourd'hui)
    today = datetime.utcnow().date()
    threshold = datetime.combine(today, datetime.min.time())

    query = SensorReading.query.filter(SensorReading.created_at < threshold)
    count = query.count()
    
    if count == 0:
        flash("Aucune mesure à supprimer.", "info")
        return redirect(url_for("main.dashboard"))

    query.delete(synchronize_session=False)
    db.session.add(
        JournalEntry(
            level="warning",
            message="Purge des mesures capteurs",
            details={
                "deleted_before": threshold.isoformat(),
                "deleted_count": count,
                "performed_by": current_user.username,
            },
        )
    )
    db.session.commit()
    flash(f"{count} mesure(s) supprimée(s) (jusqu'à aujourd'hui).", "success")
    return redirect(url_for("main.dashboard"))


@main_bp.route("/actions/collecte-manuelle", methods=["POST"])
@login_required
def manual_sensor_collect():
    if current_user.role != "admin":
        flash("Accès réservé à l’administrateur.", "danger")
        return redirect(url_for("main.dashboard"))

    next_page = request.form.get("next") or "dashboard"
    if next_page == "charts":
        redirect_endpoint = "main.charts"
    else:
        redirect_endpoint = "main.dashboard"

    trigger_time = datetime.utcnow().isoformat()
    try:
        collect_sensor_readings(current_app._get_current_object())
        db.session.add(
            JournalEntry(
                level="info",
                message="Collecte manuelle des capteurs",
                details={
                    "triggered_by": current_user.username,
                    "source": "dashboard_manual_trigger",
                    "timestamp": trigger_time,
                },
            )
        )
        db.session.commit()
        flash("Collecte des sondes et évaluation des règles lancées.", "success")
    except Exception as exc:  # pragma: no cover - dépend matériel
        current_app.logger.exception("Collecte manuelle échouée: %s", exc)
        db.session.rollback()
        db.session.add(
            JournalEntry(
                level="danger",
                message="Échec collecte manuelle des capteurs",
                details={
                    "error": str(exc),
                    "triggered_by": current_user.username,
                    "timestamp": trigger_time,
                },
            )
        )
        db.session.commit()
        flash("Impossible de lancer la collecte. Consultez le journal.", "danger")

    return redirect(url_for(redirect_endpoint))


@main_bp.route("/affichage-lcd", methods=["GET", "POST"])
@login_required
def lcd_preview():
    if current_user.role != "admin":
        flash("Accès réservé à l’administrateur.", "danger")
        return redirect(url_for("main.dashboard"))

    push_requested = request.method == "POST"
    snapshot = refresh_lcd_display(push=push_requested)
    if push_requested:
        if snapshot.get("push_success"):
            flash("Afficheur LCD mis à jour.", "success")
        else:
            message = snapshot.get("push_error") or "Impossible de contacter l'écran LCD."
            flash(message, "warning")

    return render_template("dashboard/lcd_preview.html", snapshot=snapshot)


@main_bp.route("/profil", methods=["GET", "POST"])
@login_required
def profile():
    form = ProfileForm()
    if request.method == "GET":
        form.title.data = getattr(current_user, 'title', None)
        form.first_name.data = getattr(current_user, 'first_name', None)
        form.last_name.data = getattr(current_user, 'last_name', None)
        form.username.data = current_user.username
        form.email.data = current_user.email
        # Utiliser getattr pour gérer les cas où les colonnes n'existent pas encore dans la DB
        form.street.data = getattr(current_user, 'street', None)
        form.postal_code.data = getattr(current_user, 'postal_code', None)
        form.city.data = getattr(current_user, 'city', None)
        form.country.data = getattr(current_user, 'country', None)
        form.phone.data = getattr(current_user, 'phone', None)
        form.twofa_enabled.data = current_user.twofa_enabled

    if form.validate_on_submit():
        if (
            form.username.data != current_user.username
            and User.query.filter_by(username=form.username.data).first()
        ):
            flash("Ce nom d'utilisateur est déjà utilisé par un autre compte. Veuillez en choisir un autre.", "warning")
            return render_template("dashboard/profile.html", form=form)
        elif (
            form.email.data
            and form.email.data.strip()
            and form.email.data.strip() != (current_user.email or "").strip()
            and User.query.filter_by(email=form.email.data.strip()).first()
        ):
            flash(f"L'adresse email « {form.email.data.strip()} » est déjà utilisée par un autre compte. Veuillez utiliser une autre adresse email.", "warning")
            return render_template("dashboard/profile.html", form=form)
        else:
            if form.password.data and (not form.confirm_password.data or form.password.data != form.confirm_password.data):
                flash("Merci de confirmer le nouveau mot de passe.", "danger")
                return render_template("dashboard/profile.html", form=form)
            if form.twofa_enabled.data and not form.email.data and not current_user.email:
                flash("Un email valide est requis pour activer la 2FA.", "danger")
                return render_template("dashboard/profile.html", form=form)
            twofa_before = current_user.twofa_enabled
            original_state = {
                "username": current_user.username,
                "email": current_user.email,
                "twofa_enabled": current_user.twofa_enabled,
            }
            if form.remove_avatar.data:
                delete_avatar(current_user.avatar_filename)
                current_user.avatar_filename = None
            elif form.avatar.data:
                delete_avatar(current_user.avatar_filename)
                current_user.avatar_filename = save_avatar(form.avatar.data)
            current_user.title = form.title.data.strip() if form.title.data else None
            current_user.first_name = form.first_name.data.strip() if form.first_name.data else None
            current_user.last_name = form.last_name.data.strip() if form.last_name.data else None
            current_user.username = form.username.data
            current_user.email = form.email.data.strip() if form.email.data else None
            current_user.street = form.street.data.strip() if form.street.data else None
            current_user.postal_code = form.postal_code.data.strip() if form.postal_code.data else None
            current_user.city = form.city.data.strip() if form.city.data else None
            current_user.country = form.country.data.strip() if form.country.data else None
            current_user.phone = form.phone.data.strip() if form.phone.data else None
            if form.twofa_enabled.data:
                current_user.twofa_enabled = True
            else:
                current_user.twofa_enabled = False
                current_user.twofa_code_hash = None
                current_user.twofa_code_sent_at = None
                current_user.twofa_trusted_token_hash = None
                current_user.twofa_trusted_created_at = None
            if form.password.data:
                current_user.set_password(form.password.data)
            db.session.add(current_user)
            db.session.add(
                JournalEntry(
                    level="info",
                    message=f"Profil mis à jour pour {current_user.username}",
                    details={
                        "user_id": current_user.id,
                        "modified_by": current_user.username,
                        "changes": build_changes(
                            original_state,
                            {
                                "username": current_user.username,
                                "email": current_user.email,
                                "twofa_enabled": current_user.twofa_enabled,
                            },
                            list(original_state.keys()),
                        ),
                    },
                )
            )
            if twofa_before != current_user.twofa_enabled:
                status = "activée" if current_user.twofa_enabled else "désactivée"
                db.session.add(
                    JournalEntry(
                        level="info",
                        message=f"2FA {status} pour {current_user.username}",
                        details={"user_id": current_user.id},
                    )
                )
                create_notification(
                    user=current_user,
                    title="Double authentification",
                    message=f"La 2FA a été {status} sur votre compte.",
                    level="success" if current_user.twofa_enabled else "info",
                    persistent=True,
                    action_endpoint="main.profile",
                )
            db.session.commit()
            # Expirer l'objet pour forcer le rechargement depuis la DB lors de la prochaine requête
            db.session.expire(current_user)
            flash("Profil mis à jour.", "success")
            return redirect(url_for("main.profile"))

    return render_template("dashboard/profile.html", form=form)


@main_bp.route("/notifications/read", methods=["POST"])
@login_required
def notifications_mark_read():
    ids = request.json.get("ids") if request.is_json else None  # type: ignore[attr-defined]
    query = Notification.query.filter(
        (Notification.user_id == current_user.id)
        | (Notification.audience == "global")
        | ((Notification.audience == "admin") & (current_user.role == "admin"))
    )
    if ids:
        query = query.filter(Notification.id.in_(ids))
    for notif in query:
        notif.read = True
        db.session.add(notif)
    db.session.commit()
    return jsonify({"status": "ok"})


@main_bp.route("/notifications/clear", methods=["POST"])
@login_required
def notifications_clear():
    payload = request.get_json(silent=True) or {}
    ids = payload.get("ids")

    query = Notification.query.filter(
        (Notification.user_id == current_user.id)
        | (Notification.audience == "global")
        | ((Notification.audience == "admin") & (current_user.role == "admin"))
    )

    if ids:
        try:
            ids = [int(_id) for _id in ids]
        except (TypeError, ValueError):
            ids = []
        if ids:
            query = query.filter(Notification.id.in_(ids))

    notifications = query.all()
    cleared_ids: list[int] = []
    for notif in notifications:
        cleared_ids.append(notif.id)
        if notif.user_id == current_user.id:
            db.session.delete(notif)
        else:
            notif.read = True
            db.session.add(notif)

    db.session.commit()
    return jsonify({"status": "ok", "cleared": cleared_ids})


@main_bp.route("/icon/<int:size>.png", endpoint="generate_icon")
def generate_icon(size: int):
    """Génère une icône avec fond blanc pour iOS/iPad."""
    try:
        from PIL import Image
        
        from pathlib import Path
        logo_path = Path(current_app.static_folder) / "img" / "logo.png"
        if not logo_path.exists():
            return send_from_directory(current_app.static_folder, "img/logo.png"), 404
        
        # Ouvrir le logo
        logo = Image.open(logo_path)
        
        # Créer une image avec fond blanc
        icon = Image.new("RGB", (size, size), color="white")
        
        # Calculer la taille et position pour centrer le logo
        logo_size = min(size - 40, logo.width, logo.height)  # Marge de 20px de chaque côté
        logo_resized = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
        
        # Centrer le logo sur le fond blanc
        x = (size - logo_size) // 2
        y = (size - logo_size) // 2
        
        # Coller le logo sur le fond blanc (gérer la transparence)
        if logo.mode == "RGBA":
            icon.paste(logo_resized, (x, y), logo_resized)
        else:
            icon.paste(logo_resized, (x, y))
        
        # Retourner l'image
        from io import BytesIO
        output = BytesIO()
        icon.save(output, format="PNG")
        output.seek(0)
        
        return current_app.response_class(
            output.read(),
            mimetype="image/png",
            headers={"Cache-Control": "public, max-age=31536000"}
        )
    except ImportError:
        # Si PIL n'est pas disponible, servir le logo original
        return send_from_directory(current_app.static_folder, "img/logo.png")
    except Exception as exc:
        current_app.logger.error(f"Erreur génération icône {size}x{size}: {exc}")
        return send_from_directory(current_app.static_folder, "img/logo.png")


@main_bp.route("/manifest.json")
def manifest():
    manifest_data = {
        "name": "Dashboard Automatisation",
        "short_name": "Dashboard",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#0f172a",
        "lang": "fr",
        "icons": [
            {
                "src": url_for("main.generate_icon", size=180, _external=True),
                "sizes": "180x180",
                "type": "image/png",
                "purpose": "any"
            },
            {
                "src": url_for("main.generate_icon", size=192, _external=True),
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any"
            },
            {
                "src": url_for("main.generate_icon", size=256, _external=True),
                "sizes": "256x256",
                "type": "image/png",
                "purpose": "any"
            },
            {
                "src": url_for("main.generate_icon", size=512, _external=True),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any"
            }
        ]
    }
    return jsonify(manifest_data)


@main_bp.route("/api/server-time")
@login_required
def server_time():
    """Retourne l'heure actuelle du serveur (Raspberry Pi) en heure locale"""
    # Utiliser datetime.now() pour obtenir l'heure locale du système (Raspberry Pi)
    server_now_local = datetime.now()
    server_now_utc = datetime.utcnow()
    
    return jsonify({
        "timestamp": server_now_local.isoformat(),
        "utc": server_now_utc.isoformat(),
        "local": server_now_local.strftime("%H:%M:%S"),
        "date": server_now_local.strftime("%d/%m/%Y"),
        "timezone_offset": (server_now_local - server_now_utc).total_seconds() / 3600,  # Offset en heures
    })


@main_bp.route("/service-worker.js")
def service_worker():
    response = current_app.response_class(
        current_app.open_resource("static/js/service-worker.js").read(),
        mimetype="application/javascript",
    )
    response.cache_control.max_age = 0
    return response


@main_bp.errorhandler(404)
def not_found(error):  # type: ignore[override]
    return render_template("errors/404.html"), 404


@main_bp.errorhandler(500)
def internal_error(error):  # type: ignore[override]
    db.session.rollback()
    return render_template("errors/500.html"), 500
