#!/usr/bin/env python3

from newscale.stages import USBXYZStage
from newscale.device_codes import Direction
from newscale.interfaces import MockInterface, SerialInterface
from random import uniform
from time import sleep
import logging

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

MIN_TRAVEL = 0
MAX_TRAVEL = 15

port = '/dev/ttyUSB0'

stage = USBXYZStage(port)
# Move a random amount.
stage.move_absolute(x=uniform(MIN_TRAVEL, MAX_TRAVEL),
                    y=uniform(MIN_TRAVEL, MAX_TRAVEL),
                    z=uniform(MIN_TRAVEL, MAX_TRAVEL))
print(f"position is: {stage.get_position('x', 'y', 'z')}")
stage.move_absolute(x=7.5, y=7.5, z=7.5)
print(f"position is: {stage.get_position('x', 'y', 'z')}")
print("Done moving.")

