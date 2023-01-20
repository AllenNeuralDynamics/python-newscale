#!/usr/bin/env python3

"""
Do a frequency calibration on all axes of a USBXYZStage.
This should be done occasionally to calibrate the PID controller.
Note that the stage will move up to 250 um along each axes during this process.
"""

import sys

from newscale.multistage import USBXYZStage
from newscale.interfaces import NewScaleSerial, USBInterface

# Create USBXYZStage
instances = NewScaleSerial.get_instances()
if len(instances) == 0:
    sys.exit(1)
serialInstance = instances[0]
stage = USBXYZStage(usb_interface=USBInterface(serialInstance))

# X-axis
stage.calibrate_all()

# cleanup
stage.close()
print("Done.")

