#!//usr/bin/python3 -u

import time
import sys
import obd
import subprocess
from pisugar import *

pisugar = PiSugar2()

if len(sys.argv) > 1 and sys.argv[1] == "prompt":
    input("OBD thingy ready. Press Enter to continue.")

obd.logger.setLevel(obd.logging.DEBUG)

for x in range(1, 50):
    print("try {}...".format(x))
    connection = obd.OBD("/dev/rfcomm0", baudrate=38400)
    if connection.status() != obd.OBDStatus.NOT_CONNECTED:
        break
    connection.close()
    time.sleep(1)

status = connection.status()

if status == obd.OBDStatus.NOT_CONNECTED:
    print("No connection at all. hrmph")
    if not pisugar.get_charging_status().value:
        print("no power, no obd.shutting down.")
        subprocess.run("sudo shutdown -h now", shell=True)
    sys.exit(1)

for x in range(0, 5):
    response = connection.query(obd.commands.ELM_VOLTAGE)
    print(response.value)
    response = connection.query(obd.commands.ELM_VERSION)
    print(response.value)
    time.sleep(1)

#while True:
for x in range(0,3600): # to avoid issues with instrumentation while car is simply off
    time.sleep(1)
    c = obd.commands.RPM
    response = connection.query(c)
    print(response.value)
    if status == obd.OBDStatus.CAR_CONNECTED:
        print("CAR_CONNECTED: I think I can, I think I can...")
        cmd = obd.commands.SPEED # select an OBD command (sensor)

        response = connection.query(cmd) # send the command, and parse the response

        print(response.value) # returns unit-bearing values thanks to Pint
        print(response.value.to("mph")) # user-friendly unit conversions

        c = obd.commands.RPM
        response = connection.query(c)
        print(response.value) # returns unit-bearing values thanks to Pint
        #print(response.value.to("rpm")) # user-friendly unit conversions
        #print(connection.supported_commands)

    if status == obd.OBDStatus.OBD_CONNECTED:
        print("OBD_CONNECTED, ignition off")
        response = connection.query(obd.commands.ELM_VOLTAGE)
        print(response.value)
        subprocess.run("./sync-data", shell=True)
        sys.exit("since ignition off, I should shutdown...TODO!")

subprocess.run("./sync-data", shell=True)
