from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from flask import current_app

from . import db
from .hardware.gpio_controller import set_relay_state
from .models import AutomationRule, JournalEntry, SensorReading


TRIGGER_PATTERN = re.compile(
    r"sensor:(?P<sensor_type>[a-zA-Z0-9_\-]+)\.(?P<metric>[a-zA-Z0-9_\-]+)(?:@(?P<sensor_id>[a-zA-Z0-9_\-]+))?\s*(?P<operator>>=|<=|>|<|==|!=)\s*(?P<value>-?\d+(?:\.\d+)?)"
)


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
        key = (reading.sensor_type.lower(), reading.metric.lower(), (reading.sensor_id or "").lower() or None)
        existing = reading_map.get(key)
        if existing is None or reading.created_at > existing.created_at:
            reading_map[key] = reading
    return reading_map


def _execute_actions(actions: str) -> List[Dict[str, str]]:
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
                outcome.append(set_relay_state(channel, state))
            except Exception as exc:  # pragma: no cover - parsing robuste
                outcome.append({"status": "error", "message": f"Action invalide '{line}': {exc}"})
        else:
            outcome.append({"status": "ignored", "message": f"Commande inconnue '{line}'"})
    return outcome


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

        results = _execute_actions(rule.action)
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

