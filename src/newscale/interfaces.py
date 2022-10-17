"""Set of hardware interfaces through which we can communicate with stages."""

import logging
from abc import ABC, abstractmethod
from newscale.device_codes import TransceiverCmd as Cmd
from newscale.device_codes import TRANSCEIVER_PREFIX, parse_tr_reply
from serial import Serial
from socket import socket, AF_INET, SOCK_STREAM


class HardwareInterface:

    def __init__(self, name: str = None):
        # Create an instance-level logger if specified.
        log_extension = f".{name}" if name is not None else ""
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}"
                                     f"{log_extension}")
        # Handshake with the interface.
        # TODO: Consider writing a _get_cmd_str instead of formatting here.
        msg = f"{TRANSCEIVER_PREFIX}<{Cmd.FIRMWARE_VERSION}>\r"
        self.log.debug("Handshanking with hardware interface.")
        self.send(msg)
        _, _, firmware = parse_tr_reply(self.read())
        self.log.debug(f"Transceiver firmware: {firmware}")

    def _select_stage(self, address: str):
        """Select the stage from the hub or skip if it is already connected."""
        # Select the current stage we're talking to before issuing commands.
        #   i.e: if we've not communicated with this address last, select it.
        self.log.debug(f"Selecting stage at address: {address}")
        self.last_address = address
        # TODO: Consider writing a _get_cmd_str instead of formatting here.
        msg = f"{TRANSCEIVER_PREFIX}<{Cmd.STAGE_SELECT} {address}>\r"
        self.send(msg)
        cmd, stage_address, device_present = parse_tr_reply(self.read())
        if not (device_present == 1):
            raise RuntimeError(f"Device at address {address} is not "
                               "present on this interface.")

    def send(self, msg: str, address: str = None):
        """Common function signature to send data to a stage from an interface,
        or to an interface directly.
        """
        raise NotImplementedError("To be implemented by the child class.")

    def read(self, address: str = None):
        """Common function signature to read a full reply from an interface,
        or from an interface directly.
        """
        raise NotImplementedError("To be implemented by the child class.")


class SerialInterface(HardwareInterface):
    """USB-to-Serial interface, which may be a direct link to one stage or a
    hub to many. If an address is specified when sending, then the device
    acts as a hub and selects that device first.
    """

    def __init__(self, port: str = None, baud_rate: int = 250000,
                 serial: Serial = None):
        """Init; create a Serial object from port or use an existing one.

        :param port: serial port on which to create the Serial object. If
            unspecified, `serial` will be used instead.
        :param baud_rate: baud rate to create the serial port. Ignored if a
            `serial` object is specified.
        :param serial: existing serial object. If unspecified, a Serial object
            will be creatd from the port.

        ..code_block::
            interface = SerialInterface('COM4')  # OR
            interface = SerialInterface('COM4', 115200)  # OR

            from serial import Serial
            ser = Serial('COM4', baudrate=250000)
            interface = SerialInterface(serial=ser)
        """
        name = port if port is not None \
            else serial.port if serial is not None else None
        # Use existing Serial object or create a new one.
        self.ser = Serial(port, baudrate=baud_rate, timeout=0.5) \
            if port and not serial else serial
        # Manage many devices sharing this resource.
        self.last_address = None
        # Handshake with the Interface hardware.
        super().__init__(name)

    def send(self, msg: str, address: str = None):
        """Send a message to a specific device.

        :param msg: the string to be sent
        :param address: Address of the stage to communicate with. Optional.
            If specified, the interface will issue additional commands to
            select the device first. If unspecified, the command will be sent
            as-is. (This is useful to talk to the interface directly.)
        """
        if address is not None:
            if self.last_address != address:
                self._select_stage(address)
        # Detect Transceiver-only command and re-encode it. Otherwise, pass
        # the message through.
        # Note: this implementation does NOT handle "command prefixes" if any
        # exist. (See Newscale_PathwaySoftwareManual.pdf pg73 for more info.)
        tr_msg = None
        if msg.startswith("TR"):
            tr_msg = bytearray(msg.lstrip('TR').encode('ascii'))
            for i in range(len(tr_msg)):
                tr_msg[i] |= 0x80
        # Create a situation-specific debug message.
        address_msg = f"On address: '{address}', s" if address else "S"
        tr_encoding = f" encoded as {repr(tr_msg)}" if tr_msg else ""
        debug_msg = f"{address_msg}ending: {repr(msg)}{tr_encoding}"
        self.log.debug(debug_msg)
        out_msg = tr_msg if tr_msg is not None else msg.encode('ascii')
        self.ser.write(out_msg)

    def read(self, address: str = None):
        if address is not None:
            if self.last_address != address:
                self._select_stage(address)
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
    PORT = 23

    def __init__(self, address: str, sock: socket = None):
        name = address if socket is not None \
            else sock.getpeername()[0] if sock is not None else None
        # Use existing socket object or create a new one.
        self.sock = socket(AF_INET, SOCK_STREAM) \
            if address and not sock else sock
        self.sock.connect((address, self.__class__.PORT))
        super().__init__(name)
        # Handshake with the interface hardware.

    def send(self, msg: str, address: str = None):
        if address is not None:
            if self.last_address != address:
                self._select_stage(address)
        # Note: this implementation does NOT handle "command prefixes" if any
        # exist. (See Newscale_PathwaySoftwareManual.pdf pg73 for more info.)
        # Create a situation-specific debug message.
        address_msg = f"On address: '{address}', s" if address else "S"
        debug_msg = f"{address_msg}ending: {repr(msg)}"
        self.log.debug(debug_msg)
        self.sock.sendall(msg.encode('ascii'))
        
    def read(self, address: str = None):
        if address is not None:
            if self.last_address != address:
                self._select_stage(address)
        data = self.sock.recv(self._class__.BUFFER_SIZE).decode('utf-8')
        address_msg = f"On address: '{address}', r" if address else "R"
        self.log.debug(f"{address_msg}ead back {repr(data)}")
        return data


class MockInterface(HardwareInterface):
    """Interface stub for testing (but could also be mocked with mock lib)."""

    def __init__(self):
        super().__init__()
        self._last_cmd = None  # Save cmd so we can issue an appropriate reply.

    def send(self, data: str, address: str = None):
        address_msg = f"On address: '{address}', s" if address else "S"
        self.log.debug(fr"{address_msg}ending: {repr(data)}")
        self._last_cmd = data.strip("<>\r").split(" ")[0]

    def read(self, address: str = None):
        address_msg = f"On address: '{address}', r" if address else "R"
        self.log.debug(fr"{address_msg}ead back '<{self._last_cmd}>\r'")
        return self._last_cmd
