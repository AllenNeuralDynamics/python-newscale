"""Utilities for accessing New Scale devices implemented as usbxpress devices."""

try:  # cache appeared in 3.9
    from functools import cache
except ImportError:
    from functools import lru_cache as cache
from serial import Serial
from serial.tools.list_ports import comports as list_comports
from sys import platform as PLATFORM
if PLATFORM == 'win32':
    from newscale.usbxpress import USBXpressLib, USBXpressDevice

VID_NEWSCALE = 0x10c4
PID_NEWSCALE_COMPORT = 0xea60
PID_NEWSCALE_USBX = 0xea61


@cache
def get_instances():
    """Factory function to get all New Scale USB Serial hubs, regardless
    of VID/PID. These will be returned in a dict, keyed by serial number, where
    the values are either Pyserial or NewScaleSerial objects.

    Usage:
        instances = NewScaleSerial.get_instances()
        -> [newScaleSerial1, newScaleSerial2]
        for instance in instances:
            print('serial number = ', instance.get_serial_number())
    """
    instances = {}
    if PLATFORM == 'linux':
        for comport in list_comports():
            if comport.vid == VID_NEWSCALE:
                if comport.pid in [PID_NEWSCALE_COMPORT, PID_NEWSCALE_USBX]:
                    hwid = comport.hwid
                    serial_number = hwid.split()[2].split('=')[1]
                    instances[serial_number] = (NewScaleSerial(serial_number,
                                                pyserial_device=Serial(comport.device)))
    elif PLATFORM == 'win32':
        n = USBXpressLib().get_num_devices()
        for i in range(n):
            device = USBXpressDevice(i)
            if int(device.get_vid(), 16) == VID_NEWSCALE:
                if int(device.get_pid(), 16) == PID_NEWSCALE_USBX:
                    serial_number = device.get_serial_number()
                    instances[serial_number] = (NewScaleSerial(serial_number,
                                                usbxpress_device=device))
        for comport in list_comports():
            if comport.vid == VID_NEWSCALE:
                if comport.pid == PID_NEWSCALE_COMPORT:
                    hwid = comport.hwid
                    serial_number = hwid.split()[2].split('=')[1]
                    instances[serial_number] = (NewScaleSerial(serial_number,
                                                pyserial_device=Serial(comport.device)))
    return instances


class NewScaleSerial:
    """Wrapper for NewScale USB hubs with a pyserial-like interface."""

    # FIXME: technically, we don't need to the serial number to create this
    #   wrapper. Maybe we can infer it inside this class?
    def __init__(self, serial_number, pyserial_device=None, usbxpress_device=None):
        self.sn = serial_number
        if pyserial_device:
            self.t = 'pyserial'
            self.io = pyserial_device
        elif usbxpress_device:
            self.t = 'usbxpress'
            usbxpress_device.open()
            self.io = usbxpress_device
        self.set_timeout(1)
        self.set_baudrate(250000)

    @property
    def port(self):
        """Return a unique identifier for the device connection."""
        if self.t == 'pyserial':
            return self.io.port
        elif self.t == 'usbxpress':
            return self.get_serial_number()

    def get_serial_number(self):
        return self.sn

    # Mimic pyserial interface for getting/setting baudrate
    @property
    def baudrate(self):
        return self.io.baudrate

    @baudrate.setter
    def baudrate(self, baudrate: int):
        if self.t == 'pyserial':
            self.io.baudrate = baudrate
        elif self.t == 'usbxpress':
            self.io.set_baud_rate(baudrate)

    def set_baudrate(self, baudrate: int):
        self.baudrate = baudrate

    @property
    def timeout(self):
        return self.io.get_timeouts()[0]  # both timeouts are the same.

    @timeout.setter
    def timeout(self, seconds: float):
        if self.t == 'pyserial':
            self.io.timeout = seconds
        elif self.t == 'usbxpress':
            timeout_ms = round(seconds * 1000)
            self.io.set_timeouts(timeout_ms, timeout_ms)

    def set_timeout(self, timeout_s: float):
        self.timeout = timeout_s

    def write(self, data: bytes):
        self.io.write(data)

    def read_until(self, expected: bytes = b'\n', size: int = None):
        """Read a reply up to an expected sequence or size and return it.
        Mimics Pyserial
        `read_until <https://pyserial.readthedocs.io/en/latest/pyserial_api.html#serial.Serial.read_until>`_
        implementation.

        :return: the bytes read including the expected sequence.
        """
        if self.t == 'pyserial':
            return self.io.read_until(expected=expected, size=size)
        elif self.t == 'usbxpress':
            data = bytearray()
            chars_read = 0
            while True:
                c = self.io.read(1)
                data.append(c)
                chars_read += 1
                if c.endswith(expected) or (size is not None and chars_read == size):
                    break
            return bytes(data)
