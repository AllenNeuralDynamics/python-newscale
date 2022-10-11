#!/usr/bin/env python3

from newscale.stages import M3LinearSmartStage
from newscale.device_codes import Direction
from newscale.interfaces import MockInterface
from time import sleep
import logging

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

stage = M3LinearSmartStage(MockInterface())
print("running stage.")
stage.run(Direction.FORWARD, 3)
sleep(0.5)
stage.run(Direction.BACKWARD, 3)

