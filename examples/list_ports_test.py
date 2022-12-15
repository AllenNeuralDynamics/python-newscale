#!/usr/bin/env python3

from newscale.multistage import USBXYZStage

ports = USBXYZStage.list_available_ports()
print('ports: ', ports)
