"""Set of hardware interfaces through which we can communicate with stages."""

import logging
from abc import ABC, abstractmethod
from serial import Serial
from socket import socket


class HardwareInterface(ABC):

    def __init__(self):
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def send(self, data: str, address: str = None):
        """Common function signature for sending data from any interface.
        Address may be optional if the interface is not a hub.
        """
        pass

    def read(self, address: str = None):
        """Common function signature to read a full reply from any interface.
        Address may be optional if the interface is not a hub.
        """
        pass


class SerialInterface(HardwareInterface):
    """USB-to-Serial interface, which may be a direct link to one stage or a
    hub to many. If an address is specified when sending, then the device
    acts as a hub and selects that device first.
    """

    def __init__(self, port: str = None, serial: Serial = None):
        super().__init__()
        # Use existing Serial object or create a new one.
        self.ser = Serial(port) if port and not serial else serial
        # Manage many devices sharing this resource.

    def send(self, data: str, address: str = None):
        address_msg = f"On address: '{address}', s" if address else "S"
        self.log.debug(f"{address_msg}ending: {repr(data)}")
        # Handle shared interface (i.e: hub) logic.
        # TODO: handle shared interface logic.
        #   i.e: if we'ves not seen this address previously, select the device.
        self.ser.write(data.encode('ascii'))

    def read(self, address: str = None):
        # TODO: handle shared interface logic.
        data = self.ser.read_until(b'\r').decode('utf8')
        address_msg = f"On address: '{address}', r" if address else "R"
        self.log.debug(f"{address_msg}ead back {repr(data)}")
        return data


class PoEInterface(HardwareInterface):
    """PoE-to-Serial interface, which may be a direct link to one stage or a
    hub to many. If an address is specified when sending, then the device
    acts as a hub and selects that device first.
    """

    BUFFER_SIZE = 1024

    def __init__(self, address: str = None, sock: socket = None):
        super().__init__()
        # Use existing socket object or create a new one.
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM) \
            if address and not sock else sock
        self.sock.connect(address)

    def send(self, data: str, address: str = None):
        address_msg = f"On address: '{address}', s" if address else "S"
        self.log.debug(f"{address_msg}ending: {repr(data)}")
        self.sock.sendall(data.encode('ascii'))
        
    def read(self, address: str = None):
        address_msg = f"On address: '{address}', r" if address else "R"
        self.log.debug(f"{address_msg}ead back {repr(data)}")
        return self.sock.recv(self._class__.BUFFER_SIZE).decode('utf-8')


class MockInterface(HardwareInterface):
    """Interface stub for testing (but could also be mocked with mock lib)."""

    def __init__(self):
        super().__init__()
        self._last_cmd = None

    def send(self, data: str, address: str = None):
        address_msg = f"On address: '{address}', s" if address else "S"
        self.log.debug(fr"{address_msg}ending: {repr(data)}")
        self._last_cmd = data.strip("<>\r").split(" ")[0]

    def read(self, address: str = None):
        address_msg = f"On address: '{address}', r" if address else "R"
        self.log.debug(fr"{address_msg}ead back '<{self._last_cmd}>\r'")
        return self._last_cmd
