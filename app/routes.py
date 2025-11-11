from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Generator

from flask import (Blueprint, Response, current_app, flash, jsonify, redirect,
                   render_template, request, url_for)
from flask_login import current_user, login_required
from urllib.parse import urlencode

from . import db
from .forms import AutomationRuleForm, ProfileForm, SettingForm
from .models import AutomationRule, JournalEntry, Notification, SensorReading, Setting, User
from .services import create_notification
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
        (channel, f"{relay_labels.get(channel, f'Relais {channel}')} • GPIO {pin}")
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

    # Agrégation des données capteurs AM2315
    start_window = now - timedelta(hours=24)
    am_readings = (
        SensorReading.query.filter(
            SensorReading.sensor_type == "am2315",
            SensorReading.metric.in_(["temperature", "humidity"]),
            SensorReading.created_at >= start_window,
        )
        .order_by(SensorReading.created_at.asc())
        .all()
    )
    buckets: dict[datetime, dict[str, list[float]]] = {}
    for reading in am_readings:
        if reading.value is None:
            continue
        bucket = reading.created_at.replace(minute=0, second=0, microsecond=0)
        bucket_data = buckets.setdefault(bucket, {"temperature": [], "humidity": []})
        bucket_data.setdefault(reading.metric, []).append(float(reading.value))

    chart_labels: list[str] = []
    chart_temperatures: list[float | None] = []
    chart_humidity: list[float | None] = []
    for bucket in sorted(buckets.keys()):
        slot = bucket.strftime("%H:%M")
        data = buckets[bucket]
        temp_values = data.get("temperature", [])
        hum_values = data.get("humidity", [])
        chart_labels.append(slot)
        chart_temperatures.append(round(sum(temp_values) / len(temp_values), 2) if temp_values else None)
        chart_humidity.append(round(sum(hum_values) / len(hum_values), 2) if hum_values else None)

    if not chart_labels:
        chart_labels = [(now - timedelta(hours=i)).strftime("%H:%M") for i in range(12, -1, -1)]
        chart_labels.reverse()
        chart_temperatures = [None] * len(chart_labels)
        chart_humidity = [None] * len(chart_labels)

    # Résumé des capteurs
    recent_readings = (
        SensorReading.query.order_by(SensorReading.created_at.desc()).limit(200).all()
    )
    sensor_map: dict[tuple[str, str], dict[str, object]] = {}
    for reading in recent_readings:
        key = (reading.sensor_type, (reading.sensor_id or "").lower())
        entry = sensor_map.setdefault(
            key,
            {
                "sensor_type": reading.sensor_type,
                "sensor_id": reading.sensor_id,
                "metrics": {},
                "updated_at": reading.created_at,
            },
        )
        if reading.metric not in entry["metrics"]:
            entry["metrics"][reading.metric] = {
                "value": round(reading.value, 2) if reading.value is not None else None,
                "unit": reading.unit,
            }
        if reading.created_at > entry["updated_at"]:
            entry["updated_at"] = reading.created_at

    sensor_cards: list[dict[str, object]] = []
    for key, data in sensor_map.items():
        sensor_type, sensor_id = key
        title = get_sensor_display_name(sensor_type)
        subtitle = None
        if sensor_type == "ds18b20" and sensor_id:
            subtitle = f"ID {sensor_id.upper()}"
        elif sensor_type == "am2315":
            subtitle = "Capteur combiné (température & humidité)"
        metrics = []
        for metric_key, metric_data in data["metrics"].items():
            label = "Température" if metric_key == "temperature" else "Humidité" if metric_key == "humidity" else metric_key.title()
            metrics.append(
                {
                    "label": label,
                    "value": metric_data["value"],
                    "unit": metric_data.get("unit") or "",
                }
            )
        sensor_cards.append(
            {
                "title": title,
                "subtitle": subtitle,
                "metrics": metrics,
                "updated_at": data["updated_at"],
                "updated_at_text": data["updated_at"].strftime("%d/%m/%Y %H:%M"),
            }
        )
    sensor_cards.sort(key=lambda item: item["title"])

    # Relais
    relay_pins = get_configured_relay_pins()
    relay_labels = get_relay_labels()
    relay_states = get_relay_states()
    relays_available = hardware_available() and bool(relay_pins)
    relays_active_low = is_active_low()
    relay_cards = []
    channel_rule_map: dict[int, list[str]] = {}
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
            channel_rule_map.setdefault(channel_value, []).append(rule.name)

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
        chart_labels=chart_labels,
        chart_temperatures=chart_temperatures,
        chart_humidity=chart_humidity,
        sensor_cards=sensor_cards,
        relay_cards=relay_cards,
        relays_available=relays_available,
        relays_active_low=relays_active_low,
        relay_manual_disabled=not relays_available,
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
        for key, value in submitted.items():
            if key in {"csrf_token", "refresh_hardware", "submit"} or not key.startswith("setting__"):
                continue
            setting_key = key.split("setting__", 1)[1]
            setting = Setting.query.filter_by(key=setting_key).first()
            before_value = setting.value if setting else None
            if not setting:
                setting = Setting(key=setting_key)
                db.session.add(setting)
            setting.value = value
            updated_items.append((setting_key, before_value, value))

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

    entries = query.all()
    detailed_entries = []
    for entry in entries:
        detail = entry.details or {}

        formatted = {
            "level": entry.level,
            "message": entry.message,
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
                metadata_items.append({
                    "label": key.replace("_", " ").title(),
                    "value": value,
                })
        if metadata_items:
            formatted["metadata"] = metadata_items

        detailed_entries.append(formatted)
    return render_template(
        "dashboard/journal.html",
        entries=detailed_entries,
        filters={"q": search, "level": level, "from": from_date, "to": to_date},
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
