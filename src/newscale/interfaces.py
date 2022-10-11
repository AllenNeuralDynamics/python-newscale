"""Set of hardware interfaces through which we can communicate with stages."""

import logging
from abc import ABC, abstractmethod


class HardwareInterface(ABC):

    def __init__(self):
        self.log = logging.getLogger(f"{__name__}.{self.__class__.name}")

    def send(self, address: str, data: str):
        """Common function signature for sending data from any interface."""
        pass

    def read(self, address: str):
        """Common function signature to read a full reply from any interface."""
        pass


class SerialInterface(HardwareInterface):

    def __init__(self, port: str = None, serial: Serial = None):
        super().__init__()
        # Use existing Serial object or create a new one.
        self.ser = Serial(port) if port and not serial else serial
        # Manage many devices sharing this resource.

    def send(self, address: str, data: str):
        # TODO: handle shared interface logic.
        #   i.e: if we'ves not seen this address previously, select the device.
        self.log.debug(f"On address: '{address}', sending: '{data}'")
        self.ser.write(data.encode('ascii'))

    def read(self, address: str):
        # TODO: handle shared interface logic.
        data = self.ser.read_until(b'\r').decode('utf8')
        self.log.debug(f"On address: '{address}', read back '{data}'")
        return data


class PoEInterface(HardwareInterface):

    BUFFER_SIZE = 1024

    def __init__(self, address: str = None, socket: Socket = None):
        super().__init__()
        # Use existing socket object or create a new one.
        self.sock = Socket(address) if address and not socket else socket

    def send(self, address: str, data: str):
        # TODO: handle shared interface logic.
        self.log.debug(f"On address: '{address}', sending: '{data}'")
        self.sock.sendall(data.encode('ascii'))
        
    def read(self, address: str):
        # TODO: handle shared interface logic.
        return self.sock.recv(self._class__.BUFFER_SIZE).decode('utf-8')


class MockInterface(HardwareInterface):
    """Interface stub for testing (but could also be mocked with mock lib)."""

    def __init__(self):
        super().__init__()

    def send(self, address: str, data: str):
        self.log.debug(f"On address: '{address}', sending: '{data}'")

    def read(self, address: str):
        self.log.debug(f"On address: '{address}', read back: ''")
