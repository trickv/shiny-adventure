#!/home/trick/obd/venv/bin/python3 -u

import csv
import json
import os
import os.path
import subprocess
import sys
import time
import traceback
from datetime import datetime

import obd
from pisugar import PiSugar2

# ECU sensors — these only return data when the ignition is on.
# Used for car-on/off detection.
ECU_SENSORS = [
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
]
# Adapter sensors — always return data regardless of ignition state.
# Logged but NOT used for car-on/off detection.
ADAPTER_SENSORS = [
    (obd.commands.ELM_VOLTAGE, "elm_voltage"),
]
ALL_SENSORS = ECU_SENSORS + ADAPTER_SENSORS

LOG_DIR = os.path.expanduser("~/log")
os.makedirs(LOG_DIR, exist_ok=True)

# Persistent event log — one append-only JSONL file that captures every
# state transition, error, and operational event. Synced alongside the CSVs
# so post-mortem analysis is possible even after weird sequences like
# car-off → shutdown-scheduled → car-back-on-30-seconds-later.
EVENT_LOG_PATH = os.path.join(LOG_DIR, "events.jsonl")


def log_event(event, **kwargs):
    """Append a structured event to the event log and print it."""
    entry = {"ts": datetime.now().isoformat(), "event": event, **kwargs}
    line = json.dumps(entry)
    print(f"EVENT: {line}")
    with open(EVENT_LOG_PATH, "a") as f:
        f.write(line + "\n")


DTC_CHECK_INTERVAL = 300  # re-check DTCs every 5 minutes


def check_dtcs(connection):
    """Query and log diagnostic trouble codes."""
    dtc_path = os.path.join(LOG_DIR, "dtc.log")

    status_resp = connection.query(obd.commands.STATUS)
    if not status_resp.is_null():
        mil = status_resp.value.MIL
        dtc_count = status_resp.value.DTC_count
        log_event("dtc_status", mil=mil, dtc_count=dtc_count)
    else:
        mil = None
        dtc_count = None
        log_event("dtc_status_failed")

    dtc_resp = connection.query(obd.commands.GET_DTC)
    codes = []
    if not dtc_resp.is_null() and dtc_resp.value:
        now = datetime.now().isoformat()
        with open(dtc_path, "a") as f:
            for code, desc in dtc_resp.value:
                codes.append({"code": code, "desc": desc})
                print(f"  DTC: {code} - {desc}")
                f.write(f"{now}  {code}  {desc}\n")
        log_event("dtc_codes", codes=codes)
    else:
        log_event("dtc_codes", codes=[])

    freeze_resp = connection.query(obd.commands.FREEZE_DTC)
    if not freeze_resp.is_null() and freeze_resp.value:
        log_event("dtc_freeze_frame", value=str(freeze_resp.value))

    return mil, dtc_count


def is_shutdown_pending():
    result = subprocess.run(["sudo", "shutdown", "--show"],
                            capture_output=True, text=True)
    return result.returncode == 0 and "Shutdown scheduled" in result.stdout


def schedule_shutdown_if_needed():
    subprocess.run(["./sync-data"])
    if not is_shutdown_pending():
        log_event("shutdown_scheduled", delay_min=15)
        subprocess.run(["sudo", "shutdown", "-h", "+15"])
    else:
        log_event("shutdown_already_pending")


# --- main ---

csv_file = None

try:
    log_event("startup", argv=sys.argv, pid=os.getpid())

    pisugar = PiSugar2()
    log_event("pisugar_connected")

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
    log_event("obd_connected", status=str(status), attempts=attempt)

    if status == obd.OBDStatus.NOT_CONNECTED:
        charging = pisugar.get_charging_status().value
        log_event("no_connection", pisugar_charging=charging)
        if not charging:
            log_event("shutdown_no_power")
            subprocess.run(["sudo", "shutdown", "-h", "now"])
        sys.exit(1)

    response = connection.query(obd.commands.ELM_VOLTAGE)
    elm_voltage = str(response.value)
    response = connection.query(obd.commands.ELM_VERSION)
    elm_version = str(response.value)
    log_event("elm_info", voltage=elm_voltage, version=elm_version)

    # Log which sensors the car supports
    supported = connection.supported_commands
    sensor_support = {}
    for cmd, col in ALL_SENSORS:
        sensor_support[col] = cmd in supported
    log_event("sensor_support", total_supported=len(supported), sensors=sensor_support)

    # Check DTCs on connect
    check_dtcs(connection)

    if status == obd.OBDStatus.OBD_CONNECTED:
        log_event("ignition_off")
        response = connection.query(obd.commands.ELM_VOLTAGE)
        log_event("elm_voltage_idle", voltage=str(response.value))
        time.sleep(60)
        schedule_shutdown_if_needed()
        sys.exit(42)

    # Car is on — cancel any pending shutdown
    log_event("car_on")
    was_pending = is_shutdown_pending()
    subprocess.run(["sudo", "shutdown", "-c"], capture_output=True)
    if was_pending:
        log_event("shutdown_cancelled")

    # Set up CSV logging
    csv_path = os.path.join(LOG_DIR, f"obd-{datetime.now():%Y%m%d-%H%M%S}.csv")
    csv_file = open(csv_path, "w", newline="")
    csv_columns = ["timestamp"] + [col for _, col in ALL_SENSORS] + ["pisugar_charging", "pisugar_battery_pct"]
    csv_writer = csv.DictWriter(csv_file, fieldnames=csv_columns)
    csv_writer.writeheader()
    log_event("csv_logging_started", path=csv_path)

    # Filter to only supported sensors
    active_ecu_sensors = [(cmd, col) for cmd, col in ECU_SENSORS if cmd in supported]
    active_adapter_sensors = [(cmd, col) for cmd, col in ADAPTER_SENSORS if cmd in supported]

    consecutive_nulls = 0
    NULL_THRESHOLD = 10
    rows_written = 0
    loop_start = time.monotonic()
    MAX_LOOP_SECONDS = 3600
    last_pisugar_check = 0
    last_dtc_check = 0
    last_status_print = 0

    while True:
        now_mono = time.monotonic()
        elapsed = now_mono - loop_start

        if elapsed > MAX_LOOP_SECONDS:
            break

        time.sleep(1)

        row = {"timestamp": datetime.now().isoformat()}

        # Query ECU sensors — these determine car-on/off
        ecu_got_data = False
        for cmd, col in active_ecu_sensors:
            response = connection.query(cmd)
            if not response.is_null():
                val = response.value
                row[col] = val.magnitude if hasattr(val, 'magnitude') else val
                ecu_got_data = True

        # Query adapter sensors — always respond, don't affect car-on/off
        for cmd, col in active_adapter_sensors:
            response = connection.query(cmd)
            if not response.is_null():
                val = response.value
                row[col] = val.magnitude if hasattr(val, 'magnitude') else val

        if now_mono - last_pisugar_check >= 10:
            charging = pisugar.get_charging_status().value
            battery = pisugar.get_battery_percentage().value
            row["pisugar_charging"] = charging
            row["pisugar_battery_pct"] = battery
            print(f"pisugar: charging={charging}, level={battery}")
            last_pisugar_check = now_mono

        if ecu_got_data:
            consecutive_nulls = 0
            if now_mono - last_status_print >= 5:
                rpm = row.get("rpm", "?")
                speed = row.get("speed_kmh", "?")
                coolant = row.get("coolant_temp_c", "?")
                print(f"RPM={rpm} Speed={speed} Coolant={coolant}")
                last_status_print = now_mono
        else:
            consecutive_nulls += 1

        csv_writer.writerow(row)
        rows_written += 1

        if consecutive_nulls > NULL_THRESHOLD:
            log_event("car_off_detected", consecutive_nulls=consecutive_nulls,
                      rows_written=rows_written,
                      elapsed_sec=round(elapsed))
            csv_file.close()
            csv_file = None
            schedule_shutdown_if_needed()
            sys.exit(0)

        # Re-check DTCs periodically
        if now_mono - last_dtc_check >= DTC_CHECK_INTERVAL:
            check_dtcs(connection)
            last_dtc_check = now_mono

        # Flush CSV periodically so data isn't lost on unclean exit
        if rows_written % 30 == 0:
            csv_file.flush()

    log_event("loop_timeout", rows_written=rows_written,
              elapsed_sec=round(time.monotonic() - loop_start))
    csv_file.close()
    csv_file = None
    subprocess.run(["./sync-data"])

except SystemExit:
    raise
except Exception:
    log_event("crash", traceback=traceback.format_exc())
    raise
finally:
    if csv_file and not csv_file.closed:
        csv_file.flush()
        csv_file.close()
    log_event("exit", code=getattr(sys, 'exitcode', None))
