#!/usr/bin/env python3

import pprint

from newscale.interfaces import NewScaleSerial, USBInterface
from newscale.stage import M3LinearSmartStage

# Uncomment for some prolific log statements.
#import logging
#logger = logging.getLogger()
#logger.setLevel(logging.DEBUG)
#logger.addHandler(logging.StreamHandler())
#logger.handlers[-1].setFormatter(
#    logging.Formatter(fmt='%(asctime)s:%(name)s:%(levelname)s: %(message)s'))

# Connect to a single stage.
instances = NewScaleSerial.get_instances()
if len(instances) == 0:
    sys.exit(1)
else:
    serialInstance = instances[0]
stage = M3LinearSmartStage(USBInterface(serialInstance), "01")

# Print firmware version, closed loop state, position, and motor status
print(f"Firmware is {stage.get_firmware_version()}.")
pprint.pprint(stage.get_closed_loop_state_and_position())
pprint.pprint(stage.get_motor_status())
