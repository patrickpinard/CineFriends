from __future__ import annotations

# Moved from project root to app/hardware/LCD.py

# Auteur  : Patrick Pinard
# Date    : 3.10.2022
# Objet   : Gestion du LCD
# Source  : myLCDLib.py
# Version : 1.0
# -*- coding: utf-8 -*-

import sys
import time

try:
    from smbus import SMBus as _SMBus  # type: ignore
except ImportError:
    try:
        from smbus2 import SMBus as _SMBus  # type: ignore
    except ImportError as exc:  # pragma: no cover - unmet dependency
        raise ImportError(
            "Aucun module 'smbus' détecté. Installez 'python3-smbus' (apt) ou 'smbus2' (pip)."
        ) from exc


class LCD(object):
    """
    Classe pour écran LCD :
    """

    def __init__(self):
        """
        Constructeur LCD :
        """

        if sys.platform == "uwp":
            import winrt_smbus as smbus  # type: ignore

            self.bus = smbus.SMBus(1)
        else:
            import RPi.GPIO as GPIO  # type: ignore

            rev = GPIO.RPI_REVISION
            if rev == 2 or rev == 3:
                self.bus = _SMBus(1)
            else:
                self.bus = _SMBus(0)

        # this device has two I2C addresses
        self.DISPLAY_RGB_ADDR = 0x62
        self.DISPLAY_TEXT_ADDR = 0x3E
        

    def setRGB(self, r, g, b):
        self.bus.write_byte_data(self.DISPLAY_RGB_ADDR, 0, 0)
        self.bus.write_byte_data(self.DISPLAY_RGB_ADDR, 1, 0)
        self.bus.write_byte_data(self.DISPLAY_RGB_ADDR, 0x08, 0xAA)
        self.bus.write_byte_data(self.DISPLAY_RGB_ADDR, 4, r)
        self.bus.write_byte_data(self.DISPLAY_RGB_ADDR, 3, g)
        self.bus.write_byte_data(self.DISPLAY_RGB_ADDR, 2, b)

    def textCommand(self, cmd):
        self.bus.write_byte_data(self.DISPLAY_TEXT_ADDR, 0x80, cmd)

    def setText(self, text):
        self.textCommand(0x01)
        time.sleep(0.05)
        self.textCommand(0x08 | 0x04)
        self.textCommand(0x28)
        time.sleep(0.05)
        count = 0
        row = 0
        for c in text:
            if c == "\n" or count == 16:
                count = 0
                row += 1
                if row == 2:
                    break
                self.textCommand(0xC0)
                if c == "\n":
                    continue
            count += 1
            self.bus.write_byte_data(self.DISPLAY_TEXT_ADDR, 0x40, ord(c))


def setText_norefresh(text):
    raise NotImplementedError("Function retained for completeness, not used by app.")

