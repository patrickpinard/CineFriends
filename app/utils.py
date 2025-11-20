from __future__ import annotations

import os
import platform
import secrets
from importlib import import_module
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

from flask import current_app
from werkzeug.datastructures import FileStorage

def _import_optional_module(module_name: str):
    try:
        return import_module(module_name)
    except Exception:
        return None

np = _import_optional_module("numpy")
cv2 = _import_optional_module("cv2")
lcd_module = _import_optional_module("app.hardware.LCD") or _import_optional_module("hardware.LCD")
LCD = getattr(lcd_module, "LCD", None) if lcd_module else None
LCD = getattr(lcd_module, "LCD", None) if lcd_module else None

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
        # Lire l'adresse I2C depuis les paramètres si disponible
        address_str = None
        try:
            from .models import Setting
            setting = Setting.query.filter_by(key="Sensor_AM2315_Address").first()
            if setting and setting.value:
                address_str = setting.value.strip()
        except Exception:
            pass
        
        # Parser l'adresse (peut être "0x5C" ou "5C" ou "92")
        address = 0x5C  # Adresse par défaut
        if address_str:
            try:
                if address_str.startswith("0x") or address_str.startswith("0X"):
                    address = int(address_str, 16)
                else:
                    address = int(address_str, 16) if all(c in "0123456789ABCDEFabcdef" for c in address_str) else int(address_str)
            except (ValueError, TypeError):
                pass
        
        # Initialiser le capteur
        try:
            sensor = AM2315(address=address)
        except TypeError:
            try:
                sensor = AM2315(address=address, busnum=1)  # type: ignore[call-arg]
            except TypeError:
                sensor = AM2315()  # type: ignore[call-arg]
        
        temperature = None
        humidity = None
        
        # Essayer de lire température et humidité ensemble (plus efficace)
        if hasattr(sensor, "read_humidity_temperature"):
            try:
                data = sensor.read_humidity_temperature()  # type: ignore[attr-defined]
                if isinstance(data, (tuple, list)) and len(data) >= 2:
                    humidity, temperature = data[0], data[1]
            except Exception as exc:
                # Si la lecture groupée échoue, essayer séparément
                try:
                    if hasattr(sensor, "read_temperature"):
                        temperature = sensor.read_temperature()  # type: ignore[attr-defined]
                    if hasattr(sensor, "read_humidity"):
                        humidity = sensor.read_humidity()  # type: ignore[attr-defined]
                except Exception:
                    # Si tout échoue, lever l'exception originale
                    raise exc
        else:
            # Méthode de fallback : lire séparément
            if hasattr(sensor, "read_temperature"):
                temperature = sensor.read_temperature()  # type: ignore[attr-defined]
            if hasattr(sensor, "read_humidity"):
                humidity = sensor.read_humidity()  # type: ignore[attr-defined]

        if temperature is None or humidity is None:
            status.update(
                {
                    "status": "warning",
                    "message": "Capteur AM2315 détecté mais les mesures ne sont pas disponibles.",
                    "details": {"raw": {"temperature": temperature, "humidity": humidity}, "address": hex(address)},
                }
            )
            return status

        temperature = round(float(temperature), 1)
        humidity = round(float(humidity), 1)
        status.update(
            {
                "status": "ok",
                "message": f"Capteur détecté. Température : {temperature}°C, Humidité : {humidity} %.",
                "details": {"temperature": temperature, "humidity": humidity, "address": hex(address)},
            }
        )
    except RuntimeError as exc:
        status.update(
            {
                "status": "warning",
                "message": f"Impossible de lire le capteur AM2315 : {exc}",
                "details": {"error": str(exc), "error_type": "RuntimeError"},
            }
        )
    except OSError as exc:
        status.update(
            {
                "status": "error",
                "message": f"Erreur I2C AM2315 (bus I2C inaccessible ou capteur déconnecté) : {exc}",
                "details": {"error": str(exc), "error_type": "OSError"},
            }
        )
    except Exception as exc:  # pragma: no cover - dépendances spécifiques
        status.update({
            "status": "error", 
            "message": f"Erreur AM2315 : {exc}",
            "details": {"error": str(exc), "error_type": type(exc).__name__},
        })
    return status


def detect_lcd_display(lcd_enabled: bool) -> Dict[str, Any]:
    status: Dict[str, Any] = {
        "id": "lcd",
        "label": "Grove LCD RGB 16x2",
        "category": "Affichages",
        "status": "warning",
        "message": "Afficheur désactivé dans la configuration.",
        "details": {},
    }

    if not lcd_enabled:
        return status

    if not _is_linux_arm():
        status.update({"message": "Détection uniquement disponible sur Raspberry Pi."})
        return status

    try:
        try:
            from app.hardware import LCD  # type: ignore
        except ModuleNotFoundError:
            from .hardware import LCD  # type: ignore  # pragma: no cover
        lcd_class = getattr(LCD, "LCD", None)
    except ModuleNotFoundError:
        status.update(
            {
                "status": "error",
                "message": "Driver Grove LCD (app/hardware/LCD.py) introuvable.",
            }
        )
        current_app.logger.error("LCD detection failed: module 'app.hardware.LCD' not found.")
        return status
    except Exception as exc:  # pragma: no cover - dépendances spécifiques
        status.update({"status": "error", "message": f"Impossible de charger LCD.py : {exc}"})
        current_app.logger.exception("LCD detection: import error", exc_info=True)
        return status

    if lcd_class is None:
        status.update(
            {
                "status": "error",
                "message": "La classe LCD n’a pas été trouvée dans app.hardware.LCD.",
            }
        )
        current_app.logger.error("LCD detection failed: 'LCD' class missing in app.hardware.LCD")
        return status

    try:
        screen = lcd_class()  # type: ignore[call-arg]
        if hasattr(screen, "setText"):
            screen.setText("Test\nGrove LCD OK")
        if hasattr(screen, "setRGB"):
            screen.setRGB(0, 128, 64)
        status.update(
            {
                "status": "ok",
                "message": "Grove LCD RGB 16x2 détecté (test I2C réussi).",
            }
        )
        current_app.logger.info("LCD detection successful: Grove LCD responded to test command.")
    except Exception as exc:  # pragma: no cover - dépendances spécifiques
        status.update({"status": "error", "message": f"Échec de la communication LCD : {exc}"})
        current_app.logger.exception("LCD detection failed during communication", exc_info=True)
    return status


def detect_usb_camera() -> Dict[str, Any]:
    status: Dict[str, Any] = {
        "id": "usb_camera",
        "label": "Caméra USB",
        "category": "Périphériques",
        "status": "warning",
        "message": "Vérification non disponible (OpenCV manquant).",
    }

    if cv2 is None or np is None:
        try:
            current_app.logger.warning("USB camera check skipped: OpenCV or numpy not available.")
        except Exception:
            pass
        return status

    try:
        capture = cv2.VideoCapture(0)
        if not capture or not capture.isOpened():
            status.update(
                {
                    "status": "warning",
                    "message": "Aucune caméra USB accessible sur /dev/video0.",
                }
            )
            current_app.logger.warning("USB camera not accessible on /dev/video0.")
            return status
        backend = capture.getBackendName() if hasattr(capture, "getBackendName") else "unknown"
        status.update(
            {
                "status": "ok",
                "message": "Caméra USB détectée et accessible.",
                "details": {"backend": backend},
            }
        )
        current_app.logger.info("USB camera detection successful via backend '%s'.", backend)
        return status
    except Exception as exc:  # pragma: no cover - dépend matériel
        status.update({"status": "error", "message": f"Impossible d’accéder à la caméra USB : {exc}"})
        current_app.logger.exception("USB camera detection error", exc_info=True)
        return status
    finally:
        try:
            if "capture" in locals() and capture:
                capture.release()
        except Exception:
            pass


def build_hardware_overview(relay_pins: Iterable[int], *, lcd_enabled: bool = False) -> List[Dict[str, Any]]:
    overview: List[Dict[str, Any]] = []
    overview.append(detect_gpio_relays(relay_pins))
    overview.append(detect_ds18b20())
    overview.append(detect_am2315())
    overview.append(detect_lcd_display(lcd_enabled))
    overview.append(detect_usb_camera())
    overview.append(detect_host_status())
    return overview


def detect_host_status() -> Dict[str, Any]:
    status: Dict[str, Any] = {
        "id": "host",
        "label": "État du Raspberry Pi",
        "category": "Système",
        "status": "ok",
        "message": "Ressources système surveillées.",
        "details": {},
    }
    try:
        load1, _, _ = os.getloadavg()
        cpu_usage = load1
    except Exception:
        cpu_usage = None

    try:
        import psutil  # type: ignore

        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        temp = None
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for entries in temps.values():
                    if entries:
                        temp = entries[0].current
                        break
        except Exception:
            temp = None
        status["details"] = {
            "cpu": cpu_usage,
            "ram_percent": ram.percent if ram else None,
            "ram_used": getattr(ram, "used", None),
            "ram_total": getattr(ram, "total", None),
            "disk_percent": disk.percent if disk else None,
            "disk_free": getattr(disk, "free", None),
            "disk_total": getattr(disk, "total", None),
            "temperature": temp,
        }
    except ImportError:
        status.update(
            {
                "status": "warning",
                "message": "psutil non disponible, impossible de lire l’état du système.",
            }
        )
    return status
