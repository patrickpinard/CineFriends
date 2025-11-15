from __future__ import annotations

from datetime import datetime
from typing import Any, List

from flask import current_app

from . import db
from .automation_engine import evaluate_rules_with_readings
from .lcd_display import refresh_lcd_display
from .models import JournalEntry, SensorReading
from .utils import detect_am2315, detect_ds18b20, _is_linux_arm  # type: ignore[attr-defined]


def _extract_ds18b20_readings(status: dict[str, Any]) -> List[SensorReading]:
    readings: List[SensorReading] = []
    if not status:
        return readings
    details = status.get("details") or {}
    sensor_ids = details.get("sensors") or []
    temperatures = details.get("temperatures") or []
    for sensor_id, temperature in zip(sensor_ids, temperatures):
        if temperature is None:
            continue
        readings.append(
            SensorReading(
                sensor_type="ds18b20",
                sensor_id=str(sensor_id),
                metric="temperature",
                value=float(temperature),
                unit="°C",
            )
        )
    return readings


def _extract_am2315_readings(status: dict[str, Any]) -> List[SensorReading]:
    readings: List[SensorReading] = []
    if not status:
        return readings
    details = status.get("details") or {}

    temperature = details.get("temperature")
    humidity = details.get("humidity")

    if temperature is not None:
        readings.append(
            SensorReading(
                sensor_type="am2315",
                sensor_id="am2315",
                metric="temperature",
                value=float(temperature),
                unit="°C",
            )
        )
    if humidity is not None:
        readings.append(
            SensorReading(
                sensor_type="am2315",
                sensor_id="am2315",
                metric="humidity",
                value=float(humidity),
                unit="%",
            )
        )
    return readings


def collect_sensor_readings(app) -> None:
    """Collecte périodique des mesures capteurs et stockage."""
    with app.app_context():
        logger = current_app.logger
        all_readings: List[SensorReading] = []
        warnings: List[str] = []

        try:
            ds_status = detect_ds18b20()
            status_label = ds_status.get("status")
            if status_label not in {"ok", "warning"}:
                warnings.append(f"DS18B20: {ds_status.get('message')}")
            all_readings.extend(_extract_ds18b20_readings(ds_status))
        except Exception as exc:  # pragma: no cover - dépendant hardware
            logger.exception("Erreur lecture DS18B20: %s", exc)
            warnings.append(f"DS18B20 indisponible ({exc})")

        try:
            am_status = detect_am2315()
            status_label = am_status.get("status")
            if status_label not in {"ok", "warning"}:
                warnings.append(f"AM2315: {am_status.get('message')}")
            all_readings.extend(_extract_am2315_readings(am_status))
        except Exception as exc:  # pragma: no cover - dépendant hardware
            logger.exception("Erreur lecture AM2315: %s", exc)
            warnings.append(f"AM2315 indisponible ({exc})")

        if not all_readings:
            if warnings and _is_linux_arm():
                db.session.add(
                    JournalEntry(
                        level="warning",
                        message="Lecture capteurs impossible",
                        details={"warnings": warnings, "timestamp": datetime.utcnow().isoformat()},
                    )
                )
                db.session.commit()
            return

        try:
            timestamp = datetime.utcnow().isoformat()
            for reading in all_readings:
                reading.extra = {"snapshot_at": timestamp}
                db.session.add(reading)
            db.session.commit()
            evaluate_rules_with_readings(all_readings)
            try:
                refresh_lcd_display(push=True)
            except Exception as exc:  # pragma: no cover - dépend matériel
                logger.warning("Impossible de rafraîchir l'afficheur LCD: %s", exc)
        except Exception as exc:
            db.session.rollback()
            logger.exception("Erreur enregistrement mesures capteurs: %s", exc)
            db.session.add(
                JournalEntry(
                    level="danger",
                    message="Échec enregistrement mesures capteurs",
                    details={"error": str(exc), "timestamp": datetime.utcnow().isoformat()},
                )
            )
            db.session.commit()


