# Installing obd-logger on a clean Raspberry Pi (Debian Trixie)

This guide covers setting up the OBD-II car monitoring system on a fresh
Raspberry Pi running Raspberry Pi OS based on Debian Trixie (13).

## Hardware requirements

- Raspberry Pi (Zero, 3, 4, or 5)
- [PiSugar3 battery module](https://www.pisugar.com/) attached to the Pi
- ELM327 Bluetooth OBD-II adapter (any compatible adapter — the install script
  will scan and pair with it)
- WiFi connectivity (for data sync; Home Assistant integration is optional)

## 1. Base OS setup

Flash Raspberry Pi OS (Trixie) to an SD card using
[Raspberry Pi Imager](https://www.raspberrypi.com/software/).

During imaging, configure:
- Hostname (e.g. `sensorpi1`)
- User: `trick`
- WiFi credentials
- Enable SSH

Boot the Pi and SSH in.

## 2. System packages

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y \
    bluetooth bluez \
    git git-crypt \
    python3 python3-venv python3-pip \
    moreutils \
    rsync curl \
    wireless-tools \
    i2c-tools \
    util-linux-extra
```

Package purposes:
- `bluetooth`, `bluez` — Bluetooth stack including `rfcomm` and `bluetoothctl`
- `git`, `git-crypt` — clone repo and decrypt `secret.sh`
- `python3`, `python3-venv`, `python3-pip` — Python runtime and venv support
- `moreutils` — provides the `ts` (timestamp) command used by `onboot`
- `rsync` — log sync to remote server
- `curl` — Home Assistant API calls
- `wireless-tools` — provides `iwconfig` for WiFi ESSID reporting
- `util-linux-extra` — provides `hwclock` for RTC sync

## 3. Enable I2C (for PiSugar)

```bash
sudo raspi-config
```

Navigate to: **Interface Options → I2C → Yes**

Reboot after enabling.

## 4. PiSugar setup

The `pisugar/` module talks directly to the PiSugar3 over I2C (address 0x57)
using `smbus2`. No pisugar-server daemon is needed.

Verify the PiSugar3 is visible on the I2C bus:

```bash
sudo i2cdetect -y 1
```

You should see devices at addresses `0x57` (PiSugar3 MCU) and `0x68` (DS3231 RTC).
The `smbus2` package is installed in the venv (step 8).

## 5. Configure the PiSugar RTC

The PiSugar has an onboard RTC (real-time clock) that keeps time while the Pi
is off. This is critical because the Pi is offline during drives — without the
RTC, timestamps come from `fake-hwclock` and will be wrong.

### Add the RTC overlay

Edit `/boot/firmware/config.txt` (or `/boot/config.txt` on older OS):

```bash
sudo nano /boot/firmware/config.txt
```

Add:

```
dtoverlay=i2c-rtc,ds3231
```

Reboot, then verify the kernel claimed the RTC:

```bash
sudo i2cdetect -y 1
```

You should see `UU` at address `0x68`.

### Remove fake-hwclock

`fake-hwclock` replays the last saved timestamp on boot, which conflicts with
the real RTC:

```bash
sudo apt-get -y remove fake-hwclock
sudo update-rc.d -f fake-hwclock remove
sudo systemctl disable fake-hwclock
```

### Set the RTC time

Connect to WiFi (or set manually with `sudo date -s "2026-03-08 12:00:00"`),
then write the system time to the RTC:

```bash
sudo hwclock -w    # write system time to RTC
sudo hwclock -r    # verify it reads back correctly
```

After this, every boot will initialize the system clock from the RTC
automatically — no network needed. The PiSugar's onboard battery keeps the
RTC running for over a year.

### Automatic RTC sync after NTP

The `rtc-sync.service` (installed in step 11) runs `hwclock --systohc` once
after `systemd-timesyncd` synchronizes the clock. This keeps the RTC accurate
whenever the Pi is online — no manual `hwclock -w` needed after initial setup.

## 6. Clone the repository

The systemd service and scripts expect the code at `$HOME/obd`:

```bash
cd ~
git clone https://github.com/trickv/obd-logger obd
cd obd
```

## 7. Configure sudo permissions

`obd-logger` calls `sudo rfcomm`, `sudo shutdown`, etc. without a password.
Add a sudoers rule (change `trick` to your username):

```bash
sudo visudo -f /etc/sudoers.d/obd
```

Add:
```
trick ALL=(ALL) NOPASSWD: /usr/bin/rfcomm, /usr/sbin/shutdown
```

## 8. Run the install script

The install script handles Bluetooth pairing, venv setup, OBD verification,
systemd services, and crontab in one step.

**Important:** The ELM327 adapter must be plugged into the car's OBD port
and the ignition must be ON.

```bash
cd ~/obd
./install
```

The script will:
1. Scan for Bluetooth devices and let you select your ELM327 adapter
2. Pair and trust the adapter (default PIN is `1234`)
3. Save the adapter's MAC address to `bt-addr` (this file is per-device,
   not checked into git)
4. Create a Python venv and install dependencies
5. Verify OBD communication (reads ELM version, voltage, VIN, and ECU data)
6. Install systemd services and crontab

The crontab sets up:
- Every 1 minute: `update` script (git pull, update crontab, sync data — skips if last success was <15 min ago)
- Every 1 minute: `post-to-hass` (report sensors to Home Assistant — skipped if `secret.sh` is not configured)
- Every 1 minute: `battery-check` (shut down if battery <20% and not charging)

## 9. (Optional) Home Assistant integration

The Home Assistant integration is optional and only used for debugging.
If you want it, unlock `secret.sh` with git-crypt:

```bash
git-crypt unlock /path/to/git-crypt-key
```

Or create it manually:

```bash
cat > secret.sh << 'EOF'
export hass_llac="YOUR_HOME_ASSISTANT_LONG_LIVED_ACCESS_TOKEN"
EOF
chmod 600 secret.sh
```

If `secret.sh` is absent or not decrypted, `post-to-hass` exits silently.

## 10. Verify

```bash
# Check systemd service
sudo systemctl status obd

# Check cron is loaded
crontab -l

# Test PiSugar connection
cd ~/obd
./battery.py
```

## 11. Reboot and go

```bash
sudo reboot
```

On boot, the `obd` systemd service will:
1. Bind the Bluetooth RFCOMM device
2. Start `obd-logger` which connects to the OBD-II adapter
3. Log sensor data to CSV files in `~/log/`
4. Log output to syslog (viewable with `journalctl -u obd -f`)

## Configuration reference

| File | Purpose |
|------|---------|
| `bt-addr` | ELM327 Bluetooth MAC address (created by `./install`, per-device, not in git) |
| `secret.sh` | Home Assistant API token (git-crypt encrypted, optional) |
| `crontab` | Cron schedule for updates, Home Assistant, and battery checks |
| `systemd/obd.service` | Systemd unit — update `User`/`Group` if not using `trick` |
| `systemd/rtc-sync.service` | Syncs system clock → DS3231 RTC after NTP sync |
| `systemd/pisugar-poweroff.service` | Tells PiSugar MCU to cut power at shutdown |

## Troubleshooting

**"No connection at all"** — Check that the ELM327 is powered, paired, trusted,
and that `rfcomm0` is bound (`rfcomm` with no args shows bindings).

**PiSugar I2C error** — Check that I2C is enabled (`sudo raspi-config` →
Interface Options → I2C) and that `i2cdetect -y 1` shows `0x57`.

**`pip install` fails with "externally managed environment"** — You must use
a venv (step 8). Do not use `--break-system-packages`.

**Bluetooth pairing fails** — Some ELM327 clones need the PIN set before
pairing: in `bluetoothctl`, run `agent on` and `default-agent` first.
