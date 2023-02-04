#!/usr/bin/env python3

from pisugar import *

pisugar = PiSugar2()
print(f"{pisugar.get_charging_status().value}")
