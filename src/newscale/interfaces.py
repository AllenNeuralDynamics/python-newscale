"""Set of hardware interfaces through which we can communicate with stages."""

import logging
from socket import AF_INET, SOCK_STREAM, socket
from sys import platform as PLATFORM

from serial.tools.list_ports import comports as list_comports
from serial import Serial

if PLATFORM == 'win32':
    from .usbxpress import USBXpressLib, USBXpressDevice

from newscale.device_codes import TRANSCEIVER_PREFIX, BaudRateCode
from newscale.device_codes import TransceiverCmd as Cmd
from newscale.device_codes import parse_tr_reply

VID_NEWSCALE = 0x10c4
PID_NEWSCALE = 0xea61

class HardwareInterface:

    def __init__(self, name: str = None):
        # Create an instance-level logger if specified.
        log_extension = f".{name}" if name is not None else ""
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}"
                                     f"{log_extension}")
        # Manage many devices sharing this resource.
        self.last_address = None
        # Handshake with the interface.
        # TODO: Consider writing a _get_cmd_str instead of formatting here.
        msg = f"{TRANSCEIVER_PREFIX}<{Cmd.FIRMWARE_VERSION}>\r"
        self.log.debug("Handshaking with hardware interface.")
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


class NewScaleSerial():

    """
    Cross-platform abstraction layer for New Scale USB Serial devices
    Usage:
        instances = NewScaleSerial.get_instances()
        -> [newScaleSerial1, newScaleSerial2]
        for instance in instances:
            print('serial number = ', instance.get_serial_number())
    """

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

    @classmethod
    def get_instances(cls):
        instances = []
        if PLATFORM == 'linux':
            for comport in list_comports():
                if (comport.vid == VID_NEWSCALE):
                    if (comport.pid == PID_NEWSCALE):
                        hwid = comport.hwid
                        serial_number = hwid.split()[2].split('=')[1]
                        instances.append(cls(serial_number,
                                        pyserial_device=Serial(comport.device)))    # does this work?
        elif PLATFORM== 'win32':
            n = USBXpressLib().get_num_devices()
            for i in range(n):
                device = USBXpressDevice(i)
                if (int(device.get_vid(), 16) == VID_NEWSCALE):
                    if (int(device.get_pid(), 16) == PID_NEWSCALE):
                        serial_number = device.get_serial_number()
                        instances.append(cls(serial_number, usbxpress_device=device))   # does this work?
        return instances

    def get_port_name(self):
        if self.t == 'pyserial':
            return self.io.port
        elif self.t == 'usbxpress':
            return 'USBXpress Device'

    def get_serial_number(self):
        return self.sn

    def set_baudrate(self, baudrate):
        if self.t == 'pyserial':
            self.io.baudrate = baudrate
        elif self.t == 'usbxpress':
            self.io.set_baud_rate(baudrate)

    def set_timeout(self, timeout):
        if self.t == 'pyserial':
            self.io.timeout = timeout
        elif self.t == 'usbxpress':
            timeout_ms = int(timeout*1000)
            self.io.set_timeouts(timeout_ms, timeout_ms)

    def write(self, data):
        self.io.write(data)

    def readLine(self):
        if self.t == 'pyserial':
            data = self.io.read_until(b'\r').decode('utf8')
        elif self.t == 'usbxpress':
            data = ''
            while True:
                c = self.io.read(1).decode()
                data += c
                if (c == '\r'): break
        return data


class USBInterface(HardwareInterface):
    """Generic USB-to-Serial interface, which may be a direct link to one stage
    or a hub to many. If an address is specified when sending, then the device
    acts as a hub and selects that device first.
    """

    def __init__(self, serial: NewScaleSerial):
        """Init; create a USBInterface object from an existing NewScaleSerial
            instance.

        :param serial: existing NewScaleSerial object

        .. code-block:: python

            serial = NewScaleSerial.get_instances()[0]
            interface = USBInterface(serial)

        """
        self.serial = serial
        # Handshake with the Interface hardware.
        super().__init__(self.serial.get_port_name())

    def send(self, msg: str, address: str = None):
        """Send a message to a specific device.

        :param msg: the string to be sent
        :param address: Address of the stage to communicate with. Optional.
            If specified, the interface will issue additional commands to
            select the device first. If unspecified, the command will be sent
            as-is. (This is useful to send raw commands to talk to the
            interface directly.)
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
        self.serial.write(out_msg)

    def read(self, address: str = None):
        """Read a reply (up to the ``'\\r'`` character) and return it.

        :param address: the device address to read from. For this interface
            this parameter is only for ensuring that we read from the same
            value immediately after writing to it such that we collect the
            correct response.
        """
        data = self.serial.readLine()
        # Warn if the data is supposed to go to a different stage.
        if address is not None:
            if self.last_address != address:
                self.log.warning("Requesting to read the reply from a stage "
                                 f"at address {address}, which is different "
                                 f"from the last stage at address "
                                 f"{self.last_address} that we issued a "
                                 "command to.")
        address_msg = f"On address: '{address}', r" if address else "R"
        self.log.debug(f"{address_msg}ead back {repr(data)}")
        return data


class M3USBInterface(USBInterface):
    """A Newscale M3-style USB-to-Serial interface, which supports additional
    commands beyond the generic USB-to-Serial interface."""

    def set_baud_rate(self, baud_rate: int):
        """Set the transceiver baud rate from the options available.

        `Warning`: Newscale's Pathway Software expects a transceiver baud rate
        of 250000.

        :param: the baud rate to set as an integer.
        """
        assert baud_rate in BaudRateCode, \
            "Requested input baud rate is invalid."
        baud_rate_code = BaudRateCode[baud_rate]
        msg = f"{TRANSCEIVER_PREFIX}<{Cmd.BAUD_RATE} 1 {baud_rate_code}>\r"
        self.send(msg)
        self.read()  # Discard the reply.

    def get_baud_rate(self):
        """get the Transceiver's communication baud rate.

        :return: the stage's baud rate as an integer
        """
        msg = f"{TRANSCEIVER_PREFIX}<{Cmd.BAUD_RATE} 1>\r"
        self.send(msg)
        _, _, br_code = parse_tr_reply(self.read())
        return BaudRateCode.inverse[f"{br_code:02x}"]


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
        data = self.sock.recv(self.__class__.BUFFER_SIZE).decode('utf-8')
        address_msg = f"On address: '{address}', r" if address else "R"
        self.log.debug(f"{address_msg}ead back {repr(data)}")
        return data
