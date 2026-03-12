# Installing obd-logger on a clean Raspberry Pi (Debian Trixie)

This guide covers setting up the OBD-II car monitoring system on a fresh
Raspberry Pi running Raspberry Pi OS based on Debian Trixie (13).

## Hardware requirements

- Raspberry Pi (Zero, 3, 4, or 5)
- [PiSugar2 battery module](https://www.pisugar.com/) attached to the Pi
- ELM327 Bluetooth OBD-II adapter (this project uses MAC `00:1D:A5:03:62:B2` —
  update `id` file if yours differs)
- WiFi connectivity (for Home Assistant reporting and data sync)

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
    i2c-tools
```

Package purposes:
- `bluetooth`, `bluez` — Bluetooth stack including `rfcomm` and `bluetoothctl`
- `git`, `git-crypt` — clone repo and decrypt `secret.sh`
- `python3`, `python3-venv`, `python3-pip` — Python runtime and venv support
- `moreutils` — provides the `ts` (timestamp) command used by `onboot`
- `rsync` — log sync to remote server
- `curl` — Home Assistant API calls
- `wireless-tools` — provides `iwconfig` for WiFi ESSID reporting

## 3. Enable I2C (for PiSugar)

```bash
sudo raspi-config
```

Navigate to: **Interface Options → I2C → Yes**

Reboot after enabling.

## 4. Install PiSugar Power Manager

The PiSugar daemon listens on TCP port 8423 and is required by `quick.py` and
the battery scripts.

```bash
wget https://cdn.pisugar.com/release/pisugar-power-manager.sh
bash pisugar-power-manager.sh -c release
```

Select the correct PiSugar model when prompted. Verify it's running:

```bash
sudo systemctl status pisugar-server
```

You can also check the web UI at `http://<pi-ip>:8421`.

## 5. Clone the repository

The systemd service and scripts expect the code at `$HOME/obd`:

```bash
cd ~
git clone https://github.com/trickv/obd-logger obd
cd obd
```

## 6. Unlock secrets with git-crypt

`secret.sh` contains the Home Assistant API token and is encrypted with
git-crypt. You need the symmetric key to unlock it:

```bash
git-crypt unlock /path/to/git-crypt-key
```

If you don't have the key file, you'll need to recreate `secret.sh` manually:

```bash
cat > secret.sh << 'EOF'
export hass_llac="YOUR_HOME_ASSISTANT_LONG_LIVED_ACCESS_TOKEN"
EOF
chmod 600 secret.sh
```

## 7. Python virtual environment

Debian Trixie enforces PEP 668 — you cannot `pip install` into the system
Python. Use a venv:

```bash
cd ~/obd
python3 -m venv venv
source venv/bin/activate
pip install obd
```

All Python scripts have shebangs pointing at `~/obd/venv/bin/python3`, so the
venv is used automatically — no need to activate it before running scripts.

## 8. Pair the ELM327 Bluetooth adapter

Power on the ELM327 adapter (plug it into the car's OBD port and turn the
ignition to ON).

```bash
bluetoothctl
```

Inside bluetoothctl:
```
power on
agent on
default-agent
scan on
```

Wait for the ELM327 MAC to appear (should match the address in the `id` file:
`00:1D:A5:03:62:B2`). Then:

```
pair 00:1D:A5:03:62:B2
trust 00:1D:A5:03:62:B2
exit
```

The default PIN for most ELM327 adapters is `1234`.

## 9. Configure sudo permissions

`quick.py` calls `sudo rfcomm`, `sudo shutdown`, etc. without a password.
Add a sudoers rule:

```bash
sudo visudo -f /etc/sudoers.d/obd
```

Add:
```
trick ALL=(ALL) NOPASSWD: /usr/bin/rfcomm, /usr/sbin/shutdown
```

## 10. Create the log directory

```bash
mkdir -p ~/log
```

## 11. Install the systemd service

```bash
cd ~/obd
./systemd/install
```

This copies `obd.service` to `/etc/systemd/system/`, reloads systemd, and
enables the service to start on boot.

## 12. Install the crontab

```bash
crontab ~/obd/crontab
```

This sets up:
- Every 30 minutes: `ci` script (git pull, update crontab, sync data)
- Every 1 minute: `post-to-hass` (report sensors to Home Assistant)
- On boot: both scripts with appropriate delays

## 13. Verify

```bash
# Check systemd service
sudo systemctl status obd

# Check cron is loaded
crontab -l

# Test PiSugar connection
cd ~/obd
./battery.py

# Test Bluetooth RFCOMM binding (car must be on)
sudo rfcomm bind rfcomm0 $(cat ~/obd/id)
ls -l /dev/rfcomm0
```

## 14. Reboot and go

```bash
sudo reboot
```

On boot, the `obd` systemd service will:
1. Bind the Bluetooth RFCOMM device
2. Start `quick.py` which connects to the OBD-II adapter
3. Log sensor data to CSV files in `~/log/`
4. Log output to syslog (viewable with `journalctl -u obd -f`)

## Configuration reference

| File | Purpose |
|------|---------|
| `id` | ELM327 Bluetooth MAC address — update if your adapter differs |
| `secret.sh` | Home Assistant API token (git-crypt encrypted) |
| `crontab` | Cron schedule for CI and Home Assistant updates |
| `systemd/obd.service` | Systemd unit — update `User`/`Group` if not using `trick` |

## Troubleshooting

**"No connection at all"** — Check that the ELM327 is powered, paired, trusted,
and that `rfcomm0` is bound (`rfcomm` with no args shows bindings).

**PiSugar connection refused** — Ensure `pisugar-server` is running:
`sudo systemctl restart pisugar-server`

**`pip install` fails with "externally managed environment"** — You must use
a venv (step 7). Do not use `--break-system-packages`.

**Bluetooth pairing fails** — Some ELM327 clones need the PIN set before
pairing: in `bluetoothctl`, run `agent on` and `default-agent` first.
