"""Interface-agnostic classes to create manipulator cmds and interpret replies."""

import logging
from bitstring import BitArray  # for unpacking
from newscale.device_codes import StateBit, Direction, parse_stage_reply
from newscale.device_codes import StageCmd as Cmd
from newscale.interfaces import HardwareInterface, SerialInterface, \
    PoEInterface
from serial import Serial

# Constants
TICKS_PER_UM = 2.0  # encoder ticks per micrometer.
TICKS_PER_MM = TICKS_PER_UM * 1000.


class M3LinearSmartStage:
    """A single axis stage on an interface."""

    def __init__(self, interface: HardwareInterface, address: str = None):
        """Create hardware interface if unspecified or use an existing one.

        :param interface: interface object through which to communicate.
        :param address: address to communicate to the device on the specified
            interface. Optional. If unspecified, commands will be passed
            through directly.
        """
        # Either address can be passed in XOR interface
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.address = address
        self.interface = interface

    @staticmethod
    def _get_cmd_str(cmd: Cmd, *args: str):
        args_str = " " + " ".join([a.upper() for a in args]) if args else ""
        return f"<{cmd.value.upper()}{args_str}>\r"

    @staticmethod
    def _parse_reply(reply: str):
        """Turn string reply into a Cmd plus one or more response integers."""
        reply = parse_stage_reply(reply)
        # Check for errors here.
        if len(reply) == 1:
            if reply[0] in [Cmd.ILLEGAL_COMMAND, Cmd.ILLEGAL_COMMAND_FORMAT]:
                error_msg = f"Device replied with: {reply[0].name}."
                raise RuntimeError(error_msg)
        return reply

    def _send(self, cmd_str: str):
        """Send a command and return the parsed reply."""
        # Note that interface will handle case where address is None.
        self.interface.send(cmd_str, address=self.address)
        return self._parse_reply(self.interface.read(self.address))

    # <01>
    def get_firmware_version(self):
        """Get the firmware version."""
        return self._send(self._get_cmd_str(Cmd.FIRMWARE_VERSION))[-1]

    # <03>
    def halt(self):
        return self._send(self._get_cmd_str(Cmd.HALT))

    # <04>
    def run(self, direction: Direction, seconds: float = None):
        """Enable motor for a specified time or without limit if unspecified.

        :param direction: forward or reverse
        :param seconds: time to run the motor in seconds (with increments of
            tenths of seconds).
        """
        assert direction is not Direction.NEITHER, \
            "Direction must be forward or reverse."
        if seconds is None:
            return self._send(self._get_cmd_str(Cmd.RUN, direction.value))
        duration = round(seconds*10) # value is encoded in tenths of seconds.
        assert duration < 256, "Time input value exceeds maximum value."
        return self._send(self._get_cmd_str(Cmd.RUN, direction.value,
                                            f"{duration:04x}"))

    # <05>
    def time_step(self, direction: Direction, step_count: int = None,
                  step_interval_us: float = None,
                  step_duration_us: float = None):
        # We cannot accept NEITHER as a direction
        pass

    # TODO: a class should warn if step size was never specified.
    # <06>
    def distance_step(self, direction: Direction, step_size_mm: float = None):
        """Take a step of size `step_size` in the specified direction.
        If no step size is specified, the previous step size will be used.
        """
        step_size_ticks = round(step_size_mm*TICKS_PER_MM)  # 32 bit unsigned.
        assert step_size_ticks.bit_length() < 32, "Step size exceeds maximum."
        return self._send(self._get_cmd_str(Cmd.STEP_CLOSED_LOOP,
                                            direction.value,
                                            f"{step_size_ticks:08x}"))

    # <06> variant
    def set_distance_step_size(self, step_size_mm: float):
        return self.distance_step(Direction.NEITHER, step_size_mm)

    # <07>
    # Skip this one.

    # <08>
    def move_to_target(self, setpoint_mm: float = None):
        """Move to the target absolute setpoint specified in mm.
        :param setpoint_mm:  positive or negative setpoint.
        """
        # TODO: convert target setpoint to encoder ticks.
        if setpoint_mm is None:
            return self._get_cmd_str(Cmd.MOVE_TO_TARGET)
        step_size_ticks = round(setpoint_mm*TICKS_PER_MM)
        assert step_size_ticks.bit_length() < 32, "Step size exceeds maximum."
        return self._send(self._get_cmd_str(Cmd.MOVE_TO_TARGET,
                                            f"{step_size_ticks:08x}"))

    # <09>
    def set_open_loop_speed(self, percentage: float):
        """Set the open loop speed as a percent (0 to 100) of the full scale
        range."""
        speed_byte = round(percentage/100 * 255)
        assert 1 < speed_byte < 256, "speed setting out of range."
        return self._send(self._get_cmd_str(Cmd.OPEN_LOOP_SPEED,
                                            f"{speed_byte:02x}"))

    # <10>
    def get_closed_loop_state_and_position(self):
        """Return a tuple of (state as a dict, position in mm, error in mm)."""
        # use get_state
        _, state_int, pos, error = \
            self._send(self._get_cmd_str(Cmd.CLOSED_LOOP_STATE))
        return self._parse_state(state_int), pos/TICKS_PER_MM, \
               error/TICKS_PER_MM

    @staticmethod
    def _parse_state(state: int):
        """Convert state integer (<10> reply) to dict keyed by state bit."""
        # Convert int to array of bits
        state_bits = [True if digit == '1' else False
                      for digit in bin(state)[2:]]
        # Iterate through StateBit Enum and reply to create a dict
        return {k: v for k, v in zip(StateBit, state_bits)
                if not k.name.startswith('RESERVED')}

    # <19>
    def get_motor_status(self):
        _, state_int = self._send(self._get_cmd_str(Cmd.MOTOR_STATUS))
        return self._parse_motor_flags(state_int)

    @staticmethod
    def _parse_motor_flags(state: int):
        """Convert Motor Flags integer (<19> reply) to dict keyed by state bit
        """
        state_bits = [True if digit == '1' else False
                      for digit in bin(state)[2:]]
        state_bit_subset = list(StateBit)[:16]
        return {k: v for k, v in zip(state_bit_subset, state_bits)
                if not k.name.startswith('RESERVED')}

    # <40>
    def set_closed_loop_speed_and_accel(self, um_per_second: float,
                                        um_per_squared_second: float):
        """Set the closed loop speed in micrometers per second.
        Minimum
        """

        # Scheme for converting to register values comes from the datasheet.
        ENC_RES = 500  # nm
        INTERVAL = 1000  # us
        INTERVAL_COUNT = 1
        cutoff_velocity = 20  # um/s
        vel_counts_per_interval = \
            round((um_per_second/(ENC_RES/1e3)) * 256
                  * (INTERVAL_COUNT*(INTERVAL/1e6)))
        cutoff_vel_counts_per_interval = \
            round(cutoff_velocity/(enc_res/1e3) * 256
                  * (INTERVAL_COUNT * (INTERVAL/1e6)))
        accel_counts_per_sq_interval = \
            round(vel_counts_per_interval
                  / (um_per_second/um_per_squared_second)
                  * INTERVAL_COUNT * (INTERVAL/1e6))
        interval_duration_intervals = 1

        return self._send(self._get_cmd_str(Cmd.OPEN_LOOP_SPEED,
                                            f"{vel_counts_per_interval:06x}",
                                            f"{cutoff_vel_counts_per_interval:06x}",
                                            f"{accel_counts_per_sq_interval:06x}",
                                            f"{interval_duration_intervals:04x}"))

    # <40> variant
    def get_closed_loop_speed_settings(self):
        # TODO: actually turn these numbers back into something sensible.
        # Note that some bits in these numbers represent fractions.
        return self._send(self._get_cmd_str(Cmd.OPEN_LOOP_SPEED))

    # <46>
    def set_soft_limit_values(self, min_value, max_value):
        # FIXME
        return self._get_cmd_str(Cmd.SOFT_LIMIT_VALUES, min_value, max_value)


# Decorators
def axis_check(*args_to_skip: str):
    """Ensure that the axis (specified as an arg or kwarg) exists."""
    def wrap(func):
        def inner(self, *args, **kwargs):
            # Sanitize input to all-lowercase.
            args = [a.lower() for a in args]
            kwargs = {k.lower(): v for k, v in kwargs.items()}
            # Combine args and kwarg names; skip double-adding params specified as
            # one or the other.
            iterable = [a for a in args if a not in kwargs] + list(kwargs.keys())
            for arg in iterable:
                # Skip pre-specified args.
                if arg in args_to_skip:
                    continue
                assert arg.lower() not in self.stages, \
                    f"Error. Axis '{arg.upper()}' does not exist"
            return func(self, *args, **kwargs)
        return inner
    return wrap


class MultiStage:
    """A conglomerate of many stages from many interfaces."""

    def __init__(self, **stages: M3LinearSmartStage):
        self.log = logging.getLogger(f"{__name__}.{self.__classs__.__name__}")
        # Sanitize input to lowercase.
        self.stages = {k.lower(): v for k, v in stages.items()}

    @axis_check('wait')
    def move_absolute(self, wait: bool = True, **axes: float):
        """Move the specified axes by the specified amounts.

        Note: the multistage will NOT travel in a straight line to its
            destination unless accelerations and speeds are set to do so.
        """
        # Kick off movements.
        # TODO: consider a timeout
        pass

    @axis_check('wait')
    def move_relative(self, wait: bool = True, **axes):
        pass

    @axis_check('wait')
    def move_for_time(self, wait: bool = True, **axes: float):
        """Move axes specified for the corresponding amount of time in seconds.

        :param sequential: If true, move the axes one at time. Otherwise, kick
            off each move as close to simultaneously as possible.
        :param wait: bool indicating if this function should block until the
            stage has reached its destination.
        :param axes: the axis and its corresponding time to move.
        """
        pass

    @axis_check
    def get_position(self, *axes):
        """Retrieve the specified axes positions as a dict, or get all
        positions if none are specified.

        ..code_block::
            get_position('x', 'y', 'z')  # Get specified positions OR
            get_position()  # Get all positions.
        """
        if len(axes) == 0:  # return all axes if None are specified.
            axes = self.stages.keys()
        return {k: self.stages[k].get_position() for k in axes}

    @axis_check
    def set_speed(self, **axes):
        """Set the speed of the specified axes in ."""
        pass

    @axis_check
    def halt(self, axis):
        pass


class USBXYZStage(MultiStage):
    """An XYZ Stage from a single USB interface."""

    def __init__(self, port: str = None,
                 serial_interface: SerialInterface = None):
        if not ((port is None) ^ (serial_interface is None)):
            raise SyntaxError("Exclusively either port or serial_interface"
                              "(i.e: one or the other, but not both) options "
                              "must be specified.")
        self.interface = serial_interface if serial_interface and not port \
            else SerialInterface(port)
        # Create 3 stages with corresponding addresses.
        stages = {'x': M3LinearSmartStage(self.interface, '01'),
                  'y': M3LinearSmartStage(self.interface, '02'),
                  'z': M3LinearSmartStage(self.interface, '03')}
        super().__init__(**stages)


class PoEXYZStage(MultiStage):
    """An XYZ Stage from a single Power-over-Ethernet interface."""

    def __init__(self, address: str = None,
                 socket_interface: PoEInterface = None):
        if not ((address is None) ^ (socket_interface is None)):
            raise SyntaxError("Exclusively either address or socket_interface"
                              "(i.e: one or the other, but not both) options "
                              "must be specified.")
        self.interface = socket_interface if socket_interface and not address \
            else PoEInterface(address)
        # Create 3 stages.
        stages = {'x': M3LinearSmartStage(self.interface, '01'),
                  'y': M3LinearSmartStage(self.interface, '02'),
                  'z': M3LinearSmartStage(self.interface, '03')}
        super().__init__(**stages)
