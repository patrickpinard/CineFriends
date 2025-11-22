from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple
import time

from flask import current_app

from .models import AutomationRule, RelayState, SensorReading

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
    """Formate une valeur numérique avec un nombre de décimales spécifié
    
    Args:
        value: Valeur à formater (None pour "--")
        decimals: Nombre de décimales (défaut: 1)
    
    Returns:
        Chaîne formatée avec le nombre de décimales demandé (sans espace au début)
    """
    if value is None:
        return "--"
    # Formater avec le nombre de décimales demandé
    formatted = f"{value:.{decimals}f}"
    # Limiter à 5 caractères maximum pour l'affichage LCD (ex: "123.4")
    # Retourner sans justification pour éviter les problèmes de troncature
    return formatted[:5]


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


def _has_automation_rules(channel: int) -> bool:
    """Vérifie si un relais a des règles d'automatisation actives."""
    try:
        from .automation_engine import parse_trigger
        active_rules = AutomationRule.query.filter_by(enabled=True).all()
        for rule in active_rules:
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
                    if channel_value == channel:
                        return True
                except Exception:
                    continue
    except Exception:
        pass
    return False


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
        3: "Prise",
    }

    # Page 1, ligne 1: Temp int & ext sur une ligne
    temp_int_str = _format_value(int_temp)
    temp_ext_str = _format_value(ext_temp)
    line1 = _pad(f"Ti:{temp_int_str} Te:{temp_ext_str}")
    
    # Page 1, ligne 2: Hum int & ext sur une ligne
    hum_int_str = _format_value(int_humidity)
    hum_ext_str = _format_value(ext_humidity)
    line2 = _pad(f"Hi:{hum_int_str} He:{hum_ext_str}")

    # Page 2, ligne 1: Chauffage : ON/OFF M/A
    relay1_state = relay_states.get(1)
    relay1_state_str = _format_state(relay1_state.state if relay1_state else None)
    relay1_mode = "A" if _has_automation_rules(1) else "M"
    line3 = _pad(f"{label_map.get(1, 'Chauffage')}:{relay1_state_str} {relay1_mode}")

    # Page 2, ligne 2: LED : ON/OFF   Prise : ON/OFF
    relay2_state = relay_states.get(2)
    relay2_state_str = _format_state(relay2_state.state if relay2_state else None)
    relay3_state = relay_states.get(3)
    relay3_state_str = _format_state(relay3_state.state if relay3_state else None)
    # Format: "LED:OFF Prise:ON" (avec espace, tient dans 16 caractères)
    line4 = _pad(f"LED:{relay2_state_str} Prise:{relay3_state_str}")

    lines = [line1, line2, line3, line4]
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


def _get_lcd_page_display_seconds() -> float:
    """Récupère le temps d'affichage par page depuis les paramètres (défaut: 3 secondes)
    
    Utilise le cache global depuis app.__init__ pour éviter les requêtes DB répétées.
    """
    try:
        from . import get_lcd_display_seconds
        return get_lcd_display_seconds(current_app._get_current_object(), use_cache=True)
    except Exception:
        # Fallback si le cache n'est pas disponible
        try:
            from .models import Setting
            setting = Setting.query.filter_by(key="LCD_Page_Display_Seconds").first()
            if setting and setting.value:
                try:
                    seconds = float(str(setting.value).strip())
                    # Limiter entre 1 et 60 secondes
                    return max(1.0, min(60.0, seconds))
                except (ValueError, TypeError):
                    pass
        except Exception:
            pass
        return 3.0  # Valeur par défaut


def _push_to_lcd_cycle(pages: List[List[str]]) -> Tuple[bool, Optional[str]]:
    """Affiche toutes les pages du LCD en boucle avec un délai configurable entre chaque page"""
    if not _lcd_is_enabled():
        return False, "Afficheur LCD désactivé ou indisponible."
    try:
        device = LCD()
        frames = pages or [[_pad(""), _pad("")]]
        display_seconds = _get_lcd_page_display_seconds()
        
        for frame_index, frame in enumerate(frames):
            # Effacer l'écran avant d'afficher chaque page (sauf la première)
            if frame_index > 0:
                device.setText("")
                time.sleep(0.1)  # Petit délai pour l'effacement
            
            payload = "\n".join(frame)
            device.setText(payload)
            device.setRGB(0, 128, 64)
            
            # Respecter le délai d'affichage configuré
            time.sleep(display_seconds)
        
        return True, None
    except Exception as exc:  # pragma: no cover - dépend matériel
        current_app.logger.exception("Échec mise à jour LCD: %s", exc)
        return False, str(exc)


def _push_single_page_to_lcd(page_index: int, pages: List[List[str]], clear_before: bool = True) -> Tuple[bool, Optional[str]]:
    """Affiche une seule page spécifique du LCD (pour le défilement automatique)
    
    Args:
        page_index: Index de la page à afficher
        pages: Liste des pages disponibles
        clear_before: Si True, efface l'écran avant d'afficher la nouvelle page
    """
    if not _lcd_is_enabled():
        return False, "Afficheur LCD désactivé ou indisponible."
    try:
        device = LCD()
        frames = pages or [[_pad(""), _pad("")]]
        if 0 <= page_index < len(frames):
            # Effacer l'écran avant d'afficher la nouvelle page
            if clear_before:
                device.setText("")
                time.sleep(0.1)  # Petit délai pour l'effacement
            
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
    
    # Récupérer le délai d'affichage pour la prévisualisation
    display_seconds = _get_lcd_page_display_seconds()
    
    return {
        "lines": lines,
        "pages": pages,
        "metadata": metadata,
        "generated_at": datetime.utcnow(),
        "push_success": success,
        "push_error": error,
        "driver_available": _lcd_is_enabled(),
        "display_seconds": display_seconds,
    }

