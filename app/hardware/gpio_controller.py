from __future__ import annotations

import logging
from typing import Dict, Tuple

from flask import current_app

from ..models import Setting
from ..utils import _is_linux_arm  # type: ignore[attr-defined]

try:  # pragma: no cover - dépend de l’environnement Raspberry Pi
    import RPi.GPIO as GPIO  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    GPIO = None  # type: ignore


DEFAULT_RELAY_PINS: Dict[int, int] = {1: 26, 2: 20, 3: 21}
_INITIALIZED = False
_ACTIVE_LOW = True


def _load_active_low() -> bool:
    setting = Setting.query.filter_by(key="Relay_ActiveLow").first()
    if not setting:
        return True
    value = (setting.value or "").strip().lower()
    if value in {"0", "false", "no", "off"}:
        return False
    return True


def _get_relay_pins() -> Dict[int, int]:
    pins = DEFAULT_RELAY_PINS.copy()
    for channel, key in enumerate(["Relay_Ch1", "Relay_Ch2", "Relay_Ch3"], start=1):
        setting = Setting.query.filter_by(key=key).first()
        if setting and setting.value:
            try:
                pins[channel] = int(setting.value)
            except (TypeError, ValueError):
                continue
    return pins


def _get_relay_name(channel: int) -> str:
    key = f"Relay_Name_Ch{channel}"
    setting = Setting.query.filter_by(key=key).first()
    if setting and setting.value:
        return setting.value
    return f"Relais {channel}"


def get_configured_relay_pins() -> Dict[int, int]:
    return _get_relay_pins()


def is_active_low() -> bool:
    return _load_active_low()


def hardware_available() -> bool:
    return _is_linux_arm() and GPIO is not None


def _ensure_setup() -> Tuple[bool, Dict[int, int]]:
    global _INITIALIZED, _ACTIVE_LOW
    if not _is_linux_arm() or GPIO is None:
        return False, {}

    pins = _get_relay_pins()
    current_mode = GPIO.getmode() if GPIO else None  # type: ignore[attr-defined]
    if not _INITIALIZED or current_mode is None:
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        _ACTIVE_LOW = _load_active_low()
        for pin in pins.values():
            try:
                GPIO.setup(pin, GPIO.OUT)
                GPIO.output(pin, GPIO.HIGH if _ACTIVE_LOW else GPIO.LOW)
            except Exception as exc:  # pragma: no cover - hardware spécifique
                current_app.logger.warning("Impossible d’initialiser le GPIO %s: %s", pin, exc)
        _INITIALIZED = True
    return True, pins


def set_relay_state(channel: int, state: str) -> Dict[str, str]:
    ok, pins = _ensure_setup()
    state_lower = state.strip().lower()
    if not ok:
        return {"status": "unavailable", "message": "Contrôle GPIO indisponible sur cette plateforme."}
    pin = pins.get(channel)
    if not pin:
        return {"status": "error", "message": f"Aucun GPIO configuré pour le relais {channel}."}
    if state_lower not in {"on", "off", "toggle"}:
        return {"status": "error", "message": f"État {state} non supporté (attendu: on/off/toggle)."}
    try:
        if state_lower == "toggle":
            current_level = GPIO.input(pin)
            desired_level = GPIO.LOW if current_level == GPIO.HIGH else GPIO.HIGH
        else:
            desired_level = GPIO.LOW if (state_lower == "on") == _ACTIVE_LOW else GPIO.HIGH
            if _ACTIVE_LOW and state_lower == "off":
                desired_level = GPIO.HIGH
            elif not _ACTIVE_LOW and state_lower == "off":
                desired_level = GPIO.LOW
        GPIO.output(pin, desired_level)
        return {
            "status": "ok",
            "message": f"Relais {channel} -> {state_lower}",
            "pin": str(pin),
            "active_low": str(_ACTIVE_LOW),
        }
    except Exception as exc:  # pragma: no cover - hardware spécifique
        logging.exception("Erreur lors du pilotage du relais %s", channel)
        return {"status": "error", "message": f"Échec du pilotage du relais {channel}: {exc}"}


def get_relay_states() -> Dict[int, str]:
    ok, pins = _ensure_setup()
    states: Dict[int, str] = {}
    if not ok:
        return states
    for channel, pin in pins.items():
        try:
            level = GPIO.input(pin)
            if _ACTIVE_LOW:
                states[channel] = "on" if level == GPIO.LOW else "off"
            else:
                states[channel] = "on" if level == GPIO.HIGH else "off"
        except Exception:
            states[channel] = "unknown"
    return states


def get_relay_labels() -> Dict[int, str]:
    pins = _get_relay_pins()
    return {channel: _get_relay_name(channel) for channel in pins}

