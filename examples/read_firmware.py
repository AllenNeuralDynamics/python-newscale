#!/usr/bin/env python3

import pprint
import sys

from newscale.interfaces import USBInterface
from newscale.new_scale_serial import NewScaleSerial, get_instances
from newscale.stage import M3LinearSmartStage

# Uncomment for some prolific log statements.
#import logging
#logger = logging.getLogger()
#logger.setLevel(logging.DEBUG)
#logger.addHandler(logging.StreamHandler())
#logger.handlers[-1].setFormatter(
#    logging.Formatter(fmt='%(asctime)s:%(name)s:%(levelname)s: %(message)s'))

# Connect to a single stage.
instances = list(get_instances().values())
if len(instances) == 0:
    sys.exit(1)
serialInstance = instances[0]
stage = M3LinearSmartStage(USBInterface(serial=serialInstance), "01")

# Print firmware version, closed loop state, position, and motor status
print(f"Firmware is {stage.get_firmware_version()}.")
pprint.pprint(stage.get_closed_loop_state_and_position())
pprint.pprint(stage.get_motor_status())
