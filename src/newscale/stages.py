"""Class for creating commands for a stage and interpreting replies.

This class is a collection of functions that return valid input strings that
can be sent to the hardware by some interface (USB, PoE, SPI, I2C).
"""

# General approach for unpacking replies will probably be something like:
# >>> my_bit_array = BitArray(hex='FFFFFF 00000001 00000002')
# >>> my_bit_array.unpack('int:24, int:32, int:32')

import logging
from bitstring import Bits  # for unpacking
#from newscale.device_codes import Cmd, StateBit, Direction
#from newscale.interfaces import Interface
from device_codes import Cmd, StateBit, Direction, Encoding


# Constants
TICKS_PER_UM = 2.0  # encoder ticks per micrometer.
TICKS_PER_MM = TICKS_PER_UM * 1000.


class USBXYZStage:

    def __init__(self, port: None, serial_interface: SerialInterface = None):
        self.interface = Serial if serial_interface else SerialInterface(port)
        # Create 3 stages.
        stages = {'x': M3LinearSmartStage('01', self.interface),
                  'y': M3LinearSmartStage('02', self.interface),
                  'z': M3LinearSmartStage('03', self.interface)}
        super().__init__(**stages)


class MultiStage:

    def __init__(self, **stages):
        self.stages = stages

    def move_absolute(self, **axes):
        pass

    def move_relative(self, **axes):
        pass

    def halt(self):
        pass


class M3LinearSmartStage:

    def __init__(self, address: str = None, interface: Interface = None,
                 create: bool = False):
        """Create hardware interface if unspecified or use an existing one."""
        # Either address can be passed in XOR interface
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.address = address
        self.interface = Interface() if address else interface

    @staticmethod
    def _get_cmd_str(cmd: Cmd, *args: str):
        args_str = " ".join([a.upper() for a in args if a is not None])
        return f"<{cmd.value.upper()} {args_str}>\r"

    @staticmethod
    def _parse_reply(reply: str):
        """Turn string reply into a Cmd plus one or more response integers."""
        reply = reply.strip("<>\r")
        # Receive a cmd key with possibly additional trailing words.
        cmd_chunks = reply.split(" ", 1)  # split on the first space.
        cmd = Cmd(cmd_chunks[0])
        if len(cmd_chunks) == 1:
            return cmd
        # Case-Dependent behavior for replies with additional words.
        if cmd == Cmd.FIRMWARE_VERSION:  # The trailing words form a message.
            return cmd, cmd_chunks[1]
        else:  # Everything else returns one or more ints of various sizes.
            bit_array = BitArray(hex=cmd_chunks[1])
            return cmd, *bit_array.unpack(ReplyEncoding[cmd])

    def _send(self, cmd_str: str):
        """Send a command and return the parsed reply."""
        self.interface.send(self.address, cmd_str)
        return _parse_reply(self.interface.read())

    # <01>
    def get_firmware_version(self):
        """Get the firmware version."""
        return self._send(get_cmd_str(Cmd.FIRMWARE_VERSION))

    # <03>
    def halt(self):
        return self._send(get_cmd_str(Cmd.HALT))

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
            return self._send(get_cmd_str(Cmd.RUN, direction.value))
        duration = round(seconds*10) # value is encoded in tenths of seconds.
        assert duration < 256, "Time input value exceeds maximum value."
        return self._send(get_cmd_str(Cmd.RUN, direction.value,
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
        return self._send(get_cmd_str(Cmd.STEP_CLOSED_LOOP, direction.value,
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
            return get_cmd_str(Cmd.MOVE_TO_TARGET)
        step_size_ticks = round(setpoint_mm*TICKS_PER_MM)
        assert step_size_ticks.bit_length() < 32, "Step size exceeds maximum."
        return self._send(get_cmd_str(Cmd.MOVE_TO_TARGET,
                                      f"{step_size_ticks:08x}"))

    # <09>
    def set_open_loop_speed(self, percentage: float):
        speed_byte = round(percentage/100 * 255)
        assert 1 < speed_byte < 256, "speed setting out of range."
        return self._send(get_cmd_str(Cmd.SPEED_OPEN_LOOP,
                                      f"{speed_byte:02x}"))

    # <10>
    def get_closed_loop_state_and_position(self):
        # use get_state
        _, state_int = self._send(self._get_cmd_str(Cmd.CLOSED_LOOP_STATE))
        return self._parse_state(state_int)

    @staticmethod
    def _parse_state(state: int):
        """Convert state integer (<10> reply) to dict keyed by state bit."""
        # Convert int to array of bits
        state_bits = [True if digit == '1' else False for digit in bin(n)[2:]]
        # Iterate through StateBit Enum and reply to create a dict
        return {k: v for k, v in zip(StateBit, state_bits)
                if not k.name.startswith('RESERVED')}

    # <19>
    def get_motor_status(self):
        _, state_int = _send(self._get_cmd_str(Cmd.MOTOR_STATUS))
        return self._parse_motor_flags(state_int)

    @staticmethod
    def _parse_motor_flags(state: int):
        """Convert Motor Flags integer (<19> reply) to dict keyed by state bit
        """
        state_bits = [True if digit == '1' else False for digit in bin(n)[2:]]
        state_bit_subset = list(StateBit)[:16]
        return {k: v for k, v in zip(state_bit_subset, state_bits)
                if not k.name.startswith('RESERVED')}

    # <46>
    def set_soft_limit_values(self, min_value, max_value):
        # FIXME
        return get_cmd_str(Cmd.SOFT_LIMIT_VALUES, min_value, max_value)


if __name__ == "__main__":
    print("Enable motor:")
    print(run(Direction.FORWARD, 10))
    print("Move to target:")
    print(move_to_target(50.0))
    print("Set Open Loop Speed:")
    print(set_open_loop_speed(100.0))
