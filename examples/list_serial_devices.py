#!/usr/bin/env python3

from newscale.interfaces import NewScaleSerial

instances = NewScaleSerial.get_instances()
for i in instances:
    print('Serial #%d, on %s', (i.get_serial_number(), i.get_port_name()))
