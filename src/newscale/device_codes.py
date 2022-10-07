"""Collection of interface-agnostic device commands to get/set state."""

import logging
import sys
from enum import Enum

try:
    from enum import StrEnum  # a 3.11 freature.
except ImportError:
    logging.error("StrEnum not available with this version of python."
                  "Creating it.")

    class StrEnum(str, Enum):
        pass


class Cmd(StrEnum):
    # Cmds echo back, so some commands can only be read back from the device.
    FIRMWARE_VERSION = "01"
    HALT = "03"
    RUN = "04"
    STEP_OPEN_LOOP = "05"  # Step at a fixed speed for a pre-specified time
    STEP_CLOSED_LOOP = "06"  # Step for a fixed distance
    TOGGLE_ABS_REL = "07"
    MOVE_TO_TARGET = "08"  # Move to a specified setpoint
    SPEED_OPEN_LOOP = "09"
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
    DO_FREQ_CALIBRATION = "87"
    POSITION_CONTROL_LOG = "A9"


class StateBit(Enum):
    """Bitfield offsets for interpretting commands <10> and <19>"""
    RESERVED_0 = 0
    MOTOR_DIRECTION = 1
    RUNNING = 2
    DRIVER_NOT_RESPONSIVE = 3
    BURST_MODE = 4
    TIMED_RUN = 5
    MULTIPLEXED_AXIS = 6
    HOST_CONTROL_ESTABLISHED = 7
    RESERVED_8 = 8
    FORWARD_LIMIT_REACHED = 9
    REVERSE_LIMIT_REACHED = 10
    MOTOR_MODE = 11  # 0 = Amplitude Mode, 1 = Burst Mode
    RESERVED_12 = 12
    RESERVED_13 = 13
    RESERVED_14 = 14
    BACKGROUND_JOB_ACTIVE = 15
    ENCODER_ERROR = 16
    ZERO_REFERENCE_ENABLED = 17
    MOTOR_ON_TARGET = 18
    MOTOR_MOVING_TOWARD_TARGET = 19
    MAINTENANCE_MODE_ENABLED = 20
    CLOSED_LOOP_ENABLED = 21
    MOTOR_ACCELERATING = 22
    STALLED = 23


class Direction(StrEnum):
    BACKWARD = 0
    FORWARD = 1





