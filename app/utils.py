from __future__ import annotations

import os
import platform
import secrets
import time
import calendar
from importlib import import_module
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List

from flask import current_app
from werkzeug.datastructures import FileStorage


def utc_to_local(utc_dt: datetime) -> datetime:
    """Convertit un datetime UTC en datetime local du système (Raspberry Pi)"""
    if utc_dt is None:
        return utc_dt
    
    # Utiliser la méthode la plus fiable : comparer datetime.utcnow() et datetime.now()
    # pour obtenir l'offset réel du système à ce moment précis
    # Cette méthode prend automatiquement en compte l'heure d'été/hiver
    now_utc = datetime.utcnow()
    now_local = datetime.now()
    
    # Calculer l'offset en secondes (positif si local est à l'est de UTC)
    offset_seconds = (now_local - now_utc).total_seconds()
    
    # Appliquer l'offset : ajouter les secondes pour convertir UTC vers local
    local_dt = utc_dt + timedelta(seconds=offset_seconds)
    return local_dt


def format_local_datetime(dt: datetime, format_str: str = "%d/%m/%Y %H:%M") -> str:
    """Formate un datetime UTC en heure locale du système
    
    Args:
        dt: datetime UTC à convertir
        format_str: Format de sortie (par défaut "%d/%m/%Y %H:%M")
    
    Returns:
        Chaîne formatée en heure locale
    """
    if dt is None:
        return ""
    local_dt = utc_to_local(dt)
    return local_dt.strftime(format_str)


def utc_to_unix_ms_for_chart(utc_dt: datetime) -> int:
    """Convertit un datetime UTC en timestamp Unix (millisecondes) pour les graphiques JavaScript
    
    Cette fonction garantit que JavaScript affichera l'heure locale du Raspberry Pi
    dans les graphiques. Elle ajuste les timestamps UTC en ajoutant 2 heures pour corriger
    le décalage d'affichage dans les graphiques.
    
    IMPORTANT: Cette fonction utilise une seule méthode de conversion pour toutes les mesures
    (températures, humidités, relais) pour garantir la cohérence.
    
    Args:
        utc_dt: datetime UTC depuis la base de données
    
    Returns:
        Timestamp Unix en millisecondes (pour JavaScript)
    """
    if utc_dt is None:
        return 0
    
    # Ajouter 2 heures (7200 secondes) au timestamp UTC pour corriger le décalage d'affichage
    # Cela garantit que l'heure locale du Raspberry Pi est correctement affichée dans les graphiques
    adjusted_dt = utc_dt + timedelta(hours=2)
    timestamp_ms = int(adjusted_dt.timestamp() * 1000)
    
    return timestamp_ms

def _import_optional_module(module_name: str):
    try:
        return import_module(module_name)
    except Exception:
        return None

np = _import_optional_module("numpy")
cv2 = _import_optional_module("cv2")
lcd_module = _import_optional_module("app.hardware.LCD") or _import_optional_module("hardware.LCD")
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
                "message": "psutil non disponible, impossible de lire l'état du système.",
            }
        )
    return status


def purge_sensor_data(retention_days: int = 30, perform_purge: bool = False) -> Dict[str, Any]:
    """
    Purge les données de capteurs selon les règles suivantes :
    - Supprime les données de plus de retention_days jours
    - Pour les données entre 7 jours et retention_days jours, ne garde qu'1 mesure par heure
    
    Args:
        retention_days: Nombre de jours de conservation (défaut: 30)
        perform_purge: Si False, retourne seulement les statistiques sans purger
    
    Returns:
        Dict avec les statistiques de purge
    """
    from .models import SensorReading, RelayState, Setting
    from sqlalchemy import func, and_
    
    now = datetime.utcnow()
    retention_threshold = now - timedelta(days=retention_days)
    week_threshold = now - timedelta(days=7)
    
    stats = {
        "retention_days": retention_days,
        "total_readings": SensorReading.query.count(),
        "readings_to_delete_old": 0,
        "readings_to_reduce": 0,
        "readings_deleted_old": 0,
        "readings_deleted_reduced": 0,
        "relay_states_to_delete": 0,
        "relay_states_deleted": 0,
    }
    
    if not perform_purge:
        # Mode simulation : compter seulement
        stats["readings_to_delete_old"] = SensorReading.query.filter(
            SensorReading.created_at < retention_threshold
        ).count()
        
        stats["readings_to_reduce"] = SensorReading.query.filter(
            and_(
                SensorReading.created_at >= retention_threshold,
                SensorReading.created_at < week_threshold
            )
        ).count()
        
        stats["relay_states_to_delete"] = RelayState.query.filter(
            RelayState.created_at < retention_threshold
        ).count()
        
        return stats
    
    # Mode purge réel
    try:
        # 1. Supprimer les données de plus de retention_days jours
        old_readings_query = SensorReading.query.filter(
            SensorReading.created_at < retention_threshold
        )
        stats["readings_deleted_old"] = old_readings_query.count()
        old_readings_query.delete(synchronize_session=False)
        
        # 2. Réduire les données entre 7 jours et retention_days jours (1 mesure/heure)
        # Pour chaque combinaison (sensor_type, metric, sensor_id), on garde la première mesure de chaque heure
        readings_to_reduce = SensorReading.query.filter(
            and_(
                SensorReading.created_at >= retention_threshold,
                SensorReading.created_at < week_threshold
            )
        ).order_by(
            SensorReading.sensor_type,
            SensorReading.metric,
            SensorReading.sensor_id,
            SensorReading.created_at
        ).all()
        
        # Grouper par (sensor_type, metric, sensor_id, année, mois, jour, heure)
        # et garder seulement la première mesure de chaque groupe
        readings_to_keep = set()
        readings_to_delete_ids = []
        
        current_group = None
        for reading in readings_to_reduce:
            # Créer une clé de groupe : (sensor_type, metric, sensor_id, année, mois, jour, heure)
            group_key = (
                reading.sensor_type or "",
                reading.metric or "",
                reading.sensor_id or "",
                reading.created_at.year,
                reading.created_at.month,
                reading.created_at.day,
                reading.created_at.hour
            )
            
            if group_key != current_group:
                # Nouveau groupe : garder cette mesure
                current_group = group_key
                readings_to_keep.add(reading.id)
            else:
                # Même groupe : marquer pour suppression
                readings_to_delete_ids.append(reading.id)
        
        # Supprimer les mesures en double
        if readings_to_delete_ids:
            SensorReading.query.filter(SensorReading.id.in_(readings_to_delete_ids)).delete(synchronize_session=False)
            stats["readings_deleted_reduced"] = len(readings_to_delete_ids)
        
        # 3. Supprimer les états de relais anciens
        old_relay_states_query = RelayState.query.filter(
            RelayState.created_at < retention_threshold
        )
        stats["relay_states_deleted"] = old_relay_states_query.count()
        old_relay_states_query.delete(synchronize_session=False)
        
        # Note: La sauvegarde de la configuration de rétention et le commit sont gérés dans la route admin
        
        return stats
    except Exception as exc:
        current_app.logger.exception("Erreur lors de la purge des données: %s", exc)
        stats["error"] = str(exc)
        return stats
