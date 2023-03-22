#!/usr/bin/env python3

"""
This demonstrates the use of USBXYZStage, taking the first instance of
NewScaleSerial and moving it back and forth along all 3 axes.
"""

import sys

from newscale.multistage import USBXYZStage
from newscale.interfaces import USBInterface
from newscale.new_scale_serial import NewScaleSerial, get_instances

MIN_TRAVEL_UM = 0
MAX_TRAVEL_UM = 15000

# Create USBXYZStage
instances = list(get_instances().values())
if len(instances) == 0:
    sys.exit(1)
usb_interface = USBInterface(serial=instances[0])
stage = USBXYZStage(usb_interface=usb_interface)

# X-axis
stage.move_absolute(x=1000)
stage.move_absolute(x=14000)
stage.move_absolute(x=7500)

# Y-axis
stage.move_absolute(y=1000)
stage.move_absolute(y=14000)
stage.move_absolute(y=7500)

# Z-axis
stage.move_absolute(z=1000)
stage.move_absolute(z=14000)
stage.move_absolute(z=7500)

# cleanup
stage.close()
print("Done.")

