# Documentation index

Read `HANDOFF.md` in the repository root first: it carries the current state, the open
work and the lessons learned. This index only says what each document contains.

## Documents

| File | Content |
|------|---------|
| [`01-board-jc3248w535.md`](01-board-jc3248w535.md) | Board reference: pins, peripherals, manufacturer material, port and power-cycle wiring |
| [`02-mcp-debug-server.md`](02-mcp-debug-server.md) | The debug server: MCP tools, HTTP routes, screen capture, logging ring |
| [`03-display-bringup.md`](03-display-bringup.md) | Panel bring-up: bus limits, full-frame refresh, why `SPIBusFast` is required, colour checks |
| [`04-touch-bringup.md`](04-touch-bringup.md) | Why the touch was dead and what fixed it (LVGL tick, input-priority trap, GPIO 8 collision, idle byte patterns) |
| [`05-web-ui.md`](05-web-ui.md) | The web UI: console, CodeMirror editor, file manager, configuration; chunked delivery, screenshot path |
| [`06-lvgl-remote-control.md`](06-lvgl-remote-control.md) | Study: showing and operating the LVGL UI live in the browser (transport comparison, measured throughput, pointer injection, staged plan P0-P2) |
| [`07-configuration-and-portal.md`](07-configuration-and-portal.md) | Board profiles, data driven display/touch configuration, drivers loaded at runtime, setup access point with captive portal, the setup page, verification and pitfalls |
| [`08-apps.md`](08-apps.md) | The example applications, their contract, the loader, how to choose and switch applications, how to deploy and verify them |
| [`09-lessons-learned.md`](09-lessons-learned.md) | Every rule that cost time, with the symptom, the cause and the measurement - read this before debugging |
| [`10-lvgl-design.md`](10-lvgl-design.md) | The design system: tokens in `_ui.py`, widget anatomy, contrast, fonts in `lv_conf.h`, and the off-device preview loop that renders a screen to a PNG |

## Reading order for a new agent

1. `HANDOFF.md` - state, open work, environment, safety rules, lessons.
2. `README.md` - layout, quick start, hardware.
3. `01` (board), `03`/`04` (display and touch bring-up - where the traps are).
4. `07` (configuration, profiles, portal), `08` (applications), `10` (design tokens and
   the preview loop before touching any screen).
5. `02` (debug server) and `05` (web UI) as needed.
6. `06` for the next planned feature (browser remote control).
