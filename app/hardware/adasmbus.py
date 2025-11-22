"""I2C interface that mimics the Python SMBus API."""

from __future__ import annotations

from ctypes import POINTER, Structure, c_uint8, c_uint16, c_uint32, cast, create_string_buffer, pointer
from fcntl import ioctl
import struct

I2C_M_TEN = 0x0010
I2C_M_RD = 0x0001
I2C_M_STOP = 0x8000
I2C_M_NOSTART = 0x4000
I2C_M_REV_DIR_ADDR = 0x2000
I2C_M_IGNORE_NAK = 0x1000
I2C_M_NO_RD_ACK = 0x0800
I2C_M_RECV_LEN = 0x0400

I2C_SLAVE = 0x0703
I2C_SLAVE_FORCE = 0x0706
I2C_TENBIT = 0x0704
I2C_FUNCS = 0x0705
I2C_RDWR = 0x0707
I2C_PEC = 0x0708
I2C_SMBUS = 0x0720


class i2c_msg(Structure):
    _fields_ = [
        ("addr", c_uint16),
        ("flags", c_uint16),
        ("len", c_uint16),
        ("buf", POINTER(c_uint8)),
    ]


class i2c_rdwr_ioctl_data(Structure):
    _fields_ = [("msgs", POINTER(i2c_msg)), ("nmsgs", c_uint32)]


def make_i2c_rdwr_data(messages):
    msg_data_type = i2c_msg * len(messages)
    msg_data = msg_data_type()
    for i, message in enumerate(messages):
        msg_data[i].addr = message[0] & 0x7F
        msg_data[i].flags = message[1]
        msg_data[i].len = message[2]
        msg_data[i].buf = message[3]
    data = i2c_rdwr_ioctl_data()
    data.msgs = msg_data
    data.nmsgs = len(messages)
    return data


class SMBus(object):
    def __init__(self, bus=None):
        self._device = None
        if bus is not None:
            self.open(bus)

    def __del__(self):
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def open(self, bus):
        if self._device is not None:
            self.close()
        self._device = open(f"/dev/i2c-{bus}", "r+b", buffering=0)

    def close(self):
        if self._device is not None:
            self._device.close()
            self._device = None

    def _select_device(self, addr):
        ioctl(self._device.fileno(), I2C_SLAVE, addr & 0x7F)

    def read_byte(self, addr):
        assert self._device is not None
        self._select_device(addr)
        return ord(self._device.read(1))

    def read_bytes(self, addr, number):
        assert self._device is not None
        self._select_device(addr)
        return self._device.read(number)

    def read_byte_data(self, addr, cmd):
        assert self._device is not None
        reg = c_uint8(cmd)
        result = c_uint8()
        request = make_i2c_rdwr_data(
            [
                (addr, 0, 1, pointer(reg)),
                (addr, I2C_M_RD, 1, pointer(result)),
            ]
        )
        ioctl(self._device.fileno(), I2C_RDWR, request)
        return result.value

    def read_word_data(self, addr, cmd):
        assert self._device is not None
        reg = c_uint8(cmd)
        result = c_uint16()
        request = make_i2c_rdwr_data(
            [
                (addr, 0, 1, pointer(reg)),
                (addr, I2C_M_RD, 2, cast(pointer(result), POINTER(c_uint8))),
            ]
        )
        ioctl(self._device.fileno(), I2C_RDWR, request)
        return result.value

    def am2315_read_i2c_block_data(self, addr, cmd, length=32):
        assert self._device is not None
        result = create_string_buffer(length)
        request = make_i2c_rdwr_data(
            [
                (addr, I2C_M_RD, length, cast(result, POINTER(c_uint8))),
            ]
        )
        ioctl(self._device.fileno(), I2C_RDWR, request)
        return bytearray(result.raw)

    def read_i2c_block_data(self, addr, cmd, length=32):
        assert self._device is not None
        reg = c_uint8(cmd)
        result = create_string_buffer(length)
        request = make_i2c_rdwr_data(
            [
                (addr, 0, 1, pointer(reg)),
                (addr, I2C_M_RD, length, cast(result, POINTER(c_uint8))),
            ]
        )
        ioctl(self._device.fileno(), I2C_RDWR, request)
        return bytearray(result.raw)

    def write_byte(self, addr, val):
        assert self._device is not None
        self._select_device(addr)
        data = bytearray(1)
        data[0] = val & 0xFF
        self._device.write(data)

    def write_bytes(self, addr, buf):
        assert self._device is not None
        self._select_device(addr)
        self._device.write(buf)

    def write_byte_data(self, addr, cmd, val):
        assert self._device is not None
        data = bytearray(2)
        data[0] = cmd & 0xFF
        data[1] = val & 0xFF
        self._select_device(addr)
        self._device.write(data)

    def write_i2c_block_data(self, addr, cmd, vals):
        assert self._device is not None
        data = bytearray(len(vals) + 1)
        data[0] = cmd & 0xFF
        data[1:] = vals[0:]
        self._select_device(addr)
        self._device.write(data)

