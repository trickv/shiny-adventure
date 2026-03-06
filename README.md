# obd-logger

A Raspberry Pi-based OBD-II data logger that runs in your car. It connects to
an ELM327 Bluetooth adapter, logs sensor data to CSV files, and reports status
to Home Assistant.

## What it does

- Reads vehicle sensors (RPM, speed, coolant temp, throttle, fuel level, and
  more) via OBD-II and logs them to timestamped CSV files
- Monitors a PiSugar2 battery backup and reports charging status
- Detects when the car turns off and schedules a clean Pi shutdown
- Posts sensor data to a Home Assistant instance every minute
- Syncs logs to a remote server over rsync

## Hardware

- Raspberry Pi with Raspberry Pi OS (Trixie)
- PiSugar2 battery module (keeps the Pi alive briefly after the car turns off)
- ELM327 Bluetooth OBD-II adapter

## Setup

See [INSTALL.md](INSTALL.md) for full installation instructions.
