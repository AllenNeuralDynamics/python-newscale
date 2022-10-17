#!/usr/bin/env python3

from newscale.stages import M3LinearSmartStage
from newscale.device_codes import Direction
from newscale.interfaces import SerialInterface, PoEInterface
from time import sleep
import logging
import pprint

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# Connect to a single stage.
#stage = M3LinearSmartStage(PoEInterface(address="192.168.1.3"), "01")
stage = M3LinearSmartStage(SerialInterface(port='/dev/ttyUSB0'), "01")
print(f"Firmware is {stage.get_firmware_version()}.")
pprint.pprint(stage.get_closed_loop_state_and_position())
pprint.pprint(stage.get_motor_status())

