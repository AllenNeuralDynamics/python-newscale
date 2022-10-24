"""Interface-agnostic classes to create manipulator cmds and interpret replies."""

import logging
from bitstring import BitArray  # for unpacking
from functools import wraps
from newscale.device_codes import StateBit, Direction, Mode, DriveMode,\
    parse_stage_reply
from newscale.device_codes import StageCmd as Cmd
from newscale.interfaces import HardwareInterface, USBInterface, \
    PoEInterface
from newscale.errors import IllegalCommandError, IllegalCommandFormatError
from serial import Serial
from time import perf_counter, sleep
from typing import Tuple

# Constants
TICKS_PER_UM = 2.0  # encoder ticks per micrometer.
TICKS_PER_MM = TICKS_PER_UM * 1000.


class M3LinearSmartStage:
    """A single axis stage on an interface."""
    #Constants
    ENC_RES_NM = 500.  # nanometers. Fixed value for speed calculations.
    INTERVAL = 1000.  # us. Fixed value for speed calculations.

    def __init__(self, interface: HardwareInterface, address: str = None):
        """Create hardware interface if unspecified or use an existing one.

        :param interface: interface object through which to communicate.
        :param address: address to communicate to the device on the specified
            interface. Optional. If unspecified, commands will be passed
            through directly without trying to select an axis first.
            
        .. code-block:: python

            from newscale.interfaces import USBInterface
            from newscale.stages import M3LinearSmartStage

            interface = USBInterface(port='COM4'),
            stage = M3LinearSmartStage(interface, "01")
        
        """
        # Either address can be passed in XOR interface
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.address = address
        self.interface = interface
        self.log.debug("Establishing host control by requesting firmware "
                       "version.")
        self.get_firmware_version()  # Necessary to handshake with the PC.
        self.set_drive_mode(DriveMode.CLOSED_LOOP)  # Prep stage for abs moves.

    @staticmethod
    def _get_cmd_str(cmd: Cmd, *args: str):
        args_str = " " + " ".join([a.upper() for a in args]) if args else ""
        return f"<{cmd.value.upper()}{args_str}>\r"

    def _parse_reply(self, reply: str):
        """Turn string reply into a Cmd plus one or more response integers."""
        reply = parse_stage_reply(reply)
        # Check for errors here.
        if len(reply) == 1:
            if reply[0] == Cmd.ILLEGAL_COMMAND:
                error_msg = "Prior command cannot be issued in this state."
                self.log.error(error_msg)
                raise IllegalCommandError(error_msg)
            elif reply[0] == Cmd.ILLEGAL_COMMAND_FORMAT:
                error_msg = "Prior command is formatted incorrectly."
                self.log.error(error_msg)
                raise IllegalCommandFormatError(error_msg)
        return reply

    def _send(self, cmd_str: str):
        """Send a command and return the parsed reply."""
        # Note: interface will handle the case where address is None.

        # Note: we must block until we get a reply from the device before
        # returning to ensure that the axis state has changed. Otherwise,
        # the device and pc are put into a race condition.

        self.interface.send(cmd_str, address=self.address)
        return self._parse_reply(self.interface.read(self.address))

    # <01>
    def get_firmware_version(self):
        """Get the firmware version.

        Note: this command is issued on startup to establish computer control.
        To release computer control, issue a <02> command.

        Note: some commands will reply with <24> (ILLEGAL_COMMAND) if host
        control is not yet established.
        """
        return self._send(self._get_cmd_str(Cmd.FIRMWARE_VERSION))[-1]

    # <02>
    def close(self):
        """Release host control."""
        return self._send(self._get_cmd_str(Cmd.RELEASE_HOST_CONTROL))

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
        duration = round(seconds*10)  # value is encoded in tenths of seconds.
        assert duration < 256, "Time input value exceeds maximum value."
        return self._send(self._get_cmd_str(Cmd.RUN, direction.value,
                                            f"{duration:04x}"))

    # <05>
    def time_step(self, direction: Direction, step_count: int = None,
                  step_interval_us: float = None,
                  step_duration_us: float = None):
        """Setup a specified number of steps to move through at a specific
        interval."""
        # Note: we cannot accept NEITHER as a direction
        # FIXME: we need get_time_interval_units to know how to convert.
        raise NotImplementedError

    # <06>
    def distance_step(self, direction: Direction, step_size_mm: float = None):
        """Take a step of size `step_size` in the specified direction.
        If no step size is specified, the previous step size will be used.

        :param direction: direction to step in.
        :param step_size_mm: the size of the step. Optional.
        """
        # TODO: warn if step size was never specified.
        step_size_ticks = round(step_size_mm*TICKS_PER_MM)  # 32 bit unsigned.
        assert step_size_ticks.bit_length() < 32, "Step size exceeds maximum."
        return self._send(self._get_cmd_str(Cmd.STEP_CLOSED_LOOP,
                                            direction.value,
                                            f"{step_size_ticks:08x}"))

    # <06> variant
    def set_distance_step_size(self, step_size_mm: float):
        """Specify the step size taken (in mm) in :meth:`distance_step`"""
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
    def set_open_loop_speed(self, percent: float):
        """Set the open loop speed as a percent (0 to 100) of the full scale
        range.

        :param percent: Speed indicated as a percentage (0.0-100.0)
        """
        speed_byte = round(percent/100 * 255)
        assert 1 < speed_byte < 256, "speed setting out of range."
        return self._send(self._get_cmd_str(Cmd.OPEN_LOOP_SPEED,
                                            f"{speed_byte:02x}"))

    # <09> variant
    def get_open_loop_speed(self):
        """Get the open loop speed.

        :return: the open loop speed as a percent (0-100) of the max speed.
        """
        speed_byte = self._send(self._get_cmd_str(Cmd.OPEN_LOOP_SPEED))[1]
        return (speed_byte/255.) * 100.

    # <10>
    def get_closed_loop_state_and_position(self):
        """Return a tuple of (state as a dict, position in mm, error in mm)."""
        # use get_state
        _, state_int, pos, error = \
            self._send(self._get_cmd_str(Cmd.CLOSED_LOOP_STATE))
        return self._parse_state(state_int), pos/TICKS_PER_MM, \
               error/TICKS_PER_MM

    # <10> variant
    def get_position(self):
        """return the position of this axis in [mm]."""
        _, _, pos, _ = self._send(self._get_cmd_str(Cmd.CLOSED_LOOP_STATE))
        return pos/TICKS_PER_MM

    @staticmethod
    def _parse_state(state: int):
        """Convert state integer (<10> reply) to dict keyed by state bit."""
        # Convert int to bool array representing bits sorted: lsbit to msbit.
        # zero-stuff input int to be 24 bits wide.
        state_bits = reversed([True if digit == '1' else False
                               for digit in f"{state:024b}"])
        # Iterate through StateBit Enum and reply to create a dict
        state = {k: v for k, v in zip(StateBit, state_bits)}
        #        if not k.name.startswith('RESERVED')}
        # Cleanup state flags that have richer meaning.
        state[StateBit.MODE] = Mode.BURST \
            if state[StateBit.MODE] else Mode.AMPLITUDE
        state[StateBit.DIRECTION] = Direction.FORWARD \
            if state[StateBit.DIRECTION] else Direction.BACKWARD
        return state

    # <19>
    def get_motor_status(self):
        """Return a dictionary, keyed by
        :obj:`~newscale.device_codes.StateBit` indicating the motor's
        status."""
        _, state_int = self._send(self._get_cmd_str(Cmd.MOTOR_STATUS))
        return self._parse_motor_flags(state_int)

    @staticmethod
    def _parse_motor_flags(state: int):
        """Convert Motor Flags integer (<19> reply) to dict keyed by state bit
        """
        # Convert int to bool array representing bits sorted: lsbit to msbit.
        # zero-stuff input int to be 16 bits wide.
        state_bits = reversed([True if digit == '1' else False
                               for digit in f"{state:016b}"])
        state_bit_subset = list(StateBit)[:16]
        state = {k: v for k, v in zip(state_bit_subset, state_bits)}
        #        if not k.name.startswith('RESERVED')}
        # Cleanup state flags that have richer meaning.
        state[StateBit.MODE] = Mode.BURST \
            if state[StateBit.MODE] else Mode.AMPLITUDE
        state[StateBit.DIRECTION] = Direction.FORWARD \
            if state[StateBit.DIRECTION] else Direction.BACKWARD
        return state

    # <20>
    def set_drive_mode(self, drive_mode: DriveMode):
        """Set open or closed-loop mode."""
        return self._send(self._get_cmd_str(Cmd.DRIVE_MODE, drive_mode.value))

    # <20> variant
    def get_drive_mode(self):
        """Return the mode currently set."""
        _, mode = self._send(self._get_cmd_str(Cmd.DRIVE_MODE,
                                               DriveMode.MODE_QUERY.value))
        return DriveMode(f"{mode:x}")

    # <40>
    def set_closed_loop_speed_and_accel(self, vel_mm_per_second: float,
                                        accel_mm_per_squared_second: float,
                                        min_vel_mm_per_second: float = 0.02):
        """Set the closed loop speed and accel in mm/sec and mm/(sec^2)
        respectively.

        :param vel_mm_per_second: speed in mm/sec.
        :param accel_mm_per_squared_second: acceleration in mm/sec^2 .
        :param min_vel_mm_per_second: minimum velocity in mm/sec. (Optional).
        """
        assert vel_mm_per_second > min_vel_mm_per_second, \
            "Error: requested velocity must be faster than the minimum" \
            f"velocity: {min_vel_mm_per_second} [m/sec]."
        um_per_second = vel_mm_per_second * 1.0e3
        um_per_squared_second = accel_mm_per_squared_second * 1.0e3
        cutoff_vel_um_per_sec = min_vel_mm_per_second * 1e3
        # Scheme for converting to register values comes from the datasheet.
        INTERVAL_COUNT = 1

        vel_counts_per_interval = \
            round((um_per_second/(self.__class__.ENC_RES_NM/1000.)) * 256
                  * (INTERVAL_COUNT*(self.__class__.INTERVAL/1.0e6)))
        cutoff_vel_counts_per_interval = \
            round(cutoff_vel_um_per_sec/(self.__class__.ENC_RES_NM/1e3) * 256
                  * (INTERVAL_COUNT * (self.__class__.INTERVAL/1e6)))
        accel_counts_per_sq_interval = \
            round(vel_counts_per_interval
                  / (um_per_second/um_per_squared_second)
                  * INTERVAL_COUNT * (self.__class__.INTERVAL/1e6))
        interval_duration_intervals = INTERVAL_COUNT

        # Check the size of values as they would appear on the register.
        assert len(bin(vel_counts_per_interval)[2:]) <= 24, \
            f"Requested velocity is too large."
        assert len(bin(cutoff_vel_counts_per_interval)[2:]) <= 24, \
            "Requested cutoff velocity is too large."
        assert len(bin(accel_counts_per_sq_interval)[2:]) <= 24,\
            "Requested acceleration is too large."
        # Note that interval duration is fixed for now.
        return self._send(
            self._get_cmd_str(Cmd.CLOSED_LOOP_SPEED,
                              f"{vel_counts_per_interval:06x}",
                              f"{cutoff_vel_counts_per_interval:06x}",
                              f"{accel_counts_per_sq_interval:06x}",
                              f"{interval_duration_intervals:04x}"))

    # <40> variant
    def get_closed_loop_speed_settings(self):
        """Get closed loop speed and acceleration settings.

        :returns: a 4 tuple of (<velocity in mm/sec>,
        <minimum velocity in mm/sec>, <acceleration in mm/sec^2>,
        <interval count>)
        """
        # Note that conversion equations come from datasheet.
        _, vel_counts_per_interval, min_vel_counts_per_interval, \
        accel_counts_per_sq_interval, interval_count = \
            self._send(self._get_cmd_str(Cmd.CLOSED_LOOP_SPEED))
        # Helper value.
        counts_per_interval_to_mm_per_sec = \
            (self.__class__.ENC_RES_NM*1.0e6) \
            / (1.0e3*256*interval_count*self.__class__.INTERVAL*1.0e3)
        #  Convert raw register values to have familiar units where possible.
        vel_mm_per_second = \
            vel_counts_per_interval * counts_per_interval_to_mm_per_sec
        min_vel_mm_per_second = \
            min_vel_counts_per_interval * counts_per_interval_to_mm_per_sec
        # accel value depends on raw velocity and accel regsiters AND
        # velocity computed in um/sec.
        accel_um_per_sq_second = \
            (vel_mm_per_second*1000*accel_counts_per_sq_interval*1e6) \
            / (vel_counts_per_interval*interval_count*self.__class__.INTERVAL)
        accel_mm_per_sq_second = accel_um_per_sq_second/1000.
        return vel_mm_per_second, min_vel_mm_per_second, \
               accel_mm_per_sq_second, interval_count

    # <46>
    def set_soft_limit_values(self, min_limit_mm, max_limit_mm):
        """Set the soft limit values in mm.

        Note: soft limits needs to be enabled for these values to have any
            effect.

        :param min_limit_mm:
        :param max_limit_mm:
        """
        min_value = min_limit_mm * 1e6 / self.__class__.ENC_RES_NM
        max_value = max_limit_mm * 1e6 / self.__class__.ENC_RES_NM
        # Check that requested values will fit in register representation.
        assert -0x80000000 < min_value < 0x7FFFFFFF, "Error, requested " \
            "minimum limit is out of range."
        assert -0x80000000 < max_value < 0x7FFFFFFF, "Error, requested " \
            "maximum limit is out of range."
        # Convert to 32-bit, 2's complement representation for negative
        # numbers. "Zero-stuff" up to 32 bits for positive numbers in the
        # outgoing string representation.
        min_value = min_value & 0xFFFFFFFF  # Force 32 bit size, two's comp.
        max_value = max_value & 0xFFFFFFFF
        return self._send(self._get_cmd_str(Cmd.SOFT_LIMIT_VALUES,
                                            f"{min_value:032x}",
                                            f"{max_value:032x}"))

    # <47> Enable/Disable soft limits.
    def set_soft_limit_state(self, soft_limits_enabled: bool):
        """Enable or disable soft limits.

        :param soft_limits_enabled: True to enable soft limits. False to
            disable.
        """
        soft_limit_state = f"{1:04x}" if soft_limits_enabled else f"{0:04x}"
        self._send(self._get_cmd_str(Cmd.SOFT_LIMIT_STATES, soft_limit_state))

    def enable_soft_limits(self):
        self.set_soft_limit_state(True)

    def disable_soft_limits(self):
        self.set_soft_limit_state(False)

    # <52>
    def get_time_interval_units(self):
        """Get the time interval units for this particular M3 stage.

        Note: M3-LS, M3-L, and M3-FS have different time interval units, but
        time interval units are the same within these "sub-families."

        :return: a 2-tuple of (<float>, <str>) where the first value is a float
            representing the interval, and the second value is a string
            representing the units. (The second value should always be "usec".)
        """
        _, unit_str = self._send(self._get_cmd_str(Cmd.TIME_INTERVAL_UNITS))
        val_str, unit_str = unit_str.split()
        return float(val_str), unit_str


# Decorators
def axis_check(*args_to_skip: str):
    """Ensure that the axis (specified as an arg or kwarg) exists."""
    def wrap(func):
        # wraps needed for sphinx to make docs for methods with this decorator.
        @wraps(func)
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
                assert arg.lower() in self.stages, \
                    f"Error. Axis '{arg.lower()}' does not exist"
            return func(self, *args, **kwargs)
        return inner
    return wrap


class MultiStage:
    """A conglomerate of many stages from many interfaces."""
    MOVE_TIMEOUT_S = 15.0

    def __init__(self, **stages: M3LinearSmartStage):
        """Init a MultiStage object from one or more stages.

        :param stages: one or more stage objects keyed by name.

        .. code-block:: python
        
            from newscale.interfaces import USBInterface
            from newscale.stages import M3LinearSmartStage, MultiStage

            interface = USBInterface(port='COM4'),
            x_stage = M3LinearSmartStage(interface, "01")
            y_stage = M3LinearSmartStage(interface, "02")

            stages = MultiStage(x=x_stage, y=y_stage)

        """
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        # Sanitize input to lowercase.
        self.stages = {k.lower(): v for k, v in stages.items()}

    @axis_check()
    def set_drive_mode(self, **axes: DriveMode):
        """Set the specified axes to the specified modes.

        :param axes: one or more axes specified by name with their drive mode
            specified as a DriveMode.

        .. code-block:: python

            stages.set_drive_mode(x=DriveMode.CLOSED_LOOP)

        """
        for axis_name, drive_mode in axes.items():
            self.stages[axis_name].set_drive_mode(drive_mode)

    def set_open_loop_mode(self):
        """Put all axes in open loop mode."""
        axes_dict = {x: DriveMode.OPEN_LOOP for x in self.stages.keys()}
        self.set_drive_mode(**axes_dict)

    def set_closed_loop_mode(self):
        """Put all axes in closed loop mode.

        Note: issuing absolute moves requires that the stage first be in
        closed loop mode.
        """
        axes_dict = {x: DriveMode.CLOSED_LOOP for x in self.stages.keys()}
        self.set_drive_mode(**axes_dict)

    @axis_check('wait')
    def move_absolute(self, wait: bool = True, **axes: float):
        """Move the specified axes by the specified amounts.

        Note: the multistage will NOT travel in a straight line to its
            destination unless accelerations and speeds are set to do so.

        :param wait: bool indicating if this function should block until the
            stage has reached its destination.
        :param axes: one or more axes specified by name with their move amount
            specified in [mm].
        """
        for axis_name, abs_position_mm in axes.items():
            self.stages[axis_name].move_to_target(abs_position_mm)
        if not wait:
            return
        # Poll position vector until we have reached the target or timeout.
        start_time = perf_counter()
        while perf_counter() - start_time < self.__class__.MOVE_TIMEOUT_S:
            stats = {x: self.stages[x].get_closed_loop_state_and_position()[0]
                     for x in axes.keys()}
            if any([stats[x][StateBit.STALLED] for x in axes.keys()]):
                raise RuntimeError("One or more axes is stalled.")
            if all([(not stats[x][StateBit.RUNNING])
                    and stats[x][StateBit.ON_TARGET]
                    for x in axes.keys()]):
                return
            sleep(0.01)
        raise RuntimeError("Axes timed out trying to reach target position.")

    @axis_check('wait')
    def move_for_time(self, wait: bool = True,
                      **axes: Tuple[Direction, Tuple[float, None]]):
        """Move axes specified for the corresponding amount of time in seconds.

        :param wait: bool indicating if this function should block until the
            stage has reached its destination.
        :param axes: a per-axis tuple of (Direction, <move_time_in_seconds>).
            the move time can be set to None, and the axis will run until
            reaching a limit or being issued a halt.
        """
        for axis_name, (direction, seconds) in axes.items():
            self.stages[axis_name].run(direction, seconds)
        if not wait:
            return
        # Poll position vector until we have reached the target or timeout.
        start_time = perf_counter()
        while perf_counter() - start_time < self.__class__.MOVE_TIMEOUT_S:
            stats = {x: self.stages[x].get_closed_loop_state_and_position()[0]
                     for x in axes.keys()}
            if any([stats[x][StateBit.STALLED] for x in axes.keys()]):
                raise RuntimeError("One or more axes is stalled.")
            if all([(not stats[x][StateBit.RUNNING])
                    and (not stats[x][StateBit.TIMED_RUN])
                    for x in axes.keys()]):
                return
            sleep(0.01)
        raise RuntimeError("One or more axes timed out trying to move for the"
                           "specified time.")

    @axis_check()
    def get_position(self, *axes: str):
        """Retrieve the specified axes positions (in mm) as a dict, or get all
        positions if none are specified.

        :param axes: an unlimited number of axes specified by name (string).

        .. code-block:: python

            stages.get_position('x', 'y', 'z')  # Get specified positions OR
            stages.get_position()  # Get all positions.

        """
        if len(axes) == 0:  # return all axes if None are specified.
            axes = self.stages.keys()
        return {x: self.stages[x].get_position() for x in axes}

    @axis_check()
    def set_speed(self, **axes):
        """Set the speeds of the specified axes in mm/sec."""
        # TODO: Units
        pass

    def get_speed(self, **axes):
        """Get the speeds of the specified axes"""
        # TODO: Units
        pass

    @axis_check()
    def halt(self):
        """Halt all axes"""
        return {x: self.stages[x].halt() for x in self.stages.keys()}

    @axis_check()
    def set_soft_limit_states(self, **axes):
        """set the state of the soft limits."""
        # FIXME: implement this.
        pass

    def close(self):
        """Release computer control of all axes."""
        return {x: self.stages[x].close() for x in self.stages.keys()}


class USBXYZStage(MultiStage):
    """An XYZ Stage from a single USB interface."""

    def __init__(self, port: str = None,
                 usb_interface: USBInterface = None):
        if not ((port is None) ^ (usb_interface is None)):
            raise SyntaxError("Exclusively either port or usb_interface"
                              "(i.e: one or the other, but not both) options "
                              "must be specified.")
        self.interface = usb_interface if usb_interface and not port \
            else USBInterface(port)
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
