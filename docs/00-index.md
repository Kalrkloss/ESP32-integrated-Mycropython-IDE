# Documentation index

Read `HANDOFF.md` in the repository root first: it carries the current state, the open
work and the lessons learned. This index only says what each document contains.

## Current work (the board runs MicroPython + LVGL, not BASIC)

| File | Content |
|------|---------|
| [`13-configuration-and-portal.md`](13-configuration-and-portal.md) | Board profiles, data driven display/touch configuration, drivers loaded at runtime, setup access point with captive portal, the setup page, verification and pitfalls |
| [`14-apps.md`](14-apps.md) | The example applications, their contract, the loader, how to choose and switch applications, how to deploy and verify them |
| [`15-lessons-learned.md`](15-lessons-learned.md) | Every rule that cost time, with the symptom, the cause and the measurement - read this before debugging |
| [`16-project-history.md`](16-project-history.md) | The chronological record, the decisions, and the ones that were reversed (so they are not re-opened) |
| [`12-lvgl-fernbedienung.md`](12-lvgl-fernbedienung.md) | Study: showing and operating the LVGL UI live in the browser (transport comparison, measured throughput, pointer injection, staged plan P0-P2) |
| [`11-weboberflaeche.md`](11-weboberflaeche.md) | The web UI: console, CodeMirror editor, file manager, configuration; chunked delivery, screenshot path |
| [`10-touch-bringup.md`](10-touch-bringup.md) | Why the touch was dead and what fixed it (LVGL tick, input-priority trap, GPIO 8 collision, idle byte patterns) |
| [`09-display-bringup.md`](09-display-bringup.md) | Panel bring-up: bus limits, full-frame refresh, why `SPIBusFast` is required, colour checks |
| [`08-mcp-debug-server.md`](08-mcp-debug-server.md) | The debug server: MCP tools, HTTP routes, screen capture, logging ring |
| [`07-board-jc3248w535.md`](07-board-jc3248w535.md) | Board reference: pins, peripherals, manufacturer material, port and power-cycle wiring |

## History (the abandoned BASIC / USB-audio route)

These document the original goal (USB audio inside the closed-source Annex firmware) and
the decision to drop it. They are useful for the reasoning and the sources, **not** as a
task list - do not resume that route.

| File | Content |
|------|---------|
| [`01-ausgangslage.md`](01-ausgangslage.md) | Initial situation, why a rebuilt Annex is not possible |
| [`02-plan.md`](02-plan.md) | Original plan and milestones |
| [`03-command-surface.md`](03-command-surface.md) | The BASIC command surface that was to be implemented |
| [`04-einhaengen-in-fremde-firmware.md`](04-einhaengen-in-fremde-firmware.md) | Study: hooking a FreeRTOS task into foreign firmware |
| [`05-feature-request-cicciocb.md`](05-feature-request-cicciocb.md) | Draft feature request to the Annex author |
| [`06-micropython-route.md`](06-micropython-route.md) | Effort estimate and the decision for MicroPython + LVGL |

## Reading order for a new agent

1. `HANDOFF.md` - state, open work, environment, safety rules, lessons.
2. `README.md` - layout, quick start, hardware.
3. `07` (board), `09`/`10` (display/touch bring-up - where the traps are).
4. `13` (configuration, profiles, portal), `14` (applications).
5. `08` (debug server) and `11` (web UI) as needed.
6. `12` for the next planned feature (browser remote control).
