from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple
import time

from flask import current_app

from .models import RelayState, SensorReading

try:  # pragma: no cover - dépend du matériel
    from .hardware.LCD import LCD
except Exception:  # pragma: no cover - environnement local
    LCD = None  # type: ignore

LINE_LENGTH = 16
LINE_COUNT = 2
RELAY_CHANNELS = (1, 2, 3)

# État global pour le défilement automatique des pages LCD
_lcd_current_page_index = 0


def _lcd_is_enabled() -> bool:
    return bool(LCD) and current_app.config.get("LCD_ENABLED", False)


def _latest_reading(sensor_type: str, metric: str) -> Optional[SensorReading]:
    return (
        SensorReading.query.filter(
            SensorReading.sensor_type == sensor_type,
            SensorReading.metric == metric,
            SensorReading.value.isnot(None),
        )
        .order_by(SensorReading.created_at.desc())
        .first()
    )


def _format_value(value: Optional[float], decimals: int = 1) -> str:
    if value is None:
        return "--"
    return f"{value:.{decimals}f}"[:5].rjust(4)


def _format_state(state: Optional[str]) -> str:
    if state == "on":
        return "ON"
    if state == "off":
        return "OFF"
    return "--"


def _pad(text: str) -> str:
    return text[:LINE_LENGTH].ljust(LINE_LENGTH)


def _latest_relay_state(channel: int) -> Optional[RelayState]:
    return (
        RelayState.query.filter_by(channel=channel)
        .order_by(RelayState.created_at.desc())
        .first()
    )


def build_lcd_lines() -> Tuple[List[str], dict]:
    """Construit les lignes destinées à l'afficheur."""
    ds_temp = _latest_reading("ds18b20", "temperature")
    am_temp = _latest_reading("am2315", "temperature")
    ds_humidity = _latest_reading("ds18b20", "humidity")
    am_humidity = _latest_reading("am2315", "humidity")

    relay_states = {
        channel: _latest_relay_state(channel)
        for channel in RELAY_CHANNELS
    }

    int_temp = float(ds_temp.value) if ds_temp and ds_temp.value is not None else None
    ext_temp = float(am_temp.value) if am_temp and am_temp.value is not None else None
    int_humidity = float(ds_humidity.value) if ds_humidity and ds_humidity.value is not None else None
    ext_humidity = float(am_humidity.value) if am_humidity and am_humidity.value is not None else None

    timestamps = [
        reading.created_at
        for reading in (ds_temp, am_temp, ds_humidity, am_humidity)
        if reading and reading.created_at
    ]
    last_measure_at = max(timestamps) if timestamps else None

    label_map = {
        1: "Chauffage",
        2: "Lampe",
        3: "Prise 240V",
    }

    def fmt(label: str, value: Optional[str]) -> str:
        return _pad(f"{label[:15]} {value or '--'}")

    line1 = fmt("Temp int °C :", _format_value(int_temp))
    line2 = fmt("Temp ext °C :", _format_value(ext_temp))
    line3 = fmt("Hum int % :", _format_value(int_humidity))
    line4 = fmt("Hum ext % :", _format_value(ext_humidity))

    relay_lines = []
    for channel in RELAY_CHANNELS:
        state = _format_state(relay_states[channel].state if relay_states[channel] else None)
        label = label_map.get(channel, f"Relais {channel}")
        relay_lines.append(_pad(f"{label[:13]} : {state}"))

    lines = [line1, line2, line3, line4, *relay_lines]
    metadata = {
        "internal_temp": int_temp,
        "external_temp": ext_temp,
        "internal_humidity": int_humidity,
        "external_humidity": ext_humidity,
        "relay_states": {
            channel: (relay_states[channel].state if relay_states[channel] else "unknown")
            for channel in RELAY_CHANNELS
        },
        "last_measure_at": last_measure_at,
    }
    return lines, metadata


def _chunk_lines(lines: List[str], size: int = LINE_COUNT) -> List[List[str]]:
    frames: List[List[str]] = []
    for index in range(0, len(lines), size):
        frame = lines[index:index + size]
        while len(frame) < size:
            frame.append(_pad(""))
        frames.append(frame)
    return frames


def _push_to_lcd_cycle(pages: List[List[str]]) -> Tuple[bool, Optional[str]]:
    """Affiche toutes les pages du LCD en boucle avec un délai de 3 secondes entre chaque page"""
    if not _lcd_is_enabled():
        return False, "Afficheur LCD désactivé ou indisponible."
    try:
        device = LCD()
        frames = pages or [[_pad(""), _pad("")]]
        for frame in frames:
            payload = "\n".join(frame)
            device.setText(payload)
            device.setRGB(0, 128, 64)
            time.sleep(3)
        return True, None
    except Exception as exc:  # pragma: no cover - dépend matériel
        current_app.logger.exception("Échec mise à jour LCD: %s", exc)
        return False, str(exc)


def _push_single_page_to_lcd(page_index: int, pages: List[List[str]]) -> Tuple[bool, Optional[str]]:
    """Affiche une seule page spécifique du LCD (pour le défilement automatique)"""
    if not _lcd_is_enabled():
        return False, "Afficheur LCD désactivé ou indisponible."
    try:
        device = LCD()
        frames = pages or [[_pad(""), _pad("")]]
        if 0 <= page_index < len(frames):
            frame = frames[page_index]
            payload = "\n".join(frame)
            device.setText(payload)
            device.setRGB(0, 128, 64)
            return True, None
        return False, f"Index de page invalide: {page_index}"
    except Exception as exc:  # pragma: no cover - dépend matériel
        current_app.logger.exception("Échec mise à jour LCD (page %s): %s", page_index, exc)
        return False, str(exc)


def auto_scroll_lcd_pages() -> None:
    """Fait défiler automatiquement les pages du LCD toutes les 3 secondes"""
    global _lcd_current_page_index
    
    if not _lcd_is_enabled():
        return
    
    try:
        # Construire les pages actuelles avec les dernières données
        lines, _ = build_lcd_lines()
        pages = _chunk_lines(lines)
        
        if not pages:
            return
        
        # Afficher la page actuelle
        success, error = _push_single_page_to_lcd(_lcd_current_page_index, pages)
        
        if success:
            # Passer à la page suivante (boucle)
            _lcd_current_page_index = (_lcd_current_page_index + 1) % len(pages)
        else:
            current_app.logger.warning("Échec défilement LCD automatique: %s", error)
    except Exception as exc:  # pragma: no cover - dépend matériel
        current_app.logger.exception("Erreur lors du défilement automatique LCD: %s", exc)


def refresh_lcd_display(*, push: bool = False) -> dict:
    lines, metadata = build_lcd_lines()
    pages = _chunk_lines(lines)
    success: Optional[bool] = None
    error: Optional[str] = None
    if push:
        success, error = _push_to_lcd_cycle(pages)
    return {
        "lines": lines,
        "pages": pages,
        "metadata": metadata,
        "generated_at": datetime.utcnow(),
        "push_success": success,
        "push_error": error,
        "driver_available": _lcd_is_enabled(),
    }

