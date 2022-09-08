#!/usr/bin/python3

import socket
from newscale.stages import M3_LS_34_15_XYZ_PoE as Stage

socket.setdefaulttimeout(1) # 1 second timeout

IP = '10.128.49.22'
PORT = 23

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((IP, PORT))

stage = Stage(sock)
fw_version = stage.readFirmwareVersion()
print('Firmware Version: ', fw_version)
stage.close()

