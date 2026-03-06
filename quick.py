#!/home/trick/obd/venv/bin/python3 -u

import csv
import os
import os.path
import subprocess
import sys
import time
from datetime import datetime

import obd
from pisugar import PiSugar2

# Sensors to log when the car is running.
# Each entry is (obd command, csv column name).
# Not all cars support all sensors — unsupported ones are silently skipped.
SENSORS = [
    (obd.commands.RPM, "rpm"),
    (obd.commands.SPEED, "speed_kmh"),
    (obd.commands.COOLANT_TEMP, "coolant_temp_c"),
    (obd.commands.ENGINE_LOAD, "engine_load_pct"),
    (obd.commands.THROTTLE_POS, "throttle_pct"),
    (obd.commands.INTAKE_TEMP, "intake_temp_c"),
    (obd.commands.MAF, "maf_gps"),
    (obd.commands.TIMING_ADVANCE, "timing_advance_deg"),
    (obd.commands.FUEL_LEVEL, "fuel_level_pct"),
    (obd.commands.RUN_TIME, "run_time_sec"),
    (obd.commands.BAROMETRIC_PRESSURE, "baro_kpa"),
    (obd.commands.ELM_VOLTAGE, "elm_voltage"),
]

LOG_DIR = os.path.expanduser("~/log")

pisugar = PiSugar2()

if len(sys.argv) > 1 and sys.argv[1] == "prompt":
    input("OBD thingy ready. Press Enter to continue.")

obd.logger.setLevel(obd.logging.DEBUG)

for attempt in range(1, 50):
    print(f"try {attempt}...")
    connection = obd.OBD("/dev/rfcomm0", baudrate=38400)
    if connection.status() != obd.OBDStatus.NOT_CONNECTED:
        break
    connection.close()
    time.sleep(1)

status = connection.status()

if status == obd.OBDStatus.NOT_CONNECTED:
    print("No connection at all. hrmph")
    if not pisugar.get_charging_status().value:
        print("no power, no obd. shutting down.")
        subprocess.run(["sudo", "shutdown", "-h", "now"])
    sys.exit(1)

response = connection.query(obd.commands.ELM_VOLTAGE)
print(f"ELM voltage: {response.value}")
response = connection.query(obd.commands.ELM_VERSION)
print(f"ELM version: {response.value}")

# Print which sensors the car supports
supported = connection.supported_commands
print(f"Car supports {len(supported)} commands")
for cmd, col in SENSORS:
    tag = "OK" if cmd in supported else "not supported"
    print(f"  {col}: {tag}")


DTC_CHECK_INTERVAL = 300  # re-check DTCs every 5 minutes


def check_dtcs(connection):
    """Query and log diagnostic trouble codes."""
    os.makedirs(LOG_DIR, exist_ok=True)
    dtc_path = os.path.join(LOG_DIR, "dtc.log")

    status_resp = connection.query(obd.commands.STATUS)
    if not status_resp.is_null():
        mil = status_resp.value.MIL
        dtc_count = status_resp.value.DTC_count
        print(f"MIL (check engine): {mil}, DTC count: {dtc_count}")
    else:
        mil = None
        dtc_count = None
        print("Could not read STATUS")

    dtc_resp = connection.query(obd.commands.GET_DTC)
    if not dtc_resp.is_null() and dtc_resp.value:
        now = datetime.now().isoformat()
        print(f"DTCs found: {len(dtc_resp.value)}")
        with open(dtc_path, "a") as f:
            for code, desc in dtc_resp.value:
                line = f"{now}  {code}  {desc}"
                print(f"  DTC: {code} - {desc}")
                f.write(line + "\n")
    else:
        print("No DTCs")

    freeze_resp = connection.query(obd.commands.FREEZE_DTC)
    if not freeze_resp.is_null() and freeze_resp.value:
        print(f"Freeze frame DTC: {freeze_resp.value}")

    return mil, dtc_count


def is_shutdown_pending():
    result = subprocess.run(["sudo", "shutdown", "--show"],
                            capture_output=True, text=True)
    return result.returncode == 0 and "Shutdown scheduled" in result.stdout


def schedule_shutdown_if_needed():
    subprocess.run(["./sync-data"])
    if not is_shutdown_pending():
        print("no pending shutdown, scheduling one in 15 minutes.")
        subprocess.run(["sudo", "shutdown", "-h", "+15"])
    else:
        print("already a shutdown pending!")


# Check DTCs on connect
check_dtcs(connection)

if status == obd.OBDStatus.OBD_CONNECTED:
    print("OBD_CONNECTED, ignition off")
    response = connection.query(obd.commands.ELM_VOLTAGE)
    print(f"ELM voltage: {response.value}")
    time.sleep(60)
    schedule_shutdown_if_needed()
    sys.exit(42)

# Car is on — cancel any pending shutdown
subprocess.run(["sudo", "shutdown", "-c"], capture_output=True)

# Set up CSV logging
os.makedirs(LOG_DIR, exist_ok=True)
csv_path = os.path.join(LOG_DIR, f"obd-{datetime.now():%Y%m%d-%H%M%S}.csv")
csv_file = open(csv_path, "w", newline="")
csv_columns = ["timestamp"] + [col for _, col in SENSORS] + ["pisugar_charging", "pisugar_battery_pct"]
csv_writer = csv.DictWriter(csv_file, fieldnames=csv_columns)
csv_writer.writeheader()
print(f"Logging to {csv_path}")

# Filter to only supported sensors
active_sensors = [(cmd, col) for cmd, col in SENSORS if cmd in supported]

consecutive_nulls = 0
NULL_THRESHOLD = 10

for x in range(0, 3600):
    time.sleep(1)

    row = {"timestamp": datetime.now().isoformat()}
    got_data = False

    for cmd, col in active_sensors:
        response = connection.query(cmd)
        if not response.is_null():
            val = response.value
            row[col] = val.magnitude if hasattr(val, 'magnitude') else val
            got_data = True

    if x % 10 == 0:
        charging = pisugar.get_charging_status().value
        battery = pisugar.get_battery_percentage().value
        row["pisugar_charging"] = charging
        row["pisugar_battery_pct"] = battery
        print(f"pisugar: charging={charging}, level={battery}")

    if got_data:
        consecutive_nulls = 0
        if x % 5 == 0:
            rpm = row.get("rpm", "?")
            speed = row.get("speed_kmh", "?")
            coolant = row.get("coolant_temp_c", "?")
            print(f"RPM={rpm} Speed={speed} Coolant={coolant}")
    else:
        consecutive_nulls += 1

    csv_writer.writerow(row)

    if consecutive_nulls > NULL_THRESHOLD:
        print("Car appears to have turned off.")
        print(f"pisugar charging: {pisugar.get_charging_status().value}")
        csv_file.close()
        schedule_shutdown_if_needed()
        sys.exit(0)

    # Re-check DTCs periodically
    if x > 0 and x % DTC_CHECK_INTERVAL == 0:
        check_dtcs(connection)

    # Flush CSV periodically so data isn't lost on unclean exit
    if x % 30 == 0:
        csv_file.flush()

csv_file.close()
# If we exit the loop (1 hour timeout), sync data
subprocess.run(["./sync-data"])
