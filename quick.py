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
    job = subprocess.run("sudo systemctl list-jobs shutdown.target", shell=True, capture_output=True, encoding='utf-8')
    print(job.stdout)
    if job.stdout.find("No jobs running") >= 0:
        print("fallback: no pending shutdown, so scheduling one now.")
        subprocess.run("sudo shutdown -h +15", shell=True)
    sys.exit(42)

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
            print("{}: Speed: {}".format(response.time.isoformat(), response.value))
        
        response = connection.query(obd.commands.RPM)
        if response.is_null():
            none_counter += 1
        else:
            print("{}: RPM: {}".format(response.time.isoformat(), response.value))

        if none_counter > 10:
            # the car is probably off now. close up shop.
            print("pisugar charging status: {}".format(pisugar.get_charging_status().value))
            subprocess.run("./sync-data", shell=True)
            subprocess.run("sudo shutdown -h +15", shell=True)
            sys.exit(0)

# if somehow we're here, try and sync data
subprocess.run("./sync-data", shell=True)
