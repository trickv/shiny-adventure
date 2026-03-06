#!/home/trick/obd/venv/bin/python3

from pisugar import PiSugar2

pisugar = PiSugar2()
print(f"{pisugar.get_charging_status().value}")
