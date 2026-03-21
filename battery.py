#!/usr/bin/env python3

from pisugar import PiSugar3

pisugar = PiSugar3()
print(f"{pisugar.get_battery_percentage().value}")
