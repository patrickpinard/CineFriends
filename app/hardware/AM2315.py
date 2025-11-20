#!usr/bin/python
# modified for GroveWeatherPi to return CRC information
# SwitchDoc Labs, 2019
# Adaptation pour le Dashboard utilisant le driver d’origine (adasmbus)

# COPYRIGHT 2016 Robert Wolterman
# MIT License, see LICENSE file for details

from __future__ import annotations

import time

try:
    import RPi.GPIO as GPIO

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
except ImportError:  # pragma: no cover - dépend du hardware
    GPIO = None  # type: ignore

from . import adasmbus

AM2315_I2CADDR = 0x5C
AM2315_READREG = 0x03
MAXREADATTEMPT = 10

AM2315DEBUG = False


class AM2315:
    """Base functionality for AM2315 humidity and temperature sensor."""

    def __init__(self, address=AM2315_I2CADDR, i2c=None, powerpin=0, **kwargs):
        self.powerpin = powerpin
        if self.powerpin != 0:
            if GPIO is None:
                raise RuntimeError(
                    "RPi.GPIO n’est pas disponible : impossible de contrôler powerpin."
                )
            GPIO.setup(self.powerpin, GPIO.OUT)
            GPIO.output(self.powerpin, True)
            time.sleep(1.0)

        bus_number = kwargs.get("bus", 1)
        self._device = adasmbus.SMBus(bus_number)

        self.humidity = 0
        self.temperature = 0
        self.crc = 0
        self.AM2315PreviousTemp = -1000
        self.goodreads = 0
        self.badreadings = 0
        self.badcrcs = 0
        self.retrys = 0
        self.powercycles = 0

    def powerCycleAM2315(self):
        if self.powerpin == 0 or GPIO is None:
            return
        if AM2315DEBUG:
            print("power cycling AM2315")
        GPIO.output(self.powerpin, False)
        time.sleep(10.50)
        GPIO.output(self.powerpin, True)
        time.sleep(1.50)
        self.powercycles += 1

    @staticmethod
    def verify_crc(char: bytes | bytearray) -> int:
        """Returns the 16-bit CRC of sensor data."""
        crc = 0xFFFF
        for l in char:
            crc = crc ^ l
            for _ in range(1, 9):
                if crc & 0x01:
                    crc = crc >> 1
                    crc = crc ^ 0xA001
                else:
                    crc = crc >> 1
        return crc

    def _fast_read_data(self):
        try:
            self._device.write_byte_data(AM2315_I2CADDR, AM2315_READREG, 0x00)
            time.sleep(0.050)
        except Exception:
            self._device.write_byte_data(AM2315_I2CADDR, AM2315_READREG, 0x00)
            time.sleep(0.050)

        self._device.write_i2c_block_data(AM2315_I2CADDR, AM2315_READREG, [0x00, 0x04])
        time.sleep(0.050)
        tmp = self._device.am2315_read_i2c_block_data(AM2315_I2CADDR, AM2315_READREG, 8)

        self.temperature = (((tmp[4] & 0x7F) << 8) | tmp[5]) / 10.0
        self.humidity = ((tmp[2] << 8) | tmp[3]) / 10.0

        self.crc = (tmp[7] << 8) | tmp[6]
        t = bytearray([tmp[0], tmp[1], tmp[2], tmp[3], tmp[4], tmp[5]])
        c = self.verify_crc(t)

        if (self.crc != c) or (c == 0):
            if AM2315DEBUG:
                print("AM2314 BAD CRC")
            self.crc = -1
        elif AM2315DEBUG:
            print("Fast Read AM2315temperature=", self.temperature)
            print("Fast Read AM2315humdity=", self.humidity)
            print("Fast Read AM2315crc=", self.crc)
            print("Fast Read AM2315c=", c)

    def _read_data(self):
        count = 0
        tmp = None
        powercyclecount = 0
        last_exception = None
        
        # Délai initial pour réveiller le capteur s'il est en veille
        if count == 0:
            time.sleep(0.8)
        
        while count <= MAXREADATTEMPT:
            try:
                try:
                    # Tentative de réveil du capteur
                    self._device.write_byte_data(AM2315_I2CADDR, AM2315_READREG, 0x00)
                    time.sleep(0.050)
                except OSError as e:
                    # Erreur I2C - capteur peut être déconnecté
                    last_exception = e
                    if AM2315DEBUG:
                        print(f"Wake Byte Fail (OSError): {e}")
                    time.sleep(2.000)
                    try:
                        self._device.write_byte_data(AM2315_I2CADDR, AM2315_READREG, 0x00)
                        time.sleep(0.001)
                        time.sleep(0.050)
                    except Exception as e2:
                        last_exception = e2
                        if AM2315DEBUG:
                            print(f"Wake Byte Fail (retry): {e2}")
                except Exception as e:
                    last_exception = e
                    if AM2315DEBUG:
                        print(f"Wake Byte Fail: {e}")
                    time.sleep(2.000)
                    try:
                        self._device.write_byte_data(AM2315_I2CADDR, AM2315_READREG, 0x00)
                        time.sleep(0.001)
                        time.sleep(0.050)
                    except Exception as e2:
                        last_exception = e2

                # Demander la lecture
                self._device.write_i2c_block_data(
                    AM2315_I2CADDR, AM2315_READREG, [0x00, 0x04]
                )
                time.sleep(0.09)
                
                # Lire les données
                tmp = self._device.am2315_read_i2c_block_data(
                    AM2315_I2CADDR, AM2315_READREG, 8
                )
                
                # Parser les données
                self.temperature = (((tmp[4] & 0x7F) << 8) | tmp[5]) / 10.0
                self.humidity = ((tmp[2] << 8) | tmp[3]) / 10.0
                
                # Validation des données
                if self.AM2315PreviousTemp != -1000:
                    if self.humidity < 0.01 or self.humidity > 100.0:
                        if AM2315DEBUG:
                            print(">>>>>>>>>>>>>")
                            print("Bad AM2315 Humidity = ", self.temperature)
                            print(">>>>>>>>>>>>>")
                        self.badreadings += 1
                        tmp = None
                    elif abs(self.temperature - self.AM2315PreviousTemp) > 10.0:
                        if AM2315DEBUG:
                            print(">>>>>>>>>>>>>")
                            print("Bad AM2315 Temperature = ", self.temperature)
                            print(">>>>>>>>>>>>>")
                        self.badreadings += 1
                        tmp = None
                    else:
                        self.AM2315PreviousTemp = self.temperature
                else:
                    self.AM2315PreviousTemp = self.temperature
                    
                if tmp is not None:
                    break
            except OSError as e:
                # Erreur I2C - probablement capteur déconnecté ou bus inaccessible
                last_exception = e
                if AM2315DEBUG:
                    print(f"AM2315 OSError (count={count}): {e}")
            except Exception as e:
                last_exception = e
                if AM2315DEBUG:
                    print(f"AM2315readCount = {count}, Exception: {e}")
            count += 1
            self.retrys += 1
            time.sleep(0.10)
            if self.powerpin != 0 and GPIO is not None:
                if count > MAXREADATTEMPT:
                    self.powerCycleAM2315()
                    if powercyclecount <= 2:
                        powercyclecount += 1  # Correction: += au lieu de +
                        count = 0

        if tmp is None:
            error_msg = "Impossible de lire des données AM2315."
            if last_exception:
                error_msg += f" Dernière erreur: {type(last_exception).__name__}: {last_exception}"
            raise RuntimeError(error_msg)

        self.humidity = ((tmp[2] << 8) | tmp[3]) / 10.0
        self.temperature = (((tmp[4] & 0x7F) << 8) | tmp[5]) / 10.0
        if tmp[4] & 0x80:
            self.temperature = -self.temperature

        self.crc = (tmp[7] << 8) | tmp[6]
        t = bytearray([tmp[0], tmp[1], tmp[2], tmp[3], tmp[4], tmp[5]])
        c = self.verify_crc(t)

        if AM2315DEBUG:
            print("AM2315temperature=", self.temperature)
            print("AM2315humdity=", self.humidity)
            print("AM2315crc=", self.crc)
            print("AM2315c=", c)

        if (self.crc != c) or (c == 0):
            if AM2315DEBUG:
                print("AM2314 BAD CRC")
            self.badcrcs += 1
            self.crc = -1
        else:
            self.goodreads += 1

    def fast_read_temperature(self):
        self._fast_read_data()
        return self.temperature

    def read_temperature(self):
        self._read_data()
        return self.temperature

    def read_humidity(self):
        self._read_data()
        return self.humidity

    def read_humidity_temperature(self):
        self._read_data()
        return (self.humidity, self.temperature)

    def read_humidity_temperature_crc(self):
        self._read_data()
        return (self.humidity, self.temperature, self.crc)

    def read_status_info(self):
        return (
            self.goodreads,
            self.badreadings,
            self.badcrcs,
            self.retrys,
            self.powercycles,
        )


if __name__ == "__main__":  # pragma: no cover - outil de débogage
    am2315 = AM2315()
    print(am2315.read_temperature())
    print(am2315.read_humidity())
    print(am2315.read_humidity_temperature())
    print(am2315.read_humidity_temperature_crc())
