# IMU Data Dashboard

A single-file browser dashboard that reads a six-axis IMU stream from an ESP32 over
**Web Bluetooth** and plots it live. BLE only — no Wi-Fi, no backend, no build step,
no dependencies.

```
web-imu-data-rx/
├── index.html                        the dashboard
├── start.bat                         serves it and opens a browser
├── README.md
└── sample-imu-data/
    ├── sample-imu-data.ino           the ESP32 firmware
    └── env.h                         BLE device name
```

## Run it

Double-click **`start.bat`**. It serves the folder on <http://localhost:8000> and opens the
page in Chrome or Edge. The server lives in a minimised *"imu-dashboard server"* window —
close that window to stop it.

Or by hand:

```bash
cd web-imu-data-rx
python -m http.server 8000
```

Two things the launcher handles for you:

- **`file://` will not work.** Web Bluetooth requires a secure context; localhost counts as
  one, opening `index.html` directly does not.
- **The browser matters.** Firefox and Safari do not implement Web Bluetooth at all, and
  **Brave ships it disabled** — if Brave is your default, either use Chrome/Edge or enable
  `brave://flags/#brave-web-bluetooth-api` first. The page says so up front when the API is
  missing rather than failing silently at Connect.

## Flash the board

Open `sample-imu-data/sample-imu-data.ino` in the Arduino IDE.

- **Board:** ESP32-S3 (the sketch drives the onboard RGB LED on GPIO 48).
- **Library:** *MPU6050_light* by rfetick. BLE ships with the ESP32 core.
- Change the advertised name in `env.h` if you like — the dashboard finds the board by its
  service UUID, not by name.

Keep the board still for the first two seconds after reset; it calibrates the gyro then.

| LED | Meaning |
| :-- | :-- |
| Red, blinking | MPU6050 init failed — check I²C wiring |
| Blue, 2 blinks then steady | Calibrating gyro, keep still |
| Green, 3 blinks | Calibration done, or a client just connected |
| Purple, blinking | Advertising, ready to connect |
| Off | Connected and streaming |

## Connecting

1. Power the board and wait for the **blinking purple** LED.
2. Press **Add device…** and pick `test letGo device` from the browser's chooser. You do this
   once per board; it then stays in the dropdown across reloads.
3. Press **Connect**. The board blinks green three times.

Only one central can hold the board at a time.

### About the dropdown

The browser gives a page **no API to scan for nearby devices** — choosing one always goes
through the chooser dialog that `requestDevice()` opens, and that is a deliberate security
boundary, not something a page can work around. So the dropdown lists devices you have
already granted this page access to, read back via `navigator.bluetooth.getDevices()`, and
**Add device…** is how a new one gets in. The last-connected device is remembered in
`localStorage` and re-selected automatically.

On builds where `getDevices()` is gated behind
`chrome://flags/#enable-web-bluetooth-new-permissions-backend`, the dropdown still works but
only remembers devices added during the current page session.

The chooser filters on the Nordic UART service UUID, so any board running this sketch appears
whatever you named it. Tick **Show all nearby devices** to drop the filter entirely.

## Wire format

One newline-terminated CSV line per sample at `FREQUENCY_HZ = 100`, starting 100 ms after the
central connects:

```
ax,ay,az,gx,gy,gz\n
```

| Field | Units | Notes |
|-------|-------|-------|
| `ax, ay, az` | g | MPU6050, 2 decimals, offsets from `FACTORY_ACC_*` |
| `gx, gy, gz` | deg/s | MPU6050, 2 decimals, gyro auto-calibrated at boot |

## What's on screen

- **Accelerometer (g)** fixed −2.0 … 2.0 and **Gyroscope (deg/s)** fixed −400 … 400, over a
  200-sample window, X/Y/Z in `#FF5252` / `#448AFF` / `#69F0AE`.
- **Tiles** with the six current values and the measured frame rate.

At 100 Hz the raw numbers change far faster than anyone can read them, so **the tiles are
smoothed**: they refresh every 120 ms, and each shows a mean of the newest ~12 samples with a
light exponential filter on top, so the figure eases rather than strobing. The **charts stay
raw** — that is where the actual signal lives, and smoothing them would hide real motion.
Tune `TILE_MS`, `AVG_N` and `TILE_EMA` at the top of the script if you want it calmer or
snappier.

## Changes made to the sketch

The original streamer worked but had a few things worth correcting:

- **The service UUID was never advertised.** Without `addServiceUUID()` the Nordic UART UUID
  is not in the advertisement packet, so a central can only match on the device name — and
  Web Bluetooth cannot filter on the service at all. Now advertised, which is why the chooser
  filters by service. A 128-bit UUID plus the device name exceeds the 31-byte advertisement,
  so the name rides in the scan response; the ESP32 core moves it there automatically while
  scan response is enabled.
- **The MTU was left at the default 23**, leaving 20 bytes of payload for a ~40-byte frame, so
  every single frame was split across two notifications. Now requests 128.
- **The connection interval was 20–40 ms** (`updateConnParams(..., 0x10, 0x20, ...)`), which
  cannot carry 100 notifications a second — the stream quietly ran well below `FREQUENCY_HZ`.
  Now asks for 7.5–15 ms. The central may still refuse; the Rate tile shows what actually
  arrives.
- **`String` concatenation in the hot loop** built seven temporary Strings per frame, 100
  times a second, fragmenting the heap over a long session. Now `snprintf` into a fixed
  buffer.
- **`while(1);` on sensor-init failure** starves the task watchdog, so the board reboots and
  hides the real fault. Now blinks red indefinitely instead.
- `deviceConnected` is written from the BLE callback task and read from `loop()`, so it is
  `volatile`.
- Dropped the unused RX characteristic define — nothing is ever written to the board.

The receiver reassembles notifications through a line buffer regardless, since MTU negotiation
is up to the central. Lines that arrive truncated fail the six-field check and are dropped
rather than plotted as garbage.

## Known limits

- Chrome/Edge only; Web Bluetooth on Linux also needs
  `chrome://flags/#enable-experimental-web-platform-features`.
- Viewer only — it does not record.
