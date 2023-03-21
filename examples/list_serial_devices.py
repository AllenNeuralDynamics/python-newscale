#!/usr/bin/env python3

from newscale.new_scale_serial import get_instances

instances = get_instances()
for k, v in instances.items():
    print(f"Serial # {k}, on {type(v)} interface.")
