#!/usr/bin/env python3

import pprint

from newscale.interfaces import M3USBInterface, PoEInterface
from newscale.stage import M3LinearSmartStage

# Uncomment for some prolific log statements.
#import logging
#logger = logging.getLogger()
#logger.setLevel(logging.DEBUG)
#logger.addHandler(logging.StreamHandler())
#logger.handlers[-1].setFormatter(
#    logging.Formatter(fmt='%(asctime)s:%(name)s:%(levelname)s: %(message)s'))

# Connect to a single stage.
#stage = M3LinearSmartStage(PoEInterface(address="10.128.49.57"), "01")
stage = M3LinearSmartStage(M3USBInterface(port='/dev/ttyUSB0'), "01")
print(f"Firmware is {stage.get_firmware_version()}.")
pprint.pprint(stage.get_closed_loop_state_and_position())
pprint.pprint(stage.get_motor_status())
