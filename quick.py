#!/usr/bin/env python3

import obd

connection = obd.OBD("/dev/rfcomm0", fast=False)

response = connection.query(obd.commands.ELM_VOLTAGE)
print(response.value)
response = connection.query(obd.commands.ELM_VERSION)
print(response.value)

if connection.status() == obd.OBDStatus.CAR_CONNECTED:
    print("I think I can, I think I can...")
    cmd = obd.commands.SPEED # select an OBD command (sensor)

    response = connection.query(cmd) # send the command, and parse the response

    print(response.value) # returns unit-bearing values thanks to Pint
    print(response.value.to("mph")) # user-friendly unit conversions

    c = obd.commands.RPM
    response = connection.query(c)
    print(response.value) # returns unit-bearing values thanks to Pint
    #print(response.value.to("rpm")) # user-friendly unit conversions

if connection.status() == obd.OBDStatus.OBD_CONNECTED:
    print("OBD_CONNECTED, ignition off")
    print(connection.supported_commands)
