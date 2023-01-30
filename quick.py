#!/usr/bin/env python3

import time
import sys
import obd

for x in range(1, 200):
    print("try {}...".format(x))
    connection = obd.OBD("/dev/rfcomm0", baudrate=9600)
    if connection.status() != obd.OBDStatus.NOT_CONNECTED:
        break
    connection.close()
    time.sleep(1)

if connection.status() == obd.OBDStatus.NOT_CONNECTED:
    sys.exit(1)

for x in range(0, 5):
    response = connection.query(obd.commands.ELM_VOLTAGE)
    print(response.value)
    response = connection.query(obd.commands.ELM_VERSION)
    print(response.value)
    time.sleep(1)

while True:
    time.sleep(2)
    if connection.status() == obd.OBDStatus.CAR_CONNECTED:
        print("CAR_CONNECTED: I think I can, I think I can...")
        cmd = obd.commands.SPEED # select an OBD command (sensor)

        response = connection.query(cmd) # send the command, and parse the response

        print(response.value) # returns unit-bearing values thanks to Pint
        print(response.value.to("mph")) # user-friendly unit conversions

        c = obd.commands.RPM
        response = connection.query(c)
        print(response.value) # returns unit-bearing values thanks to Pint
        #print(response.value.to("rpm")) # user-friendly unit conversions
        print(connection.supported_commands)

    if connection.status() == obd.OBDStatus.OBD_CONNECTED:
        print("OBD_CONNECTED, ignition off")
        response = connection.query(obd.commands.ELM_VOLTAGE)
        print(response.value)
