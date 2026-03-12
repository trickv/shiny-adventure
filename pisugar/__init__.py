#!/home/trick/obd/venv/bin/python3

# PiSugar3 direct I2C interface — no pisugar-server daemon required.
#
# Reads battery status directly from the PiSugar3 MCU at I2C address 0x57.
# Register map from: https://github.com/PiSugar/PiSugar/wiki/PiSugar-3-I2C-Datasheet

from collections import namedtuple
from datetime import datetime
import smbus2

PISUGAR3_ADDR = 0x57
I2C_BUS = 1

# Registers
REG_CTR1 = 0x02
REG_CTR2 = 0x03
REG_SHUTDOWN_DELAY = 0x09
REG_WRITE_ENABLE = 0x0B
REG_VOLTAGE_H = 0x22
REG_VOLTAGE_L = 0x23
REG_PERCENTAGE = 0x2A

# CTR1 bit masks
CTR1_POWER_PLUGGED = 0x80
CTR1_OUTPUT_ENABLE = 0x20
CTR1_AUTO_POWER_ON = 0x10

# Software RTC registers (BCD encoded)
REG_RTC_YY = 0x31
REG_RTC_MM = 0x32
REG_RTC_DD = 0x33
REG_RTC_HH = 0x35
REG_RTC_MN = 0x36
REG_RTC_SS = 0x37

Result = namedtuple("PiSugar", "name value")


def _bcd_to_int(bcd):
    return (bcd >> 4) * 10 + (bcd & 0x0F)


class PiSugar3:
    """Drop-in replacement using direct I2C instead of the TCP daemon.

    PiSugar 3 only — uses the PiSugar3 MCU register map (I2C address 0x57).
    """

    def __init__(self, bus=I2C_BUS, addr=PISUGAR3_ADDR):
        self.bus = smbus2.SMBus(bus)
        self.addr = addr

    def _write_byte(self, reg, value):
        """Write a byte with the required unlock/lock sequence."""
        self.bus.write_byte_data(self.addr, REG_WRITE_ENABLE, 0x29)
        try:
            self.bus.write_byte_data(self.addr, reg, value)
        finally:
            self.bus.write_byte_data(self.addr, REG_WRITE_ENABLE, 0x00)

    def get_battery_percentage(self):
        """Returns the current battery level percentage (0-100)."""
        pct = self.bus.read_byte_data(self.addr, REG_PERCENTAGE)
        return Result(name="percentage", value=float(pct))

    def get_voltage(self):
        """Returns the current battery voltage in volts."""
        vh = self.bus.read_byte_data(self.addr, REG_VOLTAGE_H)
        vl = self.bus.read_byte_data(self.addr, REG_VOLTAGE_L)
        voltage = ((vh << 8) | vl) / 1000.0
        return Result(name="voltage", value=voltage)

    def get_charging_status(self):
        """Returns whether external power is plugged in."""
        ctr1 = self.bus.read_byte_data(self.addr, REG_CTR1)
        plugged = bool(ctr1 & CTR1_POWER_PLUGGED)
        return Result(name="charging", value=plugged)

    def get_rtc_time(self):
        """Read the software RTC time from the PiSugar3 MCU."""
        yy = _bcd_to_int(self.bus.read_byte_data(self.addr, REG_RTC_YY))
        mm = _bcd_to_int(self.bus.read_byte_data(self.addr, REG_RTC_MM))
        dd = _bcd_to_int(self.bus.read_byte_data(self.addr, REG_RTC_DD))
        hh = _bcd_to_int(self.bus.read_byte_data(self.addr, REG_RTC_HH))
        mn = _bcd_to_int(self.bus.read_byte_data(self.addr, REG_RTC_MN))
        ss = _bcd_to_int(self.bus.read_byte_data(self.addr, REG_RTC_SS))
        return Result(
            name="rtc_time",
            value=datetime(2000 + yy, mm, dd, hh, mn, ss),
        )

    def get_auto_power_on(self):
        """Check if auto power-on on external power restore is enabled."""
        ctr1 = self.bus.read_byte_data(self.addr, REG_CTR1)
        return Result(
            name="auto_power_on",
            value=bool(ctr1 & CTR1_AUTO_POWER_ON),
        )

    def set_auto_power_on(self, enabled):
        """Enable/disable auto power-on when external power is restored."""
        ctr1 = self.bus.read_byte_data(self.addr, REG_CTR1)
        if enabled:
            ctr1 |= CTR1_AUTO_POWER_ON
        else:
            ctr1 &= ~CTR1_AUTO_POWER_ON & 0xFF
        self._write_byte(REG_CTR1, ctr1)

    def poweroff(self, delay_seconds=3):
        """Tell the PiSugar MCU to cut output power after a delay.

        This is what the stock pisugar-poweroff service did at shutdown:
        set a countdown timer, then disable the 5V output. The MCU waits
        delay_seconds before actually cutting power, giving the Pi time
        to finish shutting down.
        """
        self._write_byte(REG_SHUTDOWN_DELAY, delay_seconds)
        ctr1 = self.bus.read_byte_data(self.addr, REG_CTR1)
        ctr1 &= ~CTR1_OUTPUT_ENABLE & 0xFF
        self._write_byte(REG_CTR1, ctr1)


if __name__ == "__main__":
    pisugar = PiSugar3()
    print(f"Battery:       {pisugar.get_battery_percentage().value}%")
    print(f"Voltage:       {pisugar.get_voltage().value}V")
    print(f"Charging:      {pisugar.get_charging_status().value}")
    print(f"RTC time:      {pisugar.get_rtc_time().value}")
    print(f"Auto power-on: {pisugar.get_auto_power_on().value}")
