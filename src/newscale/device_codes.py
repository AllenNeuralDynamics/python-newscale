"""Collection of interface-agnostic device commands to get/set state."""

from enum import Enum

from bidict import bidict
from bitstring import BitArray

try:
    from enum import StrEnum  # a 3.11 feature.
except ImportError:
    class StrEnum(str, Enum):
        pass


# Constants
TRANSCEIVER_PREFIX = "TR"


# Commands, collected as Enums
class StageCmd(StrEnum):
    """Commands for the stage.
    When issued, the actual command is wrapped inside of '<' '>'.

    Example: '<01>', '<02>', etc.
    """
    # Cmds echo back, so some commands can only be read back from the device.
    FIRMWARE_VERSION = "01"  # Dual purpose. Also establishes host control.
    RELEASE_HOST_CONTROL = "02"
    HALT = "03"
    RUN = "04"
    STEP_OPEN_LOOP = "05"  # Step at a fixed speed for a pre-specified time
    STEP_CLOSED_LOOP = "06"  # Step for a fixed distance
    CLEAR_ENCODER_COUNT = "07"
    MOVE_TO_TARGET = "08"  # Move to a specified setpoint
    OPEN_LOOP_SPEED = "09"
    CLOSED_LOOP_STATE = "10"
    MOTOR_STATUS = "19"
    DRIVE_MODE = "20"
    ILLEGAL_COMMAND_FORMAT = "23"
    ILLEGAL_COMMAND = "24"
    CLOSED_LOOP_SPEED = "40"
    ERROR_THRESHOLDS_AND_STALL_DETECTION = "41"
    PID_COEFFICIENTS = "43"
    SOFT_LIMIT_VALUES = "46"  # motor values for forward/reverse soft limits.
    SOFT_LIMIT_STATES = "47"  # whether soft limits are active.
    TIME_INTERVAL_UNITS = "52"
    BAUD_RATE = "54"
    EEPROM_WRITING_STATE = "58"
    SAVE_CLOSED_LOOP_STATE_TO_EEPROM = "74"
    RUN_FREQ_CALIBRATION = "87"
    POSITION_CONTROL_LOG = "A9"


class TransceiverCmd(StrEnum):
    """Commands for Stage transceivers (M3-USB-3:1-EP, M3-PoE-3:1-6V, etc).
    When issued, they must be prefixed with 'TR' and the actual command is
    wrapped inside of '<' '>'.

    Example: 'TR<01>', 'TR<A2>', etc.
    """
    FIRMWARE_VERSION = "01"
    BAUD_RATE = "54"
    STAGE_SELECT = "A0"
    MAC_ADDRESS = "A2"


# Reply Encodings for pulling values out of the reply strings.
# Note: We can't use struct.unpack since the replies come in non-ctype
#   size signed and unsigned values (example: 24-bit signed integer).
StageReplyEncoding = \
{
    StageCmd.FIRMWARE_VERSION: "int:4", # Remaining response is a string.
    StageCmd.MOVE_TO_TARGET: "int:32",
    StageCmd.OPEN_LOOP_SPEED: "uint:8",
    StageCmd.CLOSED_LOOP_STATE: "uint:24, int:32, int:32",
    StageCmd.MOTOR_STATUS: "uint:16",
    StageCmd.DRIVE_MODE: "uint:4, uint:16",  # TODO: check if we get 'R' as a reply back from the controller.
    StageCmd.CLOSED_LOOP_SPEED: "uint:24, uint:24, uint:24, uint:16",
    StageCmd.ERROR_THRESHOLDS_AND_STALL_DETECTION: "uint:1, int:24, int:24",
    StageCmd.PID_COEFFICIENTS: "int:16, int:16, int:16",
    StageCmd.SOFT_LIMIT_VALUES: "int:32, int:32, uint:16",
    StageCmd.SOFT_LIMIT_STATES: "uint:4",
    StageCmd.TIME_INTERVAL_UNITS: "",  # Response is a string.
    StageCmd.BAUD_RATE: "uint:4, uint:8",
    StageCmd.EEPROM_WRITING_STATE: "uint:8, uint:4",
    StageCmd.RUN_FREQ_CALIBRATION: "uint:4, uint:8, uint:8",
    #StageCmd.POSITION_CONTROL_LOG: ""
}

TransceiverReplyEncoding = \
{
    TransceiverCmd.FIRMWARE_VERSION: "int:4",
    TransceiverCmd.BAUD_RATE: "uint:4, uint:8",
    TransceiverCmd.STAGE_SELECT: "uint:8, uint:4",
}


def parse_reply(reply: str, conversion_key: dict):
    """Turn string reply into a Cmd plus one or more response integers."""
    Cmd = TransceiverCmd if conversion_key == TransceiverReplyEncoding \
        else StageCmd
    reply = reply.strip("<>\r")
    # Receive a cmd key with possibly additional trailing words.
    cmd_chunks = reply.split(" ", 1)  # split on the first space.
    cmd = Cmd(cmd_chunks[0])
    if len(cmd_chunks) == 1:
        return (cmd,)
    # Return ILLEGAL_COMMAND--even if it returns with arguments.
    if Cmd == StageCmd and cmd == Cmd.ILLEGAL_COMMAND:
        return (cmd,)
    # Everything else returns sequence of 0 or more ints of various sizes
    # possibly followed by a string.
    # Split reply into parseable (sequence of ints) and
    # unparseable (string msg at the end).
    int_count = len(conversion_key[cmd].split())  # How many parseable ints.
    # split after int_count occurrences of " ".
    tmp = cmd_chunks[1].split(" ", int_count)
    parseable_params = " ".join(tmp[:int_count])
    unparsed = tmp[int_count:]
    # General approach for unpacking replies looks like:
    # >>> bit_array = BitArray(hex='FFFFFF 00000001 00000002')
    # >>> bit_array.unpack('int:24, int:32, int:32')  # returns a 3-tuple.
    bit_array = BitArray(hex=parseable_params)
    return (cmd, *bit_array.unpack(conversion_key[cmd]), *unparsed)


# Convenience functions.
def parse_stage_reply(reply: str):
    return parse_reply(reply, StageReplyEncoding)


def parse_tr_reply(reply: str):
    return parse_reply(reply, TransceiverReplyEncoding)


# Extra Structures for specifying stage commands and parsing stage replies.
class StateBit(Enum):
    """Bitfield offsets for interpretting the stage's state replies from
    commands :attr:`~newscale.devices.StageCmd.CLOSED_LOOP_STATE` (<10>) and
    :attr:`~newscale.devices.StageCmd.MOTOR_STATUS` (<19>)."""
    RESERVED_0 = 0
    DIRECTION = 1
    RUNNING = 2
    DRIVER_NOT_RESPONSIVE = 3
    BURST_MODE = 4
    TIMED_RUN = 5
    MULTIPLEXED_AXIS = 6
    HOST_CONTROL_ESTABLISHED = 7
    RESERVED_8 = 8
    FORWARD_LIMIT_REACHED = 9
    REVERSE_LIMIT_REACHED = 10
    MODE = 11  # 0 = Amplitude Mode, 1 = Burst Mode
    RESERVED_12 = 12
    RESERVED_13 = 13
    RESERVED_14 = 14
    BACKGROUND_JOB_ACTIVE = 15
    ENCODER_ERROR = 16
    ZERO_REFERENCE_ENABLED = 17
    ON_TARGET = 18
    MOVING_TOWARD_TARGET = 19
    MAINTENANCE_MODE_ENABLED = 20
    CLOSED_LOOP_ENABLED = 21
    ACCELERATING = 22
    STALLED = 23


BaudRateCode = \
    bidict({
        19200: "00",
        38400: "01",
        57600: "02",
        115200: "03",
        250000: "04"
    })


class Direction(StrEnum):
    BACKWARD = "0"
    FORWARD = "1"
    NEITHER = "N"


class DriveMode(StrEnum):
    OPEN_LOOP = "0"
    CLOSED_LOOP = "1"
    MODE_QUERY = "R"


class Mode(Enum):
    AMPLITUDE = 0
    BURST = 1



