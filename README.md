# python-newscale

[![License](https://img.shields.io/badge/license-MIT-brightgreen)](LICENSE)


Python library for controlling the micromanipulator systems from New Scale
Technologies.

This library implements the suite of commands for M3 Linear Smart Stages and wraps them into a collection of convenience functions.
Stage Commands can be referenced from
* [Newscale Pathway Software Datasheet](https://www.newscaletech.com/wp-content/uploads/cad/Newscale_PathwaySoftwareManual.pdf), ([backup link](https://aind.tech/docs/Newscale_PathwaySoftwareManual.pdf)) and
* [M3-LS-3.4-15 Command and Control Reference Guide](https://www.newscaletech.com/wp-content/uploads/cad/M3-LS-3-4-15-Command-and-Control-Reference-Guide.pdf) ([backup link](https://aind.tech/docs/06224-M-0003%20M3-LS-3.4-15%20Command%20and%20Control%20Reference%20Guide.pdf))

## Installation
To install this library, in the root directory, run:
```
pip install -e .
```

## Quickstart
To connect to an XYZ stage over a USB interface, invoke:
```python
from newscale.multistage import USBXYZStage
from newscale.device_codes import Direction

stage = USBXYZStage('COM4')
```

## Usage
Check the [examples directory](examples) for more usage examples.

## Provisioning an M3 USB Interface as a Virtual Com Port (Windows Only)
The following extra steps must be taken on Windows only before the driver works.

1. First, install Newscale's Pathway Software. (You may need to create an account first before you can download it.)
Post-installation, the Silicon Labs USBXpress Driver should be installed (if it wasn't already).
2. Next, install the Silicon Labs Virtual Com Port Driver.
You can find the driver in the Newscale Pathway Software download (in the SI_COM folder) *or* on Silicon Labs' [website](https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers?tab=downloads).
3. Next, launch the NstUsbBridgeSetup.exe utility.
This is likely located in: `C:\Program Files (x86)\New Scale Technologies\Closed,Open Loop Demo`.
4. From the GUI, find your device, check **SiLabs' COM Port**, and click **Save Identity**.
About 5 seconds must elapse. Then the device should show up in Device Manager as a Virtual Com Port.

Note: you must re-run this utility and check **SiLabs' USB Port** if you want this device to re-communicate with Newscale's Pathway Software.


It's worth mentioning that this utility has the effect of changing the device's PID from 0xEA61 to 0xEA60, which causes Windows to recognize it as a COM Port.
Restoring the device to a **SiLabs' USB Port** changes it back to 0xEA60.

## Troubleshooting
The most likely issue with communicating with stages is baud rate mismatches.
Note that both the USB interface, like the  M3-USB-3:1-EP, and each stage have baud rates that must agree.
It may be that you can communicate with the USB interface but not the stage that it is connected to.

To connect to the M3-USB-3:1-EP on a different baud rate, you can simply pass it in:
````python
stage = USBXYZStage('COM4', 115200)
````

## Contributing
See [CONTRIBUTING.md](CONTRIBUTING.md) for details.
