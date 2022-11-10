"""Interface-agnostic classes to create manipulator cmds and interpret replies."""

import logging

from newscale.device_codes import BaudRateCode, Direction, DriveMode, Mode
from newscale.device_codes import StageCmd as Cmd
from newscale.device_codes import StateBit, parse_stage_reply
from newscale.errors import IllegalCommandError, IllegalCommandFormatError
from newscale.interfaces import HardwareInterface

# Constants
TICKS_PER_UM = 2.0  # encoder ticks per micrometer.
TICKS_PER_MM = TICKS_PER_UM * 1000.


class M3LinearSmartStage:
    """A single axis stage connected to the specified interface."""

    # Constants
    ENC_RES_NM = 500.  # nanometers. Fixed value for speed calculations.
    INTERVAL = 1000.  # us. Fixed value for speed calculations.

    def __init__(self, interface: HardwareInterface, address: str = None):
        """Connect to a stage through a hardware interface.
        Establish computer control and put the stage in closed loop drive mode.
        Create hardware interface if unspecified or use an existing one.

        :param interface: interface object through which to communicate.
        :param address: address to communicate to the device on the specified
            interface. Optional. If unspecified, commands will be passed
            through directly without trying to select an axis first.

        .. code-block:: python

            from newscale.interfaces import USBInterface
            from newscale.stage import M3LinearSmartStage

            interface = USBInterface(port='COM4'),
            stage = M3LinearSmartStage(interface, "01")

        """
        # Either address can be passed in XOR interface
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.address = address
        self.interface = interface
        self.log.debug("Establishing host control by requesting firmware "
                       "version.")
        # Note: some commands will reply with <24> (ILLEGAL_COMMAND) if host
        # control is not yet established.
        self.get_firmware_version()  # Necessary to handshake with the PC.
        self.set_drive_mode(DriveMode.CLOSED_LOOP)  # Prep stage for abs moves.
        # Attributes.
        self.time_interval_us = None
        self.step_size_specified = False
        self.last_direction = Direction.NEITHER

    @staticmethod
    def _get_cmd_str(cmd: Cmd, *args: str):
        """Convert cmd + a sequence of input string args into the device
        representation.

        :param args: zero or more strings to append to the sequence. Both args
            ``None`` and empty string will be ignored.
        """
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

        Note: this command is issued on startup, which has the effect of
        establishing computer control. To release computer control, issue a
        :meth:`close` or create the object inside a ``with`` statement.

        :return: the firmware version encoded as a string.
        """
        return self._send(self._get_cmd_str(Cmd.FIRMWARE_VERSION))[-1]

    # <02>
    def close(self):
        """Release host control."""
        self._send(self._get_cmd_str(Cmd.RELEASE_HOST_CONTROL))

    # <03>
    def halt(self):
        self._send(self._get_cmd_str(Cmd.HALT))

    # <04>
    def run(self, direction: Direction, seconds: float = None):
        """Enable motor for a specified time or without limit if unspecified.
        Speed/accel settings depend on what drive mode the stage is set to,
        which can be changed with :meth:`set_drive_mode`.

        :param direction: which direction to run:
            :attr:`~newscale.device_codes.Direction.FORWARD` or
            :attr:`~newscale.device_codes.Direction.REVERSE` only.
        :param seconds: time to run the motor in seconds (with increments of
            tenths of seconds).
        """
        assert direction is not Direction.NEITHER, \
            "Direction must be forward or reverse."
        if seconds is None:
            self._send(self._get_cmd_str(Cmd.RUN, direction.value))
            return
        duration = round(seconds*10)  # value is encoded in tenths of seconds.
        assert duration <= 0xFF, "Run duration exceeds maximum value."
        self._send(self._get_cmd_str(Cmd.RUN, direction.value,
                                     f"{duration:04x}"))

    # <05>
    def multi_time_step(self, direction: Direction,
                        step_count: int = None,
                        step_interval_us: float = None,
                        step_duration_us: float = None):
        """Do a specified number of open-loop steps of specific length with a
        specific step period.

        :param direction: which direction to step.
            :obj:`~newscale.device_codes.Direction.FORWARD` or
            :obj:`~newscale.device_codes.Direction.REVERSE` only.
        :param step_count: how many steps to take
        :param step_interval_us: time between the start of each step
            in [us].
        :param step_duration_us: how long to step for in [us].
        """
        # We cannot accept NEITHER as a direction.
        assert direction != Direction.NEITHER, "Requested open-loop step " \
            f"direction cannot be {Direction.NEITHER}."
        assert step_count > 0, "Requested step count cannot be negative."
        # Check that either all or none of the optional args were specified.
        optional_args = [step_count, step_interval_us, step_duration_us]
        assert optional_args == 3*[None] or \
            all(v is not None for v in optional_args), "Optional args " \
            "must be either all present or all absent"
        assert step_duration_us < step_interval_us, "The requested duration " \
            "of each step must be shorter than the interval between steps."
        # Check size limits.
        step_interval = step_interval_us / self.get_time_interval_units()
        step_duration = step_duration_us / self.get_time_interval_units()
        if optional_args != 3*[None]:
            assert step_count <= 0xFFFF, "Requested step count exceeds limit."
            assert step_interval <= 0xFFFF,\
                "Requested step interval exceeds limit."
            assert step_duration <= 0xFFFF,\
                "Requested step duration exceeds limit"
        # Create the strings.
        step_count_str = f"{step_count:04x}" if step_count is not None else ""
        step_interval = step_interval_us \
            if step_interval_us is not None else ""
        step_duration = step_duration_us \
            if step_duration_us is not None else ""
        self._send(self._get_cmd_str(Cmd.STEP_OPEN_LOOP, direction.value,
                                     step_count_str,
                                     step_interval, step_duration))

    # <06>
    def _distance_step(self, direction: Direction = Direction.NEITHER,
                       step_size_um: float = None):
        """Take a step of size ``step_size`` in the specified direction.
        If no step size is specified, the previous step size will be used.
        If :attr:`~newscale.device_codes.Direction.NEITHER` is specified
        as the ``direction``, then ``step_size_um`` is not optional and will
        save the step size.

        :param direction: direction to step in.
            :attr:`~newscale.device_codes.Direction.NEITHER` is also
            acceptable, in which case the step size will be saved. Note that
            ``step_size`` is not optional in this case.
        :param step_size_um: the size of the step. Optional if a direction is
            specified.
        """
        if direction == Direction.NEITHER and step_size_um is None:
            raise ValueError("Step size must be specified if direction is "
                             "unspecified")
        # Step by the previously-specified amount.
        if step_size_um is None:
            if not self.step_size_specified:
                # The stage's default step size is technically undefined, but
                # let the user do it anyway.
                self.log.warning("Distance step step size was never specified.")
            self._send(self._get_cmd_str(Cmd.STEP_CLOSED_LOOP, direction.value))
            return
        # Save whether we have ever specified a step size before.
        self.step_size_specified = True
        # Limit checks.
        step_size_ticks = round(step_size_um*TICKS_PER_UM)  # 32 bit unsigned.
        assert step_size_ticks.bit_length() < 32, "Step size exceeds maximum."
        # Step by a specified amount.
        self._send(self._get_cmd_str(Cmd.STEP_CLOSED_LOOP, direction.value,
                                     f"{step_size_ticks:08x}"))

    # <06> variant
    def distance_step(self, step_size_um: float = None):
        """Take a step of size ``step_size_um`` forward
        (if ``step_size_um`` >= 0) or backward (if ``step_size_um`` < 0).
        If no step size is specified, the previous step size will be used.

        :param step_size_um: the step size in [um]. Postive values are
            interpretted as forward; negative values are interpretted as
            backward.

        .. code-block:: python

            stage.distance_step(10.0)  # step forward 10 [um].
            stage.distance_step(-10.0)  # step backward 10 [um].
            stage.distance_step()  # step backward 10 [um] again.
            stage.distance_step()  # step backward 10 [um] again.

        """
        direction = self.last_direction
        if step_size_um is None:  # Step using previous step size.
            self._distance_step(direction)
        else:  # Step with the specified step size.
            direction = Direction.FORWARD if step_size_um >= 0 else Direction.BACKWARD
            self.last_direction = direction
            self._distance_step(direction, abs(step_size_um))

    # <06> variant
    def set_distance_step_size(self, step_size_um: float):
        """Specify the step size taken (in um) in :meth:`distance_step` without
        stepping.

        :param step_size_um: the step size in [um]. Postive values are
            interpretted as forward; negative values are interpretted as
            backward.
        """
        self.last_direction = Direction.FORWARD if step_size_um >= 0 \
            else Direction.BACKWARD
        self._distance_step(Direction.NEITHER, abs(step_size_um))

    # <07>
    def clear_encoder_count(self):
        """Clear the encoder count, which sets the current position to 0."""
        self._send(self._get_cmd_str(Cmd.CLEAR_ENCODER_COUNT))

    # <08>
    def move_to_target(self, setpoint_um: float):
        """Move to the target absolute setpoint specified in um.
        The stage's drive mode must first be set to closed loop mode first via
        :meth:`set_drive_mode`.

        Note: On instantiation, the stage is put in
        :attr:`~newscale.device_codes.DriveMode.CLOSED_LOOP` mode.

        :param setpoint_um:  positive or negative setpoint.
        """
        setpoint_ticks = round(setpoint_um*TICKS_PER_UM)
        # Check that requested values will fit in register representation.
        # Note: We can't use bit_length() for signed numbers.
        assert -0x80000000 <= setpoint_ticks <= 0x7FFFFFFF, \
            "Error, requested maximum limit is out of range."
        # Convert to 32-bit, 2's complement representation for signed
        # numbers. i.e: mask with the expected size type and
        # "Zero-stuff" up to 32 bits for positive numbers in the
        # outgoing string representation.
        setpoint_ticks = setpoint_ticks & 0xFFFFFFFF
        self._send(self._get_cmd_str(Cmd.MOVE_TO_TARGET,
                                     f"{setpoint_ticks:08x}"))

    # <08> variant
    def get_target_position(self):
        """get the current closed loop target position.

        :return: target position in [um]
        """
        return self._send(self._get_cmd_str(Cmd.MOVE_TO_TARGET))[1]\
               / TICKS_PER_UM

    # <09>
    def set_open_loop_speed(self, percent: float):
        """Set the open loop speed as a percent (0 to 100) of the full scale
        range.

        :param percent: Speed indicated as a percentage (0.0-100.0)
        """
        speed_byte = round(percent/100 * 255)
        assert 1 < speed_byte < 256, "speed setting out of range."
        self._send(self._get_cmd_str(Cmd.OPEN_LOOP_SPEED,
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
        """Return a 3-tuple of (state as a dict, position in um, error in um).

        :return: a 3-tuple of
            ``(<state in dict>, <position in [um]>, <position error in [um]>)``
        """
        # use get_state
        _, state_int, pos, error = \
            self._send(self._get_cmd_str(Cmd.CLOSED_LOOP_STATE))
        return self._parse_state(state_int), pos/TICKS_PER_UM, \
               error/TICKS_PER_UM

    # <10> variant
    def get_position(self):
        """
        :return: the position of this stage in [um].
        """
        _, _, pos, _ = self._send(self._get_cmd_str(Cmd.CLOSED_LOOP_STATE))
        return pos/TICKS_PER_UM

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
        """
        :return: a dict, keyed by
            :obj:`~newscale.device_codes.StateBit`, indicating the motor's
            status.
        """
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
        """Set open or closed-loop mode.

        :param drive_mode: drive mode specified as
            :attr:`~newscale.device_codes.DriveMode.OPEN_LOOP` or
            :attr:`~newscale.device_codes.DriveMode.CLOSED_LOOP`.

        .. code-block:: python

            from newscale.device_codes import DriveMode

            stage.set_drive_mode(DriveMode.CLOSED_LOOP)

        """
        self._send(self._get_cmd_str(Cmd.DRIVE_MODE, drive_mode.value))

    # <20> variant
    def get_drive_mode(self):
        """Return the mode currently set.

        :return: a :obj:`~newscale.device_codes.DriveMode` enum
        """
        _, mode = self._send(self._get_cmd_str(Cmd.DRIVE_MODE,
                                               DriveMode.MODE_QUERY.value))
        return DriveMode(f"{mode:x}")

    # <40>
    def set_closed_loop_speed_and_accel(self, vel_um_per_second: float,
                                        accel_um_per_sq_second: float,
                                        min_vel_um_per_second: float = 20,
                                        interval_count: int = 1):
        """Set the closed loop speed and accel in um/sec and um/(sec^2)
        respectively.

        :param vel_um_per_second: speed in [um/s].
        :param accel_um_per_sq_second: acceleration in [um/s^2] .
        :param min_vel_um_per_second: minimum velocity in [um/s]. (Optional).
        :param interval_count: interval duration in number of intervals.
            (Optional). (Don't change this unless you really know what you're
            doing!)
        """
        assert vel_um_per_second > min_vel_um_per_second, \
            "Error: requested velocity must be faster than the minimum " \
            f"velocity: {min_vel_um_per_second} [um/s]."
        um_per_second = vel_um_per_second
        um_per_squared_second = accel_um_per_sq_second
        cutoff_vel_um_per_sec = min_vel_um_per_second

        vel_counts_per_interval = \
            round((um_per_second/(self.__class__.ENC_RES_NM/1000.)) * 256
                  * (interval_count*(self.__class__.INTERVAL/1.0e6)))
        cutoff_vel_counts_per_interval = \
            round(cutoff_vel_um_per_sec/(self.__class__.ENC_RES_NM/1e3) * 256
                  * (interval_count * (self.__class__.INTERVAL/1e6)))
        accel_counts_per_sq_interval = \
            round(vel_counts_per_interval
                  / (um_per_second/um_per_squared_second)
                  * interval_count * (self.__class__.INTERVAL/1e6))
        interval_duration_intervals = interval_count

        # Check the size of values as they would appear on the register.
        assert len(bin(vel_counts_per_interval)[2:]) <= 24, \
            f"Requested velocity is too large."
        assert len(bin(cutoff_vel_counts_per_interval)[2:]) <= 24, \
            "Requested cutoff velocity is too large."
        assert len(bin(accel_counts_per_sq_interval)[2:]) <= 24,\
            "Requested acceleration is too large."
        # Note that interval duration is fixed for now.
        self._send(self._get_cmd_str(Cmd.CLOSED_LOOP_SPEED,
                                     f"{vel_counts_per_interval:06x}",
                                     f"{cutoff_vel_counts_per_interval:06x}",
                                     f"{accel_counts_per_sq_interval:06x}",
                                     f"{interval_duration_intervals:04x}"))

    # <40> variant
    def get_closed_loop_speed_and_accel(self):
        """Get closed loop speed and acceleration settings.

        :return: a size-4 list of ``[<speed in [um/s]>,
            <acceleration in [um/s^2]>, <minimum speed in [um/s]>,
            <interval count>)``
        """
        # Note that conversion equations come from datasheet.
        _, vel_counts_per_interval, min_vel_counts_per_interval, \
        accel_counts_per_sq_interval, interval_count = \
            self._send(self._get_cmd_str(Cmd.CLOSED_LOOP_SPEED))
        # Helper value.
        counts_per_interval_to_um_per_sec = \
            (self.__class__.ENC_RES_NM*1.0e6) \
            / (1.0e3*256*interval_count*self.__class__.INTERVAL)
        #  Convert raw register values to have familiar units where possible.
        vel_um_per_second = \
            vel_counts_per_interval * counts_per_interval_to_um_per_sec
        min_vel_um_per_second = \
            min_vel_counts_per_interval * counts_per_interval_to_um_per_sec
        # accel value depends on raw velocity and accel regsiters AND
        # velocity computed in um/sec.
        accel_um_per_sq_second = \
            (vel_um_per_second*accel_counts_per_sq_interval*1e6) \
            / (vel_counts_per_interval*interval_count*self.__class__.INTERVAL)
        return [vel_um_per_second, accel_um_per_sq_second,
                min_vel_um_per_second, interval_count]

    # <46>
    def set_soft_limits(self, min_limit_um: float, max_limit_um: float,
                        margin_um: float = 0):
        """Set the soft limit values in um.

        Note: soft limits needs to be enabled via :meth:`enable_soft_limits`
        for these values to have any effect.

        :param min_limit_um: The minimum limit in [um] (aka: the "reverse
            limit").
        :param max_limit_um: The maximum limit in [um] (aka: the "forward
            limit").
        :param margin_um: The distance in [um] before each limit where
            the :attr:`~newscale.device_codes.StateBit.FORWARD_LIMIT_REACHED`
            or :attr:`~newscale.device_codes.StateBit.REVERSE_LIMIT_REACHED`
            :obj:`~newscale.device_codes.StateBit` flags will remain active
            after the limit has been tripped (aka: hysteresis).
        """
        # Convert to encoder counts.
        min_value = round(min_limit_um * 1e3 / self.__class__.ENC_RES_NM)
        max_value = round(max_limit_um * 1e3 / self.__class__.ENC_RES_NM)
        margin_value = round(margin_um * 1e3 / self.__class__.ENC_RES_NM)
        # Check that requested values will fit in register representation.
        # Note: We can't use bit_length() for signed numbers.
        assert -0x80000000 <= min_value <= 0x7FFFFFFF, "Error, requested " \
            "minimum limit is out of range."
        assert -0x80000000 <= max_value <= 0x7FFFFFFF, "Error, requested " \
            "maximum limit is out of range."
        assert 0x0000 <= margin_value <= 0xFFFF, "Error, requested " \
            "error margin (hysteresis) value is out of range."
        # Convert to 32-bit, 2's complement representation for signed
        # numbers. "Zero-stuff" up to 32 bits for positive numbers in the
        # outgoing string representation.
        min_value = min_value & 0xFFFFFFFF  # Force 32 bit size, two's comp.
        max_value = max_value & 0xFFFFFFFF
        self._send(self._get_cmd_str(Cmd.SOFT_LIMIT_VALUES,
                                     f"{max_value:08x}", f"{min_value:08x}",
                                     f"{margin_value:04x}"))

    # <46> variant
    def get_soft_limits(self):
        """Get the soft travel limit minimum, maximum, and error margin.

        :return: 3-Tuple of
            ``<min limit [um]>, <max limit [um]>, <error margin [um]>)`` where
            the error margin represents a value before the limit where the
            :attr:`~newscale.device_codes.StateBit.FORWARD_LIMIT_REACHED` or
            :attr:`~newscale.device_codes.StateBit.REVERSE_LIMIT_REACHED`
            :obj:`~newscale.device_codes.StateBit` flags will remain active
            after the limit has been tripped (aka: hysteresis).
        """
        max_limit_reg, min_limit_reg, error_reg = \
            self._send(self._get_cmd_str(Cmd.SOFT_LIMIT_VALUES))[1:]
        return min_limit_reg * self.__class__.ENC_RES_NM / 1.e3, \
               max_limit_reg * self.__class__.ENC_RES_NM / 1.e3, \
               error_reg * self.__class__.ENC_RES_NM / 1.e3

    # <47> Enable/Disable soft limits.
    def _set_soft_limit_state(self, soft_limits_enabled: bool):
        """Enable or disable soft limits.

        :param soft_limits_enabled: True to enable soft limits. False to
            disable.
        """
        soft_limit_state = f"{1:04x}" if soft_limits_enabled else f"{0:04x}"
        self._send(self._get_cmd_str(Cmd.SOFT_LIMIT_STATES, soft_limit_state))

    # <47> variant
    def enable_soft_limits(self):
        """Enable software-based stage travel limits.
        These values can be set with :meth:`set_soft_limit_values`.
        """
        self._set_soft_limit_state(True)

    # <47> variant
    def disable_soft_limits(self):
        """Disable software-based stage travel limits.
        These values can be set with :meth:`set_soft_limit_values`.
        """
        self._set_soft_limit_state(False)

    # <52>
    def get_time_interval_units(self):
        """Get the time interval units for this particular M3 stage.

        Note: M3-LS, M3-L, and M3-FS have different time interval units, but
        time interval units are the same within these "sub-families."

        :return: the time interval in [us].
        """
        # Cache this since it won't change.
        # Don't use @cache or @cached_property for pre 3.8 compatibility.
        if self.time_interval_us is not None:
            return self.time_interval_us
        _, data_str = self._send(self._get_cmd_str(Cmd.TIME_INTERVAL_UNITS))
        val_str, _ = data_str.split()  # last chunk is the string 'USEC'
        self.time_interval_us = float(val_str)
        return self.time_interval_us

    # <54> variant
    def set_baud_rate(self, baud_rate: int):
        """Set the stage uart baud rate from the options available.
        Baud rate changes take effect on the next power cycle.

        `Warning`: the uart pins are not exposed on most M3 linear stages,
        whose wires only expose the SPI interface.
        """
        assert baud_rate in BaudRateCode, \
            "Requested input baud rate is invalid."
        baud_rate_code = BaudRateCode[baud_rate]
        self._send(self._get_cmd_str(Cmd.BAUD_RATE, baud_rate_code))

    # <54> variant
    def get_baud_rate(self):
        """get the stage's communication baud rate.
        :return: the stage's baud rate as an integer
        """
        _, _, br_code = self._send(self._get_cmd_str(Cmd.BAUD_RATE))
        return BaudRateCode.inverse[f"{br_code:02x}"]

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
