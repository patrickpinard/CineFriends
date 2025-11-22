from __future__ import annotations

from datetime import datetime
from typing import Any, List

from flask import current_app

from . import db
from .logging_config import get_app_logger
from .automation_engine import evaluate_rules_with_readings
from .lcd_display import refresh_lcd_display
from .models import JournalEntry, RelayState, SensorReading
from .utils import detect_am2315, detect_ds18b20, _is_linux_arm  # type: ignore[attr-defined]
from .hardware.gpio_controller import get_configured_relay_pins, get_relay_states


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
        logger = get_app_logger()
        all_readings: List[SensorReading] = []
        warnings: List[str] = []

        try:
            ds_status = detect_ds18b20()
            status_label = ds_status.get("status")
            if status_label not in {"ok", "warning"}:
                warnings.append(f"DS18B20: {ds_status.get('message')}")
            all_readings.extend(_extract_ds18b20_readings(ds_status))
        except Exception as exc:  # pragma: no cover - dépendant hardware
            logger.exception("Erreur lecture DS18B20", sensor="ds18b20", error=str(exc), error_type=type(exc).__name__)
            warnings.append(f"DS18B20 indisponible ({exc})")

        try:
            am_status = detect_am2315()
            status_label = am_status.get("status")
            message = am_status.get("message", "")
            details = am_status.get("details", {})
            
            if status_label not in {"ok", "warning"}:
                warnings.append(f"AM2315: {message}")
                logger.warning("AM2315 statut anormal", sensor="am2315", status=status_label, message=message, details=details)
            
            am_readings = _extract_am2315_readings(am_status)
            if not am_readings and status_label == "ok":
                logger.warning("AM2315: statut OK mais aucune mesure extraite", sensor="am2315", details=details)
            elif not am_readings:
                logger.warning("AM2315: aucune mesure disponible", sensor="am2315", status=status_label, message=message, details=details)
            
            all_readings.extend(am_readings)
        except Exception as exc:  # pragma: no cover - dépendant hardware
            logger.exception("Erreur lecture AM2315", sensor="am2315", error=str(exc), error_type=type(exc).__name__)
            warnings.append(f"AM2315 indisponible ({exc})")
            # Enregistrer l'erreur dans le journal pour diagnostic
            db.session.add(
                JournalEntry(
                    level="warning",
                    message="Erreur lecture AM2315",
                    details={
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                )
            )
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()

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
            
            # Collecter et sauvegarder les états des relais périodiquement
            try:
                relay_pins = get_configured_relay_pins()
                if relay_pins:
                    relay_states = get_relay_states()
                    for channel, state in relay_states.items():
                        if channel in relay_pins:
                            # Toujours sauvegarder l'état pour avoir une trace périodique continue
                            # Cela permet d'afficher l'état dans le graphique même s'il n'a pas changé
                            relay_state = RelayState(
                                channel=channel,
                                state=state,
                                source="scheduler",
                            )
                            db.session.add(relay_state)
            except Exception as exc:
                logger.warning("Erreur lors de la collecte des états des relais: %s", exc)
            
            db.session.commit()
            evaluate_rules_with_readings(all_readings)
            try:
                refresh_lcd_display(push=True)
            except Exception as exc:  # pragma: no cover - dépend matériel
                logger.warning("Impossible de rafraîchir l'afficheur LCD", component="lcd", error=str(exc), error_type=type(exc).__name__)
        except Exception as exc:
            db.session.rollback()
            logger.exception("Erreur enregistrement mesures capteurs", readings_count=len(all_readings), error=str(exc), error_type=type(exc).__name__)
            db.session.add(
                JournalEntry(
                    level="danger",
                    message="Échec enregistrement mesures capteurs",
                    details={"error": str(exc), "timestamp": datetime.utcnow().isoformat()},
                )
            )
            db.session.commit()


