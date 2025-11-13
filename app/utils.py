from __future__ import annotations

import os
import platform
import secrets
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

from flask import current_app
from werkzeug.datastructures import FileStorage


def save_avatar(file: FileStorage) -> str:
    ext = Path(file.filename or "").suffix.lower()
    filename = f"avatar_{secrets.token_hex(8)}{ext}"
    upload_folder = Path(current_app.config["UPLOAD_FOLDER"])  # type: ignore[arg-type]
    upload_folder.mkdir(parents=True, exist_ok=True)
    destination = upload_folder / filename
    file.save(destination)
    return filename


def delete_avatar(filename: str | None) -> None:
    if not filename:
        return
    upload_folder = Path(current_app.config["UPLOAD_FOLDER"])
    filepath = upload_folder / filename
    try:
        if filepath.exists():
            filepath.unlink()
    except OSError:
        current_app.logger.warning("Impossible de supprimer l’avatar %s", filepath)


def serialize_value(value):
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
    changes = {}
    for field in fields:
        before = serialize_value(original.get(field))
        after = serialize_value(updated.get(field))
        if before != after:
            changes[field] = {"before": before, "after": after}
    return changes


def _is_linux_arm() -> bool:
    machine = platform.machine().lower()
    return platform.system().lower() == "linux" and ("arm" in machine or "aarch64" in machine)


def detect_gpio_relays(pins: Iterable[int]) -> Dict[str, Any]:
    pins_list = list(pins)
    status: Dict[str, Any] = {
        "id": "relays",
        "label": "Carte relais 3 canaux",
        "category": "Actionneurs",
        "status": "warning",
        "message": "Détection uniquement disponible sur Raspberry Pi.",
        "details": {"pins": pins_list},
    }

    if not _is_linux_arm():
        return status

    try:
        import RPi.GPIO as GPIO  # type: ignore
    except ModuleNotFoundError:
        status.update(
            {
                "status": "error",
                "message": "Bibliothèque RPi.GPIO introuvable. Installez-la sur le Raspberry Pi.",
            }
        )
        return status
    except Exception as exc:  # pragma: no cover - dépendances spécifiques
        status.update({"status": "error", "message": f"Erreur lors du chargement de RPi.GPIO : {exc}"})
        return status

    try:
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        unreachable: List[int] = []
        for pin in pins_list:
            try:
                GPIO.gpio_function(pin)
            except Exception:  # pragma: no cover - dépendances spécifiques
                unreachable.append(pin)
        if unreachable:
            status.update(
                {
                    "status": "warning",
                    "message": f"GPIO inaccessibles : {', '.join(str(pin) for pin in unreachable)}.",
                }
            )
        else:
            status.update(
                {
                    "status": "ok",
                    "message": f"{len(pins_list)} relais prêts sur les GPIO {', '.join(str(pin) for pin in pins_list)}.",
                }
            )
    except RuntimeError as exc:
        status.update({"status": "error", "message": f"Accès GPIO refusé ({exc}). Exécutez l’application en sudo sur le Raspberry Pi."})
    except Exception as exc:  # pragma: no cover - dépendances spécifiques
        status.update({"status": "error", "message": f"Échec de la vérification des relais : {exc}"})
    finally:
        try:
            GPIO.cleanup()  # type: ignore
        except Exception:
            pass
    return status


def detect_ds18b20() -> Dict[str, Any]:
    status: Dict[str, Any] = {
        "id": "ds18b20",
        "label": "Sonde de température intérieure (DS18B20)",
        "category": "Capteurs",
        "status": "warning",
        "message": "Détection uniquement disponible sur Raspberry Pi.",
        "details": {},
    }

    if not _is_linux_arm():
        return status

    try:
        from w1thermsensor import NoSensorFoundError, SensorNotReadyError, W1ThermSensor  # type: ignore
    except ModuleNotFoundError:
        status.update(
            {
                "status": "error",
                "message": "Bibliothèque w1thermsensor manquante. Activez 1-Wire et installez la dépendance.",
            }
        )
        return status
    except Exception as exc:  # pragma: no cover - dépendances spécifiques
        status.update({"status": "error", "message": f"Impossible de charger w1thermsensor : {exc}"})
        return status

    try:
        sensors = W1ThermSensor.get_available_sensors()
        if not sensors:
            status.update(
                {
                    "status": "warning",
                    "message": "Aucune sonde DS18B20 détectée. Vérifiez le câblage et l’activation du bus 1-Wire.",
                }
            )
            return status
        temperatures = []
        for sensor in sensors:
            try:
                temperatures.append(round(sensor.get_temperature(), 1))
            except SensorNotReadyError:
                temperatures.append(None)
        details = {"sensors": [sensor.id for sensor in sensors], "temperatures": temperatures}
        readable_temps = [f"{temp}°C" for temp in temperatures if temp is not None]
        if readable_temps:
            message = f"{len(sensors)} sonde(s) détectée(s). Température(s) : {', '.join(readable_temps)}."
            status.update({"status": "ok", "message": message, "details": details})
        else:
            status.update(
                {
                    "status": "warning",
                    "message": f"{len(sensors)} sonde(s) détectée(s) mais aucune mesure disponible pour le moment.",
                    "details": details,
                }
            )
    except (NoSensorFoundError, FileNotFoundError):
        status.update(
            {
                "status": "warning",
                "message": "Aucune sonde DS18B20 détectée. Vérifiez le module w1-gpio et le capteur.",
            }
        )
    except Exception as exc:  # pragma: no cover - dépendances spécifiques
        status.update({"status": "error", "message": f"Erreur de lecture DS18B20 : {exc}"})
    return status


def detect_am2315() -> Dict[str, Any]:
    status: Dict[str, Any] = {
        "id": "am2315",
        "label": "Sonde température & humidité extérieure (AM2315)",
        "category": "Capteurs",
        "status": "warning",
        "message": "Détection uniquement disponible sur Raspberry Pi.",
        "details": {},
    }

    if not _is_linux_arm():
        return status

    try:
        try:
            from app.hardware.AM2315 import AM2315  # type: ignore
        except ModuleNotFoundError:
            from hardware.AM2315 import AM2315  # type: ignore
    except ModuleNotFoundError:
        status.update(
            {
                "status": "error",
                "message": "Bibliothèque AM2315 introuvable (app/hardware/AM2315.py). Vérifiez son emplacement.",
            }
        )
        return status
    except Exception as exc:  # pragma: no cover - dépendances spécifiques
        status.update({"status": "error", "message": f"Impossible de charger la bibliothèque AM2315 : {exc}"})
        return status

    try:
        try:
            sensor = AM2315()
        except TypeError:
            sensor = AM2315(busnum=1)  # type: ignore[call-arg]
        temperature = None
        humidity = None

        if hasattr(sensor, "read_sensor"):
            try:
                data = sensor.read_sensor()  # type: ignore[attr-defined]
            except TypeError:
                data = sensor.read_sensor(quick=True)  # type: ignore[attr-defined]
            if isinstance(data, dict):
                temperature = data.get("temperature")
                humidity = data.get("humidity")
            elif isinstance(data, (tuple, list)) and len(data) >= 2:
                temperature, humidity = data[0], data[1]
        if temperature is None and hasattr(sensor, "read_temperature"):
            temperature = sensor.read_temperature()  # type: ignore[attr-defined]
        if humidity is None and hasattr(sensor, "read_humidity"):
            humidity = sensor.read_humidity()  # type: ignore[attr-defined]

        if temperature is None or humidity is None:
            status.update(
                {
                    "status": "warning",
                    "message": "Capteur AM2315 détecté mais les mesures ne sont pas disponibles.",
                    "details": {"raw": {"temperature": temperature, "humidity": humidity}},
                }
            )
            return status

        temperature = round(float(temperature), 1)
        humidity = round(float(humidity), 1)
        status.update(
            {
                "status": "ok",
                "message": f"Capteur détecté. Température : {temperature}°C, Humidité : {humidity} %.",
                "details": {"temperature": temperature, "humidity": humidity},
            }
        )
    except RuntimeError as exc:
        status.update(
            {
                "status": "warning",
                "message": f"Impossible de lire le capteur AM2315 : {exc}",
            }
        )
    except Exception as exc:  # pragma: no cover - dépendances spécifiques
        status.update({"status": "error", "message": f"Erreur AM2315 : {exc}"})
    return status


def build_hardware_overview(relay_pins: Iterable[int]) -> List[Dict[str, Any]]:
    overview: List[Dict[str, Any]] = []
    overview.append(detect_gpio_relays(relay_pins))
    overview.append(detect_ds18b20())
    overview.append(detect_am2315())
    return overview
