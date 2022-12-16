#!/usr/bin/env python3

from newscale.interfaces import NewScaleSerial


instances = NewScaleSerial.get_instances()

print('New Scale Serial Instances: ', len(instances))
for instance in instances:
    print('\tserial number ', instance.get_serial_number())
