from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Generator, Tuple

from flask import (Blueprint, Response, current_app, flash, jsonify, redirect,
                   render_template, request, url_for)
from flask_login import current_user, login_required
from sqlalchemy import func
from urllib.parse import urlencode

from . import db, schedule_sensor_poll
from .forms import AutomationRuleForm, ProfileForm, SettingForm
from .models import AutomationRule, JournalEntry, Notification, SensorReading, Setting, User
from .services import create_notification
from .tasks import collect_sensor_readings
from .utils import build_changes, build_hardware_overview, delete_avatar, save_avatar
from .automation_engine import parse_trigger
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


def get_setting_value(key: str, default: str) -> str:
    setting = Setting.query.filter_by(key=key).first()
    if setting and setting.value:
        return setting.value
    return default


def get_sensor_display_name(sensor_type: str) -> str:
    key = SENSOR_NAME_KEYS.get(sensor_type)
    default = SENSOR_LABELS.get(sensor_type, sensor_type.upper())
    if not key:
        return default
    return get_setting_value(key, default)


def _extract_relay_action_description(line: str) -> str:
    try:
        _, command = line.split(":", 1)
        channel_part, state_part = command.split("=", 1)
        channel = channel_part.strip()
        state = state_part.strip().lower()
        state_map = {"on": "Allumer", "off": "Éteindre", "toggle": "Basculer"}
        label = state_map.get(state, state.upper())
        return f"Relais {channel} → {label}"
    except Exception:
        return line.strip()


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


def build_trigger_expression(sensor_type: str, metric: str, sensor_id: str | None, operator: str, threshold) -> str:
    base = f"sensor:{sensor_type}.{metric}"
    if sensor_id:
        base += f"@{sensor_id}"
    return f"{base} {operator} {threshold}"


def build_action_expression(channel: int, command: str) -> str:
    return f"relay:{channel}={command}"


def parse_relay_action(action: str) -> tuple[int | None, str | None]:
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
                "description": "Fréquence d’échantillonnage des capteurs (1 à 1440 minutes).",
            },
        ],
    },
]


def _camera_stream() -> Generator[bytes, None, None]:
    if cv2 is None:
        current_app.logger.error("OpenCV n’est pas installé pour le streaming caméra.")
        raise RuntimeError("Camera indisponible")

    capture = cv2.VideoCapture(0)
    if not capture.isOpened():
        current_app.logger.error("Impossible d’ouvrir la caméra USB.")
        raise RuntimeError("Camera indisponible")

    try:
        while True:
            success, frame = capture.read()
            if not success:
                continue

            ret, buffer = cv2.imencode(".jpg", frame)
            if not ret:
                continue

            frame_bytes = buffer.tobytes()
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
    finally:
        capture.release()


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

    def build_sensor_highlight(
        *,
        sensor_type: str,
        metric: str,
        title: str,
        subtitle: str | None,
        default_unit: str,
        icon: str,
    ) -> dict[str, object]:
        reading = (
        SensorReading.query.filter(
                SensorReading.sensor_type == sensor_type,
                SensorReading.metric == metric,
            )
            .order_by(SensorReading.created_at.desc())
            .first()
        )
        card: dict[str, object] = {
            "title": title,
            "subtitle": subtitle,
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
            card["last_seen_text"] = reading.created_at.strftime("%d/%m/%Y %H:%M")
            card["last_seen_iso"] = reading.created_at.isoformat()
            if reading.sensor_id and not subtitle:
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

    sensor_highlights = [
        build_sensor_highlight(
            sensor_type="ds18b20",
            metric="temperature",
            title="Température DS18B20",
            subtitle=get_sensor_display_name("ds18b20"),
            default_unit="°C",
            icon="temperature",
        ),
        build_sensor_highlight(
            sensor_type="am2315",
            metric="temperature",
            title="Température AM2315",
            subtitle=get_sensor_display_name("am2315"),
            default_unit="°C",
            icon="temperature",
        ),
        build_sensor_highlight(
            sensor_type="am2315",
            metric="humidity",
            title="Humidité AM2315",
            subtitle=get_sensor_display_name("am2315"),
            default_unit="%",
            icon="humidity",
        ),
    ]

    # Relais
    relay_pins = get_configured_relay_pins()
    relay_labels = get_relay_labels()
    relay_states = get_relay_states()
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

    climate_readings = (
        SensorReading.query.filter(
            SensorReading.metric.in_(["temperature", "humidity"]),
            SensorReading.created_at >= period_start,
        )
        .order_by(SensorReading.created_at.asc())
        .all()
    )

    series_map: dict[str, dict[str, object]] = {}
    for reading in climate_readings:
        if reading.value is None:
            continue
        timestamp = reading.created_at.isoformat()
        value = round(float(reading.value), 2)
        if reading.sensor_type == "ds18b20":
            alias = get_sensor_display_name("ds18b20")
            series_name = alias or "Température DS18B20"
            unit = "°C"
            axis = "temperature"
        elif reading.sensor_type == "am2315":
            if reading.metric == "temperature":
                alias = get_sensor_display_name("am2315")
                series_name = alias or "Température AM2315"
                unit = "°C"
                axis = "temperature"
            elif reading.metric == "humidity":
                alias = get_sensor_display_name("am2315")
                series_name = f"Humidité {alias}" if alias else "Humidité AM2315"
                unit = "%"
                axis = "humidity"
            else:
                continue
        else:
            continue
        key = (reading.sensor_type, reading.metric)
        base_color = base_color_map.get(key)
        series_entry = series_map.setdefault(
            series_name,
            {
                "name": series_name,
                "unit": unit,
                "axis": axis,
                "data": [],
                "color": base_color,
                "meta": {"sensor_type": reading.sensor_type, "metric": reading.metric},
            },
        )
        series_entry["data"].append({"x": timestamp, "y": value})

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
        last_point: tuple[str, float] | None = None
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
            "last_at": last_point[0] or None,
            "count": len(values),
            "decimals": decimals,
        }

    temperature_series, temperature_colors = _split_series_by_axis("temperature")
    humidity_series, humidity_colors = _split_series_by_axis("humidity")
    temperature_summary = _summarize_series(temperature_series, "°C", "Température")
    humidity_summary = _summarize_series(humidity_series, "%", "Humidité")
    temperature_has_data = temperature_summary["count"] > 0
    humidity_has_data = humidity_summary["count"] > 0
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

    relay_entries = (
        JournalEntry.query.filter(
            JournalEntry.message.like("Commande relais ch%"),
            JournalEntry.created_at >= period_start,
        )
        .order_by(JournalEntry.created_at.asc())
        .all()
    )

    relay_channel_colors = {
        1: {"border": "#f97316", "background": "rgba(249, 115, 22, 0.15)"},
        2: {"border": "#8b5cf6", "background": "rgba(139, 92, 246, 0.18)"},
        3: {"border": "#14b8a6", "background": "rgba(20, 184, 166, 0.18)"},
    }
    relay_annotations = []
    relay_last_command: dict[int, str] = {}
    relay_legend_map: dict[int, dict[str, object]] = {}
    relay_labels_map = get_relay_labels()
    for entry in relay_entries:
        details = entry.details or {}
        channel = details.get("channel")
        if channel is None:
            try:
                channel = int(entry.message.split("ch")[1])
            except Exception:
                channel = None
        command = details.get("command", "").strip().lower()
        if channel is None or not command:
            continue
        colors = relay_channel_colors.get(
            channel,
            {"border": "#f97316", "background": "rgba(249, 115, 22, 0.15)"},
        )
        command_lower = command.lower()
        relay_name = relay_labels_map.get(channel, f"Relais {channel}")
        details_text = []
        if command_lower in {"on", "off"}:
            if relay_last_command.get(channel) == command_lower:
                continue
            relay_last_command[channel] = command_lower
        else:
            relay_last_command[channel] = command_lower

        if command_lower == "on":
            label_text = f"▲ {relay_name} ON"
            details_text.append("État cible : ON")
        elif command_lower == "off":
            label_text = f"▼ {relay_name} OFF"
            details_text.append("État cible : OFF")
        elif command_lower == "toggle":
            label_text = f"⇄ {relay_name} Toggle"
            details_text.append("Commande : bascule")
        else:
            label_text = f"{relay_name} → {command_lower}"
        issued_by = details.get("issued_by")
        if issued_by:
            details_text.append(f"Par : {issued_by}")
        if details.get("result"):
            status = details["result"].get("status")
            if status:
                details_text.append(f"Résultat : {status}")
        relay_data = {"channel": channel, "command": command_lower, "details": details_text}
        relay_annotations.append(
            {
                "timestamp": entry.created_at.isoformat(),
                "label": label_text,
                "color": colors["border"],
                "background": colors["background"],
                "data": relay_data,
            }
        )
        if channel not in relay_legend_map:
            relay_legend_map[channel] = {
                "channel": channel,
                "name": relay_name,
                "color": colors["border"],
            }

    relay_legend = sorted(relay_legend_map.values(), key=lambda item: item["name"])

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
        flash("Accès réservé à l’administrateur.", "danger")
        return redirect(url_for("main.dashboard"))
    command = (request.form.get("command") or "").strip().lower()
    if not command:
        flash("Commande invalide.", "danger")
        return redirect(url_for("main.dashboard"))

    result = set_relay_state(channel, command)
    status = result.get("status")
    message = result.get("message", "Commande exécutée.")

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
        flash(message, "success")
    elif status == "unavailable":
        flash("Contrôle des relais indisponible sur cette plateforme.", "warning")
    else:
        flash(message, "danger")
    return redirect(url_for("main.dashboard"))


@main_bp.route("/automatisation", methods=["GET", "POST"])
@login_required
def automation():
    form = AutomationRuleForm()

    sensor_registry = _build_sensor_registry()
    relay_pins = get_configured_relay_pins()
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
    return render_template(
        "dashboard/automation.html",
        form=form,
        rules=rules,
        filters=filters,
        filters_query=filters_query,
        form_action=url_for("main.automation") + ("?" + filters_query if filters_query else ""),
        form_title="Créer une règle",
        form_subtitle="Définissez les déclencheurs et actions pour automatiser vos scénarios.",
        submit_label="Enregistrer",
        cancel_url=None,
        editing_rule_id=None,
        sensor_registry_json=json.dumps(sensor_registry),
    )


@main_bp.route("/automatisation/<int:rule_id>/modifier", methods=["GET", "POST"])
@login_required
def edit_rule(rule_id: int):
    rule = AutomationRule.query.get_or_404(rule_id)
    if rule.owner != current_user and current_user.role != "admin":
        flash("Accès refusé.", "danger")
        return redirect(url_for("main.automation"))

    form = AutomationRuleForm()

    sensor_registry = _build_sensor_registry()
    relay_pins = get_configured_relay_pins()

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
        if action_channel:
            form.relay_channel.data = action_channel
        if action_command:
            form.relay_action.data = action_command

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

    form_action = url_for("main.edit_rule", rule_id=rule.id)
    cancel_url = url_for("main.automation")
    if filters_query:
        form_action = f"{form_action}?{filters_query}"
        cancel_url = f"{cancel_url}?{filters_query}"

    return render_template(
        "dashboard/automation.html",
        form=form,
        rules=rules,
        filters=filters,
        filters_query=filters_query,
        form_action=form_action,
        form_title="Modifier la règle",
        form_subtitle=f"Dernière mise à jour le {rule.updated_at.strftime('%d/%m/%Y %H:%M') if rule.updated_at else rule.created_at.strftime('%d/%m/%Y %H:%M')}",
        submit_label="Mettre à jour",
        cancel_url=cancel_url,
        editing_rule_id=rule.id,
        sensor_registry_json=json.dumps(sensor_registry),
    )


@main_bp.route("/automatisation/<int:rule_id>/supprimer", methods=["POST"])
@login_required
def delete_rule(rule_id: int):
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
    return render_template("dashboard/camera.html")


@main_bp.route("/camera/flux")
@login_required
def camera_feed():
    try:
        return Response(_camera_stream(), mimetype="multipart/x-mixed-replace; boundary=frame")
    except RuntimeError:
        flash("Caméra indisponible.", "danger")
        return redirect(url_for("main.camera"))


@main_bp.route("/parametres", methods=["GET", "POST"])
@login_required
def settings():
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
            if new_poll_interval is not None:
                app_obj = current_app._get_current_object()
                if app_obj.config.get("SENSOR_POLL_ENABLED", True):
                    schedule_sensor_poll(app_obj, new_poll_interval)
                else:
                    app_obj.config["SENSOR_POLL_INTERVAL_MINUTES"] = new_poll_interval
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

    hardware_status = build_hardware_overview(relay_pins)
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
        flash("Accès réservé à l’administrateur.", "danger")
        return redirect(url_for("main.dashboard"))
    search = request.args.get("q", "").strip()
    level = request.args.get("level", "")
    sort = request.args.get("sort", "recent")
    page = max(int(request.args.get("page", 1)), 1)
    per_page = max(min(int(request.args.get("per_page", 20)), 100), 5)
    from_date = request.args.get("from", "")
    to_date = request.args.get("to", "")

    query = JournalEntry.query

    if search:
        like = f"%{search}%"
        query = query.filter(JournalEntry.message.ilike(like))

    if level in {"info", "warning", "danger"}:
        query = query.filter_by(level=level)

    if from_date:
        try:
            start = datetime.fromisoformat(from_date)
            query = query.filter(JournalEntry.created_at >= start)
        except ValueError:
            pass

    if to_date:
        try:
            end = datetime.fromisoformat(to_date)
            query = query.filter(JournalEntry.created_at <= end)
        except ValueError:
            pass

    if sort == "oldest":
        query = query.order_by(JournalEntry.created_at.asc())
    else:
        query = query.order_by(JournalEntry.created_at.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    entries = pagination.items
    query_args = request.args.to_dict()
    relay_label_map = get_relay_labels()
    sensor_alias_cache: dict[str, str] = {}
    detailed_entries = []
    for entry in entries:
        detail = entry.details or {}

        message = entry.message
        if message.lower().startswith("commande relais ch"):
            try:
                channel_part = message.split("ch", 1)[1].strip()
                channel = int("".join(filter(str.isdigit, channel_part)))
                relay_name = relay_label_map.get(channel, f"Relais {channel}")
                message = f"Commande relais • {relay_name}"
            except Exception:
                pass

        formatted = {
            "level": entry.level,
            "message": message,
            "timestamp": entry.created_at,
            "detail": detail,
            "actors": detail.get("actors") if isinstance(detail.get("actors"), list) else None,
            "metadata": None,
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

        if detail:
            try:
                formatted["detail_pretty"] = json.dumps(detail, ensure_ascii=False, indent=2, sort_keys=True)
            except (TypeError, ValueError):
                formatted["detail_pretty"] = None
        else:
            formatted["detail_pretty"] = None

        detailed_entries.append(formatted)

    prev_url = None
    next_url = None
    if pagination.has_prev:
        params = query_args.copy()
        params["page"] = pagination.prev_num
        prev_url = url_for("main.journal", **params)
    if pagination.has_next:
        params = query_args.copy()
        params["page"] = pagination.next_num
        next_url = url_for("main.journal", **params)

    return render_template(
        "dashboard/journal.html",
        entries=detailed_entries,
        filters={"q": search, "level": level, "from": from_date, "to": to_date},
        pagination={
            "page": pagination.page,
            "pages": pagination.pages,
            "total": pagination.total,
            "per_page": pagination.per_page,
            "has_prev": pagination.has_prev,
            "has_next": pagination.has_next,
            "prev_num": pagination.prev_num,
            "next_num": pagination.next_num,
            "prev_url": prev_url,
            "next_url": next_url,
        },
    )


@main_bp.route("/journal/purge", methods=["POST"])
@login_required
def journal_purge():
    if current_user.role != "admin":
        flash("Accès réservé à l’administrateur.", "danger")
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


@main_bp.route("/profil", methods=["GET", "POST"])
@login_required
def profile():
    form = ProfileForm(obj=current_user)
    if request.method == "GET":
        form.username.data = current_user.username
        form.email.data = current_user.email
        form.twofa_enabled.data = current_user.twofa_enabled

    if form.validate_on_submit():
        if (
            form.username.data != current_user.username
            and User.query.filter_by(username=form.username.data).first()
        ):
            flash("Ce nom d’utilisateur est déjà utilisé.", "warning")
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
            current_user.username = form.username.data
            current_user.email = form.email.data
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


@main_bp.route("/manifest.json")
def manifest():
    manifest_data = {
        "name": "Dashboard Automatisation",
        "short_name": "Dashboard",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0f172a",
        "theme_color": "#0f172a",
        "lang": "fr",
        "icons": [
            {
                "src": url_for("static", filename="img/icon-128.png", _external=True),
                "sizes": "128x128",
                "type": "image/png"
            },
            {
                "src": url_for("static", filename="img/192.png", _external=True),
                "sizes": "192x192",
                "type": "image/png"
            },
            {
                "src": url_for("static", filename="img/256.png", _external=True),
                "sizes": "256x256",
                "type": "image/png"
            },
            {
                "src": url_for("static", filename="img/icon-512.png", _external=True),
                "sizes": "512x512",
                "type": "image/png"
            }
        ]
    }
    return jsonify(manifest_data)


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
