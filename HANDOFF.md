# Handoff

Picking this up? Read this file, then `README.md`, then `docs/00-index.md`. Everything
needed to continue is in the repository on purpose - nothing lives only in someone's
session.

**One paragraph:** an ESP32-S3 board (Guition JC3248W535, 320x480 QSPI touch panel) runs
our own MicroPython + LVGL firmware. It comes up with a visible splash, starts an
application (default: a launcher listing 8 example apps), and serves both a debug server
(MCP tools: screenshot, code execution, files, logs, LVGL tree, I2C scan, WiFi, reset)
and a web UI (console, CodeMirror editor, file manager, configuration). An unconfigured
board opens an open access point with a captive portal and a setup page where board
profile, display driver, touch driver and pins can be chosen. The firmware was built for
one chip only, so the board list is filtered by `os.uname().machine`.

## 1. State

### Done and verified on hardware

| Area | Evidence |
|------|----------|
| Display (QSPI, full-frame refresh) | `docs/03-display-bringup.md`; colour bands read back, panel visible |
| Touch | `docs/04-touch-bringup.md`; 262 points / 300 s, ~28 Hz, UI counter increments |
| Debug server + MCP tools | `docs/02-mcp-debug-server.md`; MCP registered in Hermes as `esp32` (9 tools) |
| Web UI | `docs/05-web-ui.md`; console, editor save, file listing, configuration round-trip |
| Data driven display/touch config | `/api/config` returns `board JC3248W535`, `driver axs15231b`; display initialised from `/drv/display/axs15231b` |
| Board profiles + chip filter | `/api/profiles` -> 4 profiles, all `chip: esp32s3` |
| Drivers at runtime | `/api/drivers` -> `{"display": ["axs15231b"], "touch": ["axs15231"]}` |
| Setup portal | with `config.json` removed: AP active, `192.168.4.1/24`, SSID `ESP32-Setup`, authmode open, setup-mode server started |
| Example applications | `tools/apps_smoke.py`: 8 of 8 start and render, each with its own framebuffer signature |
| Visible boot | `tools/camtext.py`: the glass shows a bright splash, then the light launcher with its blue header |
| Runtime app switch | `POST /api/app {"name":"snake"}` -> log `app_loader: started snake` -> different screen |
| Host tests | 51 + 190 + 13 + 48 + 119 checks, all green; `node --check` on both JS files |

### Not verified yet (be honest about this when you continue)

* **Nobody has touched the applications with a finger.** They build, render and their
  touch targets are >= 40x40 px, but no game was played through by hand. Test snake's
  buttons, minesweeper's dig/flag toggle, the calculator keypad and the alarm dialog on
  the real panel.
* **The captive portal was never tested from a client.** The server has no WiFi
  interface, so the redirect is only verified from the device side plus the host tests.
  Take a phone, join `ESP32-Setup` and check that the setup page pops up.
* **Only two drivers are on the device** (`axs15231b`, `axs15231`). `tools/deploy.sh drv`
  uploads all 38 display and 21 touch drivers; until then `/api/drivers` shows two.
* **The setup page's pin table has not been tried against a second panel.** Pins come
  from documentation for the JC4827W543, the Waveshare 3.5B and a CUSTOM template.
* **`/api/app` and `/api/apps`** are exercised, but the "Start application now" button
  was only checked through the API, not clicked in a browser.

## 2. Open work, in the order I would do it

1. **Finish the language sweep.** Three files still carry German comments:
   `firmware/device/drivers/axs15231b.py` (and its copy under
   `firmware/device/drv/display/axs15231b/`), `firmware/device/test_bands.py`,
   `tools/touch_probe_rst.py`. Everything else - docs, `firmware/mcpsrv/`, the web UI,
   the tests - is English.
2. **Deploy the full driver set**: `tools/deploy.sh drv` (~1 MB, several minutes over
   mpremote). Then check `/api/drivers` and the setup page's drop-downs.
3. **Verify the apps by hand** (see above). Fix what feels wrong - a game that cannot be
   played is not finished, no matter what the framebuffer says.
4. **Browser remote control of the LVGL UI** (`docs/06-lvgl-remote-control.md`). The plan
   is written and measured: P0 = poll `/screen.raw?scale=1` at ~2 fps (0.457 s/frame,
   ~2.2 fps), P1 = a second pointer `lv.indev` fed from a lock-protected queue
   (`mcp_pointer.py` + one line in `main.py`), P2 = delta rectangles from the LVGL flush
   area over a binary WebSocket on a second port (8-26 fps). Note the measured trap:
   device-side downscaling is *slower* than sending full frames (scale=4 costs 1.2 s).
5. **Light theme for the example apps** if desired. The launcher is light and there is a
   bright splash, but the games kept their own dark palettes; on the glass they look dim
   (visible, but not obviously alive).
6. **Touch calibration/limits**: the panel reports 320x480 raw coordinates with the
   driver as configured; check the edges (especially the bottom row of the launcher,
   which sits above a status label).
7. **A second board profile on hardware.** Add pins to `profiles.json` and verify; the
   failure mode is a black panel, and setup mode stays reachable because the access point
   comes up first.

## 3. Environment and hardware access

Reference machine (Debian 13, `192.168.1.90`):

| | |
|---|---|
| Board | `192.168.1.168`, port `/dev/serial/by-path/pci-0000:00:15.0-usb-0:4.4.3:1.0` (dock port 1-4.4.3) |
| Reset the board | `uhubctl -l 1-4.4 -p 3 -a cycle -d 2` (power cycles the dock port) |
| MicroPython host tool | `/opt/esp-tools/bin/python3 -m mpremote ...` (has `mpremote` and `pyserial`) |
| esptool | `/root/.espressif/python_env/idf5.5_py3.13_env/bin/python -m esptool ...` |
| MicroPython/LVGL source | `/opt/lvgl_micropython` (mainline + `SPIBusFast`); drivers under `api_drivers/common_api_drivers/` |
| Camera on the panel | `/dev/video0`, `ffmpeg -f v4l2 -i /dev/video0 -frames:v 6 -y /tmp/cam%03d.jpg` |
| Node | needed for `node --check` on the web UI's JavaScript |
| **Never touch** | `/dev/ttyACM0` = Zigbee stick (by-id `...F0:F5:BD:03:09:5C...`, port 1-3, `zigbee2mqtt.service`) |

Helper tools that save time:

| Tool | Purpose |
|------|---------|
| `tools/board.sh` | resolve the board port (refuses the Zigbee stick), ls/rm/reset/run/exec/repl |
| `tools/deploy.sh` | `mods`, `all`, `web`, `apps`, `drv`, `drv-one <name>`, `lib`, `run`, `exec`, `repl` |
| `tools/drivers.sh` | collect 38 display + 21 touch drivers from the LVGL tree into `firmware/device/drv/` |
| `tools/serial_boot.py` | read the console *across* a power cycle (reconnects through re-enumeration) |
| `tools/camtext.py` | a webcam frame as a text brightness/colour map - the only honest view of the glass |
| `tools/apps_smoke.py` | start every application on the board, check the log line and the frame |
| `tools/mcp_call.py`, `tools/mcp_shot.py`, `tools/snapshot.py` | talk to the debug server, grab screens |
| `tools/camlook.py` | crop/brighten a camera frame for a human to look at |

## 4. Safety rules

* Never address the board by an unscoped device name. Use by-id/by-path;
  `tools/board.sh` and `tools/deploy.sh` do that for you.
* No blind flashing. `mpremote` copies + power cycle are enough; esptool only for a new
  image, and then with the board's own port path.
* The debug server and web UI execute code and write files, with no authentication. They
  are meant for a trusted LAN. Setup mode is deliberately restricted to configuration
  (no `/api/exec`, no file access) because its access point is open.
* If a display configuration is wrong, the panel can stay black and a C call can block.
  The access point and the setup server come up *before* the display is touched, so the
  board stays fixable - keep that order.

## 5. Verification workflow that worked

1. **Host first**: `python3 tests/test_*.py` (5 suites) and `node --check` on the JS.
   They catch logic errors and, with a little malice (see the `os.path` test), traps that
   would otherwise only appear on the device.
2. **Deploy narrowly**: `tools/deploy.sh` with the smallest target that covers the change.
3. **Power cycle, then read the console**: `tools/serial_boot.py` - a boot that fails
   prints a traceback there instead of showing a black panel with no explanation.
4. **Ask the board**: `/status`, `/api/log`, `/api/state`, `/api/config`.
5. **Look at the glass**: `tools/camtext.py` on a fresh camera frame. A device screenshot
   is *not* proof (see lesson 6 below).
6. **Drive the thing**: `tools/apps_smoke.py` for the applications, `POST /api/app` for
   switching, `tools/camlook.py` when a human should judge the picture.

## 6. Lessons learned (short version; details in `docs/09-lessons-learned.md`)

1. **LVGL needs a fed tick.** Without `lv.tick_inc()` per loop iteration, `lv.tick_get()`
   stays 0 and `lv.timer_handler()` runs *no* timer: no touch polling, no refresh. This
   looked like a broken touch controller for hours.
2. **`enable_input_priority()` is a trap** in this binding: it switches the indev to
   EVENT mode and LVGL stops polling. Do not use it.
3. **A pin can belong to two things.** GPIO 8 was display DC *and* touch SCL; the display
   init killed the touch bus (`ETIMEDOUT`). Resolve by not driving DC (`dc=-1`) in QSPI
   mode.
4. **Full frames need a bus driver that chunks.** The SPI bus limit is 32768 bytes, a
   full frame is 307200. Without `SPIBusFast` the panel silently stays black; partial
   render also stays black with two full framebuffers configured.
5. **A timeout must not change the mode.** The board fell back into setup mode because a
   WiFi join took longer than 20 s; it then served a configuration page instead of the
   application and looked dead. Keep the mode, retry in the background.
6. **Never judge the glass from a framebuffer read.** With two full framebuffers the
   capture lags a frame, and a dead backlight is invisible to it. Use the camera
   (`tools/camtext.py`).
7. **A dark theme reads as a dead panel.** `#101820` with `#24384F` cards is lit but
   looks black on a small panel. Splash + light launcher fixed the user's complaint.
8. **Screens built before the main loop need the timers driven explicitly** - otherwise
   the *previous* frame stays on the glass (that is what `main.pump()` is for).
9. **This MicroPython has no `os.path`.** `os.path.isdir` works on CPython and raises on
   the board; detect directories by listability, and emulate a `path`-less `os` in a host
   test.
10. **`mpremote exec` resets and interrupts the running program.** Using it to inspect a
    live mode kills what you are inspecting; read the console instead.
11. **`mpremote fs cp` needs the destination directory to exist** and `fs mkdir` creates
    no parents.
12. **The device-side downscale is a Python pixel loop** and slower than sending full
    frames (scale=4: 1.2 s vs scale=1: 0.45 s). Send raw, scale in the browser.
13. **Never embed JavaScript in a Python string.** A `\n` became a real newline, the
    script broke silently and every handler disappeared. Files on disk + `node --check`.
14. **Deliver big files in chunks, and supervise the accept loop.** A 174 KB read killed
    the server's accept thread; 2 KB chunks plus a supervisor fixed it.
15. **A profile change must not be pinned by the first save.** `config.json` is a delta
    over the profile; storing the merged section made profile switching a silent no-op.
16. **Measure, do not assume.** Several "facts" here contradict intuition (a 20 s join
    timeout being too short, a *smaller* image being slower, an idle touch byte pattern
    looking like an error). Every number in the docs was measured on the board.

## 7. Git history

Commit messages carry the reasoning per change - read them with `git log` when you want
to know why something looks the way it does (the older ones are titled in German, before
the switch to English).
