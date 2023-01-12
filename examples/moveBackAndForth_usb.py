#!/usr/bin/env python3

import sys

from newscale.multistage import USBXYZStage
from newscale.interfaces import NewScaleSerial, USBInterface

MIN_TRAVEL_UM = 0
MAX_TRAVEL_UM = 15000

# Create USBXYZStage
instances = NewScaleSerial.get_instances()
if len(instances) == 0:
    sys.exit(1)
serialInstance = instances[0]
stage = USBXYZStage(usb_interface=USBInterface(serialInstance))

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

