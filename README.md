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

## On Windows
You must first install the [Silicon Labs USBXpress Driver](https://www.silabs.com/documents/public/software/install_USBXpress_SDK.exe).

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
