# 13 - Configuration, board profiles and captive portal

An unconfigured board must be reachable without a cable and without knowing its IP.
This document describes how that works: an open access point with a captive portal,
the setup page behind it, the data driven display/touch configuration and the
runtime driver lookup.

## 1. Why

A new board starts with no WiFi credentials. Without a fallback it is only reachable
over the serial console, so the first configuration would need a laptop with
mpremote and the right port -- the exact situation this project exists to avoid.

The requirement was: show a selection of known boards, let the user pick one, then let
them adjust display driver, touch driver and pin assignment. Two constraints shaped the
result:

* **One chip per firmware image.** A MicroPython build is compiled for exactly one
  ESP32 type, so a board offering other chips would be lying. The profile list is
  therefore filtered by `os.uname().machine` (e.g. `ESP32S3`) -- only boards with
  `chip == esp32s3` are offered by an S3 image (`display_config.chip_name`).
* **No rebuild for a different panel.** Display and touch drivers live as Python
  files on the device and are imported at runtime, so changing a driver is a
  configuration change, not a build.

## 2. Boot flow

`boot.py` runs before `main.py`:

1. Read credentials: `config.json` (written by the web UI) wins, `wifi.json` is the
   legacy location and only fills empty fields.
2. Configured (`configured` flag set **and** an SSID present) -> connect as station.
3. Not configured -> `portal.SETUP_MODE = True` and open the access point.
4. Configured but the join does **not** finish within 45 s -> stay in normal mode!
   `boot.py` only sets `portal.STA_RETRY`; `main.py` retries the join every 15 s from
   its main loop. Falling back to setup mode here was a mistake: a slow DHCP lease
   then replaced the running application with a configuration page and restricted the
   web UI, which looked exactly like a dead board with a black display.

A wrong SSID or password therefore needs a cable (or a corrected `wifi.json`); the
access point is reserved for a board that is really unconfigured.

`main.py` then branches on `portal.SETUP_MODE`: in setup mode it starts the DNS
hijack and a **restricted** server (see section 5) and shows a hint on the panel;
otherwise it builds display, touch, a bright splash, the configured application and
the full debug server.

Order inside setup mode matters: access point, DNS and server first, the display
last. A wrong display configuration can block inside a C call, and the user must
still be able to reach the setup page to correct it.

### Visible screen at boot

Every boot draws a bright splash (`show_splash`) for ~0.7 s and then the configured
application; `launcher` uses a light theme. Reason: a dark application theme on a
small panel is easily mistaken for a dead display, which is what happened here. The
splash runs `main.pump()`, which drives `lv.tick_inc`/`lv.timer_handler` explicitly --
a screen drawn before the main loop starts is otherwise not flushed to the panel.

## 3. Data model

`profiles.json` (shipped with the firmware) holds board profiles: pins, drivers,
resolution. `config.json` (on the device, not in the repo) is the **delta** on top
of the selected profile:

```
effective = DEFAULT_DISPLAY <- profile.display <- config.json.display
```

* Values stored in `config.json` always win -- that is what the setup page writes
  when the user reviews the fields.
* Fields that were never stored keep coming from the profile, so switching profiles
  later really changes the pins.
* `getattr`-style merging is field by field, not section by section; storing the
  whole merged section would pin the first profile forever and make a later profile
  change silently do nothing (that bug existed and is covered by a test).
* WiFi password: needed on the device, never sent to the browser. The API returns
  `password_gesetzt` instead, and an empty password field never deletes a stored one.
* `brightness` is accepted both as `display.brightness` (current) and as a top level
  field (the older UI wrote it there).

## 4. Drivers at runtime

Driver files live on the device under:

```
/drv/display/<name>/<name>.py     (a package may hold several files)
/drv/indev/<name>.py
```

`display_config.import_driver(kind, name)` puts that directory on `sys.path` and
imports the module by name. The filesystem takes precedence over frozen modules, so
the patched copy of a driver wins over the one compiled into the image.
`driver_class(module)` finds the driver class by name (case insensitively), which is
why `driver: axs15231b` finds the class `AXS15231B`.

`tools/drivers.sh` collects the upstream drivers plus our patched files from
`/opt/lvgl_micropython/api_drivers/common_api_drivers/` into `firmware/device/drv/`
(38 display, 21 touch, ~940 KB) and `tools/deploy.sh drv` copies them to the board
(`drv-one <name>` for a single driver).

`available_drivers()` lists what is actually present on the device, which is what
the setup page offers. A driver listed but missing on the device would only fail at
boot, so the list is derived from the file system, never hard coded.

## 5. Setup mode: open access point, captive portal

* `network.WLAN(AP_IF)`, open (no authmode password), `192.168.4.1/24`,
  SSID `ESP32-Setup` (configurable as `ap_ssid`/`ap_password`).
* DNS hijack on UDP/53 in a thread: every A query is answered with `192.168.4.1`,
  other record types get a valid answer with zero records so clients fall back to
  normal resolution. Queries are rejected if they are responses, too short, or if
  the name field is malformed -- malformed input must never crash the thread.
* Every HTTP path that is not a setup route is answered with `302 -> /setup`
  (captive portal). The route table is matched exactly first, so the catch-all
  prefix route (`GET *`, empty prefix) never shadows a real endpoint.

The access point is **open**, therefore setup mode serves configuration only:

| Allowed in setup mode      | Not served in setup mode            |
|----------------------------|-------------------------------------|
| `/`, `/setup`, `/setup.js` | `/mcp` (MCP debug tools)            |
| `/app.css`, `/favicon.ico` | `/api/exec` (code execution)        |
| `/api/config` (GET/POST)   | `/api/file`, `/api/files` (files)   |
| `/api/profiles`, `/api/drivers`, `/api/state`, `/api/log`, `/api/reset` | `/editor/*` |

Anything else -- including `/api/exec` and `/api/files` -- lands on the redirect
handler instead of the real one. The full UI has no authentication either; it is a
debug tool for a trusted, isolated LAN, and setup mode is the one case where that
trust does not hold.

## 6. Setup page

`setup.html` + `setup.js` (no CDN, shared `app.css`), four sections: network, board,
display and touch, save.

* `GET /api/profiles` returns the profiles for this chip plus the current
  configuration; `GET /api/drivers` returns the drivers present on the device.
* The form is rendered from a field list (key, label, type) so adding a field is a
  one line change; types cover int, bool, pin list, enumerations and driver lists.
* Picking a board fills the display and touch fields from the profile, so the user
  sees and can correct every pin before saving.
* "Save and restart" writes the configuration and calls `/api/reset`; a note says
  the board comes back on the configured network.
* The main UI's configuration tab (reachable in normal mode) offers SSID, hostname,
  brightness, board profile and application; both write the same `config.json`.

## 7. Verified

Host tests (`python3 tests/...`, CPython, no hardware):

| Test             | Checks | Content                                                        |
|------------------|--------|----------------------------------------------------------------|
| `test_webui.py`  | 190    | page structure, routes, API, configuration, setup page, files  |
| `test_mcpsrv.py` | 51     | MCP protocol, PNG encoder, screen buffer                       |
| `test_portal.py` | 48     | DNS answer construction, probe detection, redirect, setup mode |
| `test_boot.py`   | 13     | credential merge rules, setup-mode decision                    |

Device (JC3248W535, measured over the network and the serial console):

* Normal mode after the change: display initialised from `/drv/display/axs15231b`,
  touch ok, demo screen, server on port 80, `/api/config` returns the profile based
  configuration (`board JC3248W535`, `driver axs15231b`, `brightness 65`).
* `/api/profiles` -> 4 profiles, all `chip: esp32s3` (JC3248W535, JC4827W543,
  Waveshare ESP32-S3-Touch-LCD-3.5B, CUSTOM).
* `/api/drivers` -> `{"display": ["axs15231b"], "touch": ["axs15231"], "chip": "esp32s3"}`.
* `/setup` 200 with 2717 bytes, `/setup.js` 200 with 7742 bytes.
* With `config.json` removed: access point active, `192.168.4.1/24`, SSID
  `ESP32-Setup`, `authmode 0` (open), station not connected, and the setup-mode
  server started (proved by `main: setup hint shown`, which runs only after
  `mcp_serve.start(setup_only=True)` returned).

Not verified here: a real client (phone/laptop) being redirected by the portal. The
server has no WiFi interface, so the client side could not be reproduced; the
redirect itself is covered by the host tests and by the route table on the device.

## 8. Pitfalls (paid for once already)

* **Predrawn screens need `main.pump()`.** A screen built before the main loop runs
  (both the splash and the application) is flushed only when something drives LVGL's
  timers; without it the panel keeps the previous frame.
* **`/screen.raw` can be one frame behind the glass.** With two full framebuffers the
  capture reads the buffer that `mcp_screen` attached to, while the panel shows the
  other one. Never judge the glass from the raw buffer alone: `tools/camtext.py`
  renders a webcam frame of the panel as a text brightness/colour map, which is the
  reliable check (and the only one that also catches a dead backlight).
* **A slow WiFi join must not change the mode.** See section 2: falling back to setup
  mode on a timeout turned a running board into a configuration portal and looked like
  a black display.
* **A dark theme reads as a dead panel.** The first launcher version used `#101820`
  with `#24384F` cards; measured through the camera the panel was lit but visually
  black. Splash + light launcher fixed it.
* **MicroPython has no `os.path` in this build.** `os.path.isdir` worked on the host
  and raised `AttributeError: 'module' object has no attribute 'path'` on the board.
  `available_drivers()` now recognises a directory by listability, and the host test
  emulates an `os` module without `path`.
* **`mpremote exec` resets and interrupts the running program.** Probing a running
  mode with it kills what is being probed: a setup-mode server looked "not listening"
  because mpremote had stopped it. To watch a boot, read the console:
  `python3 tools/serial_boot.py 35 3` (power cycles the dock port while reading, and
  reconnects across the USB re-enumeration).
* **`mpremote fs cp` needs the destination directory to exist**, and `fs mkdir` does
  not create parents. `tools/deploy.sh drv-one` creates `:drv`, `:drv/display` and
  `:drv/indev` before copying.
* **`config.json` must stay a delta** (section 3): storing the merged section makes
  profile switching a no-op.
* **The device cannot reach its own access point address.** Connecting from the board
  to `192.168.4.1:80` gives `ECONNRESET` without a station connection -- a routing
  artefact of LwIP, not a server fault.
* **Reading the CDC port does not reset the S3**, but the power cycle does, and the
  board re-enumerates: the boot messages of the first ~2 s are only visible if the
  console is read without a reset in between.

## 9. Open

* Deploy the full driver set (`tools/deploy.sh drv`) so the setup page offers all
  38 display and 21 touch drivers.
* Switching the display/touch driver currently needs a restart. A runtime switch
  (tear down the bus, re-create the driver, rebuild the UI) has to go through the
  request queue in `main.py`, exactly like screen captures do.
* Board profiles for other S3 panels: add an entry to `profiles.json`, pins from the
  panel documentation, and verify on the hardware. A wrong pin can put the panel into
  boot mode -- setup mode stays reachable because the access point comes up first.
