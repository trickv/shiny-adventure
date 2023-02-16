#!//usr/bin/python3 -u

import time
import sys
import obd
import subprocess
import os.path
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

response = connection.query(obd.commands.ELM_VOLTAGE)
print(response.value)
response = connection.query(obd.commands.ELM_VERSION)
print(response.value)

if status == obd.OBDStatus.OBD_CONNECTED:
    print("OBD_CONNECTED, ignition off")
    response = connection.query(obd.commands.ELM_VOLTAGE)
    print(response.value)
    time.sleep(60)
    subprocess.run("./sync-data", shell=True)
    # in some version of systemd, you may be able to do:
    # sudo systemctl list-jobs shutdown.target
    # but not here on systemd 241.
    # and apparently on systemd 251, you can do:
    # shutdown --show
    # but. I'm on systemd 241 on debian buster.
    if not os.path.isfile("/run/systemd/shutdown/scheduled"):
        print("fallback: no pending shutdown, so scheduling one now.")
        subprocess.run("sudo shutdown -h +15", shell=True)
    else:
        print("already a shutdown pending! :)")
    sys.exit(42)

# looks like the car is on!
# kill any pending shutdown
subprocess.run("sudo shutdown -c", shell=True)

none_counter = 0

#while True:
for x in range(0,3600): # to avoid issues with instrumentation while car is simply off
    time.sleep(1)
    if x % 10 == 0:
        print("pisugar battery: charging={}, level={}".format(pisugar.get_charging_status().value, pisugar.get_battery_percentage().value))

    if status == obd.OBDStatus.CAR_CONNECTED:
        print("CAR_CONNECTED: I think I can, I think I can...")
        
        response = connection.query(obd.commands.SPEED)
        if response.is_null():
            none_counter += 1
        else:
            print("{}: Speed: {}".format(response.time, response.value))
        
        response = connection.query(obd.commands.RPM)
        if response.is_null():
            none_counter += 1
        else:
            print("{}: RPM: {}".format(response.time, response.value))

        if none_counter > 10:
            # the car is probably off now. close up shop.
            print("Car appears to have turned off.")
            print("pisugar charging status: {}".format(pisugar.get_charging_status().value))
            subprocess.run("./sync-data", shell=True)
            subprocess.run("sudo shutdown -h +15", shell=True)
            sys.exit(0)

# if somehow we're here, try and sync data
subprocess.run("./sync-data", shell=True)
