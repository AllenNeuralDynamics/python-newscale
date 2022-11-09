#!/usr/bin/env python3

import pprint
from random import uniform
from time import perf_counter, sleep

from newscale.device_codes import Direction
from newscale.multistage import USBXYZStage, PoEXYZStage

# Uncomment for some prolific log statements.
#import logging
#logger = logging.getLogger()
#logger.setLevel(logging.DEBUG)
#logger.addHandler(logging.StreamHandler())
#logger.handlers[-1].setFormatter(
#   logging.Formatter(fmt='%(asctime)s:%(name)s:%(levelname)s: %(message)s'))

MIN_TRAVEL_UM = 0
MAX_TRAVEL_UM = 15000

# Create Stage depending on interface.
port = '/dev/ttyUSB0'
stage = USBXYZStage(port)
#ip_address = "10.128.49.57"
#stage = PoEXYZStage(ip_address)

# Closed loop moves.
print("Moving and waiting")
# Move a random amount.
# Function returns when the move is done (or timeout).
stage.move_absolute(x=uniform(MIN_TRAVEL_UM, MAX_TRAVEL_UM),
                    y=uniform(MIN_TRAVEL_UM, MAX_TRAVEL_UM),
                    z=uniform(MIN_TRAVEL_UM, MAX_TRAVEL_UM))
print(f"position is: {stage.get_position('x', 'y', 'z')}")
sleep(1)
print()
print("Moving and NOT waiting")
# Function returns immediately after stage confirms command.
stage.move_absolute(x=7500, y=7500, z=7500, wait=False)
# Poll the position manually.
start_time = perf_counter()
while perf_counter() - start_time < 4:
    print(f"position is: {stage.get_position('x', 'y', 'z')}")
    sleep(0.25)
sleep(1)

# Time Moves:
print()
print("Time move and waiting.")
stage.move_for_time(x=(Direction.FORWARD, 0.25),
                    y=(Direction.FORWARD, 0.5),
                    z=(Direction.FORWARD, 0.75))
print(f"position is: {stage.get_position('x', 'y', 'z')}")
sleep(1)

# Speed changes
print("Returning to midpoints.")
speed_settings = stage.get_closed_loop_speed_and_accel()
print(f"Original speed settings are:")
pprint.pprint(speed_settings)
old_x_speed = speed_settings['x'][0]  # save original x axis speed.
speed_settings['x'][0] = 2000.  # Slow down x axis.
print(f"New speed settings are:")
pprint.pprint(speed_settings)
stage.set_closed_loop_speed_and_accel(**speed_settings)
print("Moving to origin.")
stage.move_absolute(x=0, y=0, z=0)
print("Moving to midpoint.")
stage.move_absolute(x=7500, y=7500, z=7500)
print("Restoring speed settings.")
speed_settings['x'][0] = old_x_speed  # restore original x axis speed.
stage.set_closed_loop_speed_and_accel(x=speed_settings['x'])

stage.close()
print("Done.")

