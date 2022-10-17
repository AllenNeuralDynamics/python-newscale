#!/usr/bin/env python3

from newscale.stages import USBXYZStage
from newscale.device_codes import Direction
from newscale.interfaces import MockInterface, SerialInterface
from random import uniform
from time import sleep, perf_counter
import logging

# Uncomment for some prolific log statements.
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

MIN_TRAVEL = 0
MAX_TRAVEL = 15

port = '/dev/ttyUSB0'

stage = USBXYZStage(port)
stage.set_closed_loop_mode()
# Move a random amount.
print("Moving and waiting")
# Function returns when the move is done (or timeout).
stage.move_absolute(x=uniform(MIN_TRAVEL, MAX_TRAVEL),
                    y=uniform(MIN_TRAVEL, MAX_TRAVEL),
                    z=uniform(MIN_TRAVEL, MAX_TRAVEL))
print(f"position is: {stage.get_position('x', 'y', 'z')}")
sleep(1)
print()
print("Moving and NOT waiting")
# Function returns immediately after stage confirms command.
stage.move_absolute(x=7.5, y=7.5, z=7.5, wait=False)
# Poll the position manually.
start_time = perf_counter()
while perf_counter() - start_time < 4:
    print(f"position is: {stage.get_position('x', 'y', 'z')}")
    sleep(0.25)
sleep(1)

# Time Moves:
print()
print("Time move and waiting.")
stage.set_open_loop_mode()
# This will throw an error if mode is not set to open loop first.
stage.move_for_time(x=(Direction.FORWARD, 0.25),
                    y=(Direction.FORWARD, 0.5),
                    z=(Direction.FORWARD, 0.75))
print(f"position is: {stage.get_position('x', 'y', 'z')}")
print("Done.")

