from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from flask import current_app

from . import db
from .hardware.gpio_controller import set_relay_state
from .mailer import send_email
from .models import AutomationRule, JournalEntry, RelayState, SensorReading, User


TRIGGER_PATTERN = re.compile(
    r"sensor:(?P<sensor_type>[a-zA-Z0-9_\-]+)\.(?P<metric>[a-zA-Z0-9_\-]+)(?:@(?P<sensor_id>[a-zA-Z0-9_\-]+))?\s*(?P<operator>>=|<=|>|<|==|!=)\s*(?P<value>-?\d+(?:\.\d+)?)"
)

EMAIL_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="utf-8">
    <title>{title}</title>
    <style>
        body {{ font-family: 'Inter', Arial, sans-serif; background: #f8fafc; color: #0f172a; }}
        .container {{ max-width: 520px; margin: 0 auto; padding: 32px 24px; background: #ffffff; border-radius: 24px; box-shadow: 0 20px 60px -30px rgba(15, 23, 42, 0.25); }}
        .card {{ margin-top: 18px; padding: 16px 18px; border-radius: 18px; background: #f1f5f9; }}
        .badge {{ display: inline-block; padding: 4px 10px; border-radius: 9999px; background: #ecfdf5; color: #047857; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; }}
        .meta {{ font-size: 13px; color: #475569; margin: 4px 0; }}
        .footer {{ margin-top: 32px; font-size: 12px; color: #94a3b8; }}
    </style>
</head>
<body>
    <div class="container">
        <img src="{logo_url}" alt="Logo Dashboard" style="height: 48px; border-radius: 16px;">
        <h1 style="margin-top: 24px; font-size: 22px;">{title}</h1>
        {body}
        <p class="footer">Dashboard · Automatisation et supervision.</p>
    </div>
</body>
</html>"""


@dataclass
class Trigger:
    sensor_type: str
    metric: str
    operator: str
    threshold: float
    sensor_id: Optional[str] = None


def parse_trigger(trigger_str: str) -> Optional[Trigger]:
    match = TRIGGER_PATTERN.fullmatch(trigger_str.strip())
    if not match:
        return None
    groups = match.groupdict()
    return Trigger(
        sensor_type=groups["sensor_type"].lower(),
        metric=groups["metric"].lower(),
        operator=groups["operator"],
        threshold=float(groups["value"]),
        sensor_id=groups.get("sensor_id"),
    )


def _compare(value: float, operator: str, threshold: float) -> bool:
    if operator == ">":
        return value > threshold
    if operator == "<":
        return value < threshold
    if operator == ">=":
        return value >= threshold
    if operator == "<=":
        return value <= threshold
    if operator == "==":
        return value == threshold
    if operator == "!=":
        return value != threshold
    return False


def _build_reading_map(readings: Iterable[SensorReading]) -> Dict[Tuple[str, str, Optional[str]], SensorReading]:
    reading_map: Dict[Tuple[str, str, Optional[str]], SensorReading] = {}
    for reading in readings:
        sensor_type = (reading.sensor_type or "").lower()
        metric = (reading.metric or "").lower()
        sensor_id = (reading.sensor_id or "").lower() or None
        timestamp = reading.created_at or datetime.utcnow()

        key = (sensor_type, metric, sensor_id)
        existing = reading_map.get(key)
        if existing is None or (existing.created_at or datetime.min) < timestamp:
            reading_map[key] = reading

        fallback_key = (sensor_type, metric, None)
        fallback = reading_map.get(fallback_key)
        if fallback is None or (fallback.created_at or datetime.min) < timestamp:
            reading_map[fallback_key] = reading
    return reading_map


def _execute_actions(actions: str, *, rule: Optional[AutomationRule] = None) -> List[Dict[str, str]]:
    outcome: List[Dict[str, str]] = []
    for raw_line in actions.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("relay:"):
            try:
                command = line.split(":", 1)[1]
                channel_part, state_part = command.split("=", 1)
                channel = int(channel_part.strip())
                state = state_part.strip()
                result = set_relay_state(channel, state)
                final_state = result.get("state") or state
                outcome.append(
                    {
                        "channel": channel,
                        "state": final_state,
                        **result,
                    }
                )
                db.session.add(
                    JournalEntry(
                        level="info" if result.get("status") == "ok" else "warning",
                        message=f"Commande relais ch{channel}",
                        details={
                            "channel": channel,
                            "command": final_state,
                            "result": result,
                            "issued_by": (rule.name if rule else "Automatisation"),
                            "rule_id": rule.id if rule else None,
                            "timestamp": datetime.utcnow().isoformat(),
                        },
                    )
                )
                if result.get("status") == "ok":
                    _notify_relay_change(
                        channel=channel,
                        state=final_state,
                        source=f"Automatisation '{rule.name if rule else 'Automatisation'}'",
                    )
            except Exception as exc:  # pragma: no cover - parsing robuste
                outcome.append({"status": "error", "message": f"Action invalide '{line}': {exc}"})
        else:
            outcome.append({"status": "ignored", "message": f"Commande inconnue '{line}'"})
    return outcome


def _collect_admin_recipients() -> list[str]:
    app = current_app
    recipients: set[str] = set()
    admin_email = app.config.get("ADMIN_NOTIFICATION_EMAIL")
    if admin_email:
        recipients.add(admin_email)
    admin_users = User.query.filter_by(role="admin").all()
    for admin in admin_users:
        if admin.email:
            recipients.add(admin.email)
    return sorted(recipients)


def _notify_rule_trigger(triggered: List[Dict[str, object]], triggered_at: datetime) -> None:
    recipients = _collect_admin_recipients()
    if not recipients:
        current_app.logger.info("Notification automatisation ignorée: aucun destinataire configuré.")
        db.session.add(
            JournalEntry(
                level="warning",
                message="Notification email ignorée",
                details={
                    "type": "automation_trigger",
                    "reason": "no_recipients",
                    "timestamp": triggered_at.isoformat(),
                },
            )
        )
        db.session.commit()
        return

    subject = f"Alerte automatisation : {len(triggered)} règle(s) déclenchée(s)"
    lines = [
        "Bonjour,",
        "",
        "Les règles d’automatisation suivantes viennent d’être déclenchées :",
        "",
    ]
    for execution in triggered:
        rule_name = execution.get("rule_name", "Règle sans nom")
        trigger_expr = execution.get("trigger")
        reading = execution.get("reading") or {}
        reading_timestamp = reading.get("created_at")
        try:
            timestamp_dt = datetime.fromisoformat(str(reading_timestamp))
        except Exception:
            timestamp_dt = triggered_at
        timestamp_label = timestamp_dt.strftime("%d/%m/%Y %H:%M:%S UTC")
        lines.append(f"- {rule_name} • {timestamp_label}")
        if trigger_expr:
            lines.append(f"  Condition : {trigger_expr}")
        metric = reading.get("metric")
        value = reading.get("value")
        sensor = reading.get("sensor_type")
        if value is not None and metric and sensor:
            lines.append(f"  Mesure : {sensor} {metric} = {value}")
        actions = execution.get("actions") or []
        if actions:
            summary = ", ".join(
                f"Relais {item.get('channel')} -> {item.get('state')}"
                for item in actions
                if isinstance(item, dict) and item.get("channel") is not None
            )
            if summary:
                lines.append(f"  Actions : {summary}")
        lines.append("")

    lines.append("Ceci est un message automatique. Merci de vérifier votre installation si nécessaire.")
    body = "\n".join(lines)

    logo = current_app.config.get("EXTERNAL_LOGO_URL") or ""
    if not logo:
        try:
            with current_app.app_context():
                from flask import url_for

                logo = url_for("static", filename="img/logo.png", _external=True)
        except Exception:
            logo = ""

    html_blocks = [
        "<p>Bonjour,</p>",
        "<p>Les règles d’automatisation suivantes viennent d’être déclenchées :</p>",
    ]
    for execution in triggered:
        rule_name = execution.get("rule_name", "Règle sans nom")
        trigger_expr = execution.get("trigger")
        reading = execution.get("reading") or {}
        metric = reading.get("metric", "")
        value = reading.get("value")
        sensor = reading.get("sensor_type", "")
        timestamp = reading.get("created_at", triggered_at.isoformat())
        actions = execution.get("actions") or []
        action_summary = ", ".join(
            f"Relais {item.get('channel')} → {item.get('state')}"
            for item in actions
            if isinstance(item, dict) and item.get("channel") is not None
        )
        html_blocks.append(
            f"""
            <div class="card">
                <span class="badge">{rule_name}</span>
                <p class="meta"><strong>Heure :</strong> {timestamp}</p>
                {'<p class="meta"><strong>Condition :</strong> ' + trigger_expr + '</p>' if trigger_expr else ''}
                {'<p class="meta"><strong>Mesure :</strong> ' + str(sensor) + ' ' + str(metric) + ' = ' + str(value) + '</p>' if value is not None else ''}
                {'<p class="meta"><strong>Actions :</strong> ' + action_summary + '</p>' if action_summary else ''}
            </div>
            """
        )
    html_blocks.append("<p>Message automatique — surveillance Dashboard.</p>")
    html_body = EMAIL_TEMPLATE.format(title=subject, logo_url=logo, body="".join(html_blocks))

    send_email(subject=subject, recipients=recipients, body=body, html_body=html_body)
    db.session.add(
        JournalEntry(
            level="info",
            message="Notification email envoyée",
            details={
                "type": "automation_trigger",
                "subject": subject,
                "recipients": recipients,
                "timestamp": triggered_at.isoformat(),
            },
        )
    )
    db.session.commit()


def _notify_relay_change(*, channel: int, state: str, source: str) -> None:
    now = datetime.utcnow()
    normalized_state = (state or "").strip().lower()
    previous_state = (
        RelayState.query.filter_by(channel=channel)
        .order_by(RelayState.created_at.desc())
        .first()
    )
    if previous_state and (previous_state.state or "").lower() == normalized_state:
        current_app.logger.info(
            "Notification relais ignorée: channel=%s état inchangé (%s)",
            channel,
            normalized_state,
        )
        return

    recipients = _collect_admin_recipients()
    db.session.add(
        RelayState(channel=channel, state=normalized_state, source=source, created_at=now)
    )
    display_state = (normalized_state or state or "unknown").upper()

    if not recipients:
        current_app.logger.info("Notification relais ignorée: aucun destinataire configuré.")
        db.session.add(
            JournalEntry(
                level="warning",
                message="Notification email ignorée",
                details={
                    "type": "relay_change",
                    "channel": channel,
                    "state": normalized_state,
                    "source": source,
                    "reason": "no_recipients",
                    "timestamp": now.isoformat(),
                },
            )
        )
        db.session.commit()
        return

    timestamp_label = now.strftime("%d/%m/%Y %H:%M:%S UTC")
    subject = f"Relais {channel} → {display_state}"
    body = "\n".join(
        [
            "Bonjour,",
            "",
            f"Le relais #{channel} vient de passer à l’état {display_state} ({source}).",
            f"Heure: {timestamp_label}",
            "",
            "Ceci est un message automatique ; vérifiez votre installation si nécessaire.",
        ]
    )
    logo = current_app.config.get("EXTERNAL_LOGO_URL") or ""
    if not logo:
        try:
            with current_app.app_context():
                from flask import url_for

                logo = url_for("static", filename="img/logo.png", _external=True)
        except Exception:
            logo = ""
    card = f"""
    <div class="card">
        <span class="badge">Relais {channel}</span>
        <p class="meta"><strong>Nouvel état :</strong> {display_state}</p>
        <p class="meta"><strong>Origine :</strong> {source}</p>
        <p class="meta"><strong>Horodatage :</strong> {timestamp_label}</p>
    </div>
    """
    html_body = EMAIL_TEMPLATE.format(
        title=subject,
        logo_url=logo,
        body=f"<p>Bonjour,</p><p>Le relais suivant a changé d’état :</p>{card}<p>Surveillance Dashboard.</p>",
    )
    send_email(subject=subject, recipients=recipients, body=body, html_body=html_body)
    db.session.add(
        JournalEntry(
            level="info",
            message=f"Notification email envoyée — Relais {channel} {display_state}",
            details={
                "type": "relay_change",
                "channel": channel,
                "state": normalized_state,
                "source": source,
                "subject": subject,
                "recipients": recipients,
                "timestamp": now.isoformat(),
            },
        )
    )
    db.session.commit()


def evaluate_rules_with_readings(readings: Iterable[SensorReading]) -> None:
    active_rules = AutomationRule.query.filter_by(enabled=True).all()
    if not active_rules:
        return
    reading_map = _build_reading_map(readings)
    now = datetime.utcnow()
    triggered = []

    for rule in active_rules:
        trigger = parse_trigger(rule.trigger)
        if not trigger:
            current_app.logger.warning("Règle %s: déclencheur invalide '%s'", rule.name, rule.trigger)
            continue
        key = (trigger.sensor_type, trigger.metric, trigger.sensor_id.lower() if trigger.sensor_id else None)
        reading = reading_map.get(key)
        if not reading:
            # Essayer sans sensor_id si non trouvé
            if trigger.sensor_id:
                fallback_key = (trigger.sensor_type, trigger.metric, None)
                reading = reading_map.get(fallback_key)
            if not reading:
                continue

        if reading.value is None:
            continue

        if rule.cooldown_seconds and rule.last_triggered_at:
            delta = now - rule.last_triggered_at
            if delta < timedelta(seconds=rule.cooldown_seconds):
                continue

        if not _compare(float(reading.value), trigger.operator, trigger.threshold):
            continue

        results = _execute_actions(rule.action, rule=rule)
        rule.last_triggered_at = now
        triggered.append(
            {
                "rule_id": rule.id,
                "rule_name": rule.name,
                "trigger": rule.trigger,
                "reading": {
                    "value": reading.value,
                    "metric": reading.metric,
                    "sensor_type": reading.sensor_type,
                    "sensor_id": reading.sensor_id,
                    "created_at": reading.created_at.isoformat(),
                },
                "actions": results,
            }
        )

    if triggered:
        db.session.add(
            JournalEntry(
                level="info",
                message="Automatisation déclenchée",
                details={"executions": triggered, "timestamp": now.isoformat()},
            )
        )
        db.session.commit()
        _notify_rule_trigger(triggered, now)
    else:
        db.session.commit()

