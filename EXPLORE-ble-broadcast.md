# Exploration: BLE Broadcast of Live OBD Metrics + React Native App

## Current Architecture

The Pi runs `obd-logger`, polling 13 ECU sensors + 1 adapter sensor every ~1 second
via Bluetooth Classic (RFCOMM) to an ELM327 OBD-II adapter. Data lands in CSV files.
A `coolant-display` script already tails the CSV to show live coolant temp on a terminal.

## The Challenge: Bluetooth Conflict

**This is the biggest issue.** The Pi's Bluetooth is already occupied talking to the
ELM327 adapter over Bluetooth Classic (RFCOMM). BLE and Classic share the same radio
on most Pi models, but they *can* coexist — the Pi's Bluetooth chipset supports
dual-mode (BR/EDR + BLE) simultaneously.

However, there are practical concerns:
- **Pi Zero W/WH**: BCM43438 — dual-mode supported but limited bandwidth
- **Pi Zero 2 W**: BCM43436s — dual-mode supported
- **Pi 3/4/5**: All support dual-mode

So BLE advertising *while* maintaining an RFCOMM connection to the ELM327 should work,
but would need testing for interference/timing issues since the OBD polling loop is
already timing-sensitive.

## Option A: BLE GATT Server (on the Pi)

The Pi would run a BLE peripheral (GATT server) advertising a custom service with
characteristics for each sensor reading.

### How it would work
1. `obd-logger` writes sensor data as it does now
2. A separate process (or thread in obd-logger) runs a BLE GATT server
3. The GATT server exposes characteristics like:
   - `RPM` (uint16)
   - `Speed` (uint16, km/h × 10 for one decimal)
   - `Coolant Temp` (int8, °C)
   - `Throttle` (uint8, %)
   - `MPG` (uint16, × 10)
   - etc.
4. Phone connects and subscribes to notifications (push updates every 1s)

### Python libraries
- **`bless`** — Python BLE peripheral library (cross-platform, works on Linux/BlueZ)
- **`dbus-next`** + raw BlueZ D-Bus API — more control, more complexity
- **Direct `bluetoothctl`/`hciconfig`** — advertising only, no GATT

### Data feed options
- **In-process (thread):** Add a BLE thread to `obd-logger` that reads from a shared
  dict. Simplest, tightest coupling. The `row` dict at line ~265 has everything needed.
- **File-based (like coolant-display):** Separate process tails the CSV. Adds ~1-30s
  latency (CSV flushes every 30 rows). Could be reduced by flushing every row.
- **Shared memory / Unix socket:** New IPC between obd-logger and a BLE server process.
  Clean separation but more moving parts.

### GATT Service Design
```
Service: OBD Live Data (custom 128-bit UUID)
├── Characteristic: RPM              (notify, read) — uint16
├── Characteristic: Speed            (notify, read) — uint16 (km/h × 10)
├── Characteristic: Coolant Temp     (notify, read) — int16 (°C × 10)
├── Characteristic: Engine Load      (notify, read) — uint8 (%)
├── Characteristic: Throttle         (notify, read) — uint8 (%)
├── Characteristic: Fuel Level       (notify, read) — uint8 (%)
├── Characteristic: MPG              (notify, read) — uint16 (× 10)
├── Characteristic: ELM Voltage      (notify, read) — uint16 (mV)
├── Characteristic: All Sensors Pack (notify, read) — packed binary blob
└── Characteristic: Drive Status     (notify, read) — uint8 (0=off, 1=on)
```

A single packed characteristic would be more efficient than many individual ones
(fewer BLE round-trips). A 30-byte struct could hold all 13 sensors.

## Option B: WiFi Instead of BLE

Worth considering as an alternative:
- Pi runs a simple WebSocket server
- Phone connects over WiFi (Pi as AP or both on same network)
- Lower latency, higher bandwidth, no Bluetooth conflict
- **But:** Pi is typically offline during drives (no WiFi), would need to run as AP

This is arguably simpler but requires the Pi to run as a WiFi access point while
driving, which is additional configuration and power draw.

## Option C: BLE Advertising Only (No Connection)

Instead of a GATT server, broadcast data in the BLE advertising payload:
- Up to 31 bytes in legacy advertising, 254 bytes in extended
- Encode key metrics in manufacturer-specific data
- Phone scans for advertisements passively (no connection needed)
- Lower power, simpler, but one-way and limited payload
- Multiple phones could receive simultaneously without connection management

## React Native Companion App

### Libraries
- **`react-native-ble-plx`** — most popular BLE library for React Native
- **`react-native-ble-manager`** — alternative, also well-maintained

### App Architecture
```
┌─────────────────────────────────────────────┐
│  React Native App                           │
│                                             │
│  ┌─────────────┐  ┌──────────────────────┐  │
│  │ BLE Manager │  │ State Management     │  │
│  │             │──│ (Context or Zustand) │  │
│  │ - scan      │  │                      │  │
│  │ - connect   │  │ { rpm, speed, ...  } │  │
│  │ - subscribe │  │                      │  │
│  └─────────────┘  └──────┬───────────────┘  │
│                          │                  │
│  ┌───────────────────────┴───────────────┐  │
│  │           UI Components               │  │
│  │                                       │  │
│  │  ┌─────────┐ ┌──────┐ ┌───────────┐  │  │
│  │  │ Gauges  │ │ MPG  │ │ Coolant   │  │  │
│  │  │ (RPM,   │ │ Live │ │ Temp Bar  │  │  │
│  │  │  Speed) │ │      │ │           │  │  │
│  │  └─────────┘ └──────┘ └───────────┘  │  │
│  │                                       │  │
│  │  ┌──────────────────────────────────┐ │  │
│  │  │  DTC / Check Engine Indicator    │ │  │
│  │  └──────────────────────────────────┘ │  │
│  └───────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

### Gauge Libraries
- **`react-native-svg`** + custom gauge components
- **`victory-native`** — charting library with gauge support
- **`react-native-circular-progress`** — for RPM/speed dials

### Screens
1. **Scan/Connect** — find the Pi, show connection status
2. **Dashboard** — live gauges (RPM, speed, coolant, MPG)
3. **Detail View** — all 13 sensors in a list/grid
4. **DTC View** — check engine status and codes (would need additional BLE characteristic)

## Effort Estimate

| Component | Complexity | Notes |
|-----------|-----------|-------|
| BLE GATT server on Pi | Medium | `bless` library, ~200 lines Python |
| IPC (obd-logger → BLE server) | Low-Medium | Shared dict (thread) or Unix socket |
| React Native app scaffold | Medium | Expo or bare RN, BLE permissions |
| BLE connection/subscription | Medium | Platform-specific BLE quirks |
| Dashboard UI with gauges | Medium-High | Custom SVG gauges, animations |
| Testing BLE dual-mode | Unknown | May have timing issues with OBD polling |

## Risks & Open Questions

1. **Bluetooth contention**: Will BLE GATT notifications interfere with the RFCOMM
   OBD polling? The 1-second poll loop is already tight (~300-400ms per poll).
   Testing needed.

2. **iOS background BLE**: iOS is restrictive about background BLE — the app would
   need to stay in foreground, or use background modes (which Apple scrutinizes).

3. **Range**: BLE range in a car is fine (< 5 meters), but metal/interference
   could be an issue depending on Pi placement.

4. **Power**: Running a BLE GATT server adds modest power draw. The PiSugar3
   battery is already managing tight power budgets (shutdown at 20%).

5. **Security**: Should the BLE service require pairing/bonding? For an in-car
   display it's probably fine without, but someone nearby could read your RPM.

## Recommendation

**Option A (GATT server) with in-process threading** is the most practical:
- Add a BLE thread to `obd-logger` that reads from the existing `row` dict
- Use `bless` library for the GATT server
- Pack all sensors into a single notification characteristic (efficient, simple)
- React Native app with `react-native-ble-plx` for the phone side
- Start with a minimal dashboard (RPM, speed, coolant, MPG) and expand

The existing `coolant-display` proves the "live display" concept works. BLE just
replaces "tail the CSV on the Pi's terminal" with "push over radio to a phone."
