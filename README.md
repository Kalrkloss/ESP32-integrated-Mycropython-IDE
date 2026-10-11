# ESP32-S3 MicroPython + LVGL firmware with an on-device debug server

Firmware for the **Guition JC3248W535** (ESP32-S3, 3.5" QSPI panel, capacitive touch)
that an agent can debug **by itself**: a debug server runs on the board, and the board
also serves a web UI (REPL, code editor, file manager, configuration), a setup access
point with a captive portal for first-time configuration, and a set of example
applications (snake, minesweeper, sokoban, calculator, clock with stopwatch and alarm,
2048, tic-tac-toe) behind a launcher.

Everything here is our own code, MIT licensed (see [LICENSE](LICENSE)); no code or
artefacts from Annex RDS.

## What this repository is not

It started as an attempt to add USB audio (UAC) to the closed-source **Annex RDS** BASIC
firmware. That path was abandoned: Annex is not open source, its licence forbids reverse
engineering, and this board has I2S audio anyway. BASIC is dropped, USB audio is parked.
Documents 01-06 record that investigation - read them as history, do not resume that
route.

## Hardware

| | |
|---|---|
| Board | Guition JC3248W535, ESP32-S3 N16R8, 3.5" 320x480 QSPI panel, capacitive touch |
| Firmware | MicroPython 1.27 + LVGL 9, built with `lvgl_micropython` (mainline + `SPIBusFast`) |
| Board in the reference setup | `http://192.168.1.168/` |
| Debug server | `http://192.168.1.168/mcp` (MCP over HTTP) and `/status` (plain text) |
| Web UI | console, CodeMirror editor, file manager, configuration |
| Setup portal | unconfigured board: open AP `ESP32-Setup`, page at `http://192.168.4.1/` |

## Repository layout

```
firmware/device/     board side application
  main.py            boot: display, touch, splash, application, server, main loop
  boot.py            WiFi: connect as station, or open the setup access point
  display_config.py  data driven bus/display/touch setup (profile + config.json)
  portal.py          setup mode: access point, DNS hijack, captive portal redirect
  app_loader.py      starts applications from /apps, switches them at runtime
  profiles.json      board profiles (only profiles for this firmware's chip are offered)
  drv/               display and touch drivers, deployed to /drv on the device
  drivers/           our patched drivers (they win over the vendored copies)
  webfiles/          web UI: HTML/CSS/JS + vendored CodeMirror 5.65.16
  apps/              example applications (launcher, games, calculator, clock)
firmware/mcpsrv/     debug server: MCP protocol, HTTP server, tools, screen, PNG, web API
tools/               deploy, board/port resolution, measurement and verification helpers
tests/               host tests (CPython, no hardware)
docs/                design and bring-up documentation (English); see docs/00-index.md
```

## Quick start

Host side, no hardware needed:

```sh
python3 tests/test_mcpsrv.py    # MCP protocol, PNG encoder      (51 checks)
python3 tests/test_webui.py     # web UI, API, configuration     (190 checks)
python3 tests/test_boot.py      # credential merge rules          (13 checks)
python3 tests/test_portal.py    # DNS hijack, captive portal      (48 checks)
python3 tests/test_apps.py      # applications and loader        (119 checks)
```

Device side (reference setup; see `HANDOFF.md` for the machine specifics):

```sh
tools/board.sh ls               # which port is the board (never the Zigbee stick)
tools/deploy.sh all             # server modules, web UI, device files, apps, boot.py
tools/deploy.sh drv             # every display/touch driver to /drv (~1 MB)
tools/serial_boot.py 35 3       # read the console across a power cycle
python3 tools/apps_smoke.py     # start every application on the board and check it
python3 tools/camtext.py        # what the panel really shows (webcam frame as text)
```

Reset the board with `uhubctl -l 1-4.4 -p 3 -a cycle -d 2` (dock port 3).

## Safety rules on this machine

* **Never touch `/dev/ttyACM0`** - that is the Zigbee stick (by-id
  `...F0:F5:BD:03:09:5C...`, port 1-3, held open by `zigbee2mqtt.service`). Always
  address the board through its by-id/by-path name; `tools/board.sh` and
  `tools/deploy.sh` resolve the port and refuse anything else.
* No blind flashing: `mpremote` file copies plus a power cycle are enough. A full
  esptool flash is only needed for a new MicroPython image.
* The web UI and the debug server have **no authentication** (they execute code and
  write files). They belong in a trusted, isolated LAN. Setup mode is the one case that
  is locked down to configuration only, because its access point is open.

## Documentation

[`docs/00-index.md`](docs/00-index.md) lists every document with a one-line summary.
Picking the project up? Start with [`HANDOFF.md`](HANDOFF.md) - state, open work,
environment, lessons learned.
