#!/usr/bin/env python3

import pprint
from random import uniform
from time import perf_counter, sleep
import sys

from newscale.device_codes import Direction
from newscale.multistage import USBXYZStage, PoEXYZStage
from newscale.interfaces import NewScaleSerial, USBInterface

MIN_TRAVEL_UM = 0
MAX_TRAVEL_UM = 15000

# Create USBXYZStage
instances = NewScaleSerial.get_instances()
if len(instances) == 0:
    sys.exit(1)
serialInstance = instances[0]
stage = USBXYZStage(usb_interface=USBInterface(serialInstance))

# Closed loop moves.
stage.move_absolute(x=1000)
stage.move_absolute(x=14000)
stage.move_absolute(x=7500)

# cleanup
stage.close()
print("Done.")

