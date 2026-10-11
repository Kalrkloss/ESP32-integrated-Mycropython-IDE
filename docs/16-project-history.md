# 16 - Project history and decisions

The chronological record, so a new agent knows **which paths were already walked and
abandoned** instead of re-litigating them. `git log` carries the details per change.

## Phases

1. **Analysis of the original goal.** Add USB audio (UAC) to the proprietary Annex RDS
   BASIC firmware, so BASIC programs could use a USB sound card. Result: impossible from
   the outside - no source, the licence forbids reverse engineering, and a symbol-free
   image cannot be rebuilt. Insights in [`docs/01-ausgangslage.md`-`05-feature-request-cicciocb.md`](01-ausgangslage.md).
2. **Route decision.** Own ESP-IDF firmware with a BASIC core (route B) versus own
   MicroPython + LVGL firmware (route C). Route C was favoured after the effort estimate
   ([`docs/06-micropython-route.md`](06-micropython-route.md)) - mainly because the web UI, the REPL and the display stack come almost for
   free, which is exactly what this project needed.
3. **Board access first.** A board- and port-resolution helper was written before any
   firmware work: the machine also carries a Zigbee stick, and addressing the wrong device
   would have broken a running home automation. Everything goes through by-id/by-path.
4. **Debug server before display.** The MCP server (screenshot, exec, files, logs, LVGL
   tree) was built and host-tested while the panel was still black. That investment paid
   off: every following bug was diagnosable from the device itself ([`docs/08-mcp-debug-server.md`](08-mcp-debug-server.md)).
5. **Display bring-up.** A fork build failed on `esp_tinyusb`/`tinyusb` version conflicts;
   the working `SPIBusFast` driver was transplanted into the mainline tree instead. The
   panel was verified with colour bands ([`docs/09-display-bringup.md`](09-display-bringup.md)).
6. **Touch bring-up.** The longest debugging stretch: a dead touch that turned out to be
   four separate causes (LVGL tick never fed, input-priority mode, a double-used GPIO, and
   an idle answer misread as an error). [`docs/10-touch-bringup.md`](10-touch-bringup.md) is the record.
7. **Web UI.** Console, CodeMirror editor, file manager, configuration. Two real bugs hit
   production-shaped problems: a large file killing the accept thread, and a JavaScript
   string embedded in Python ([`docs/11-weboberflaeche.md`](11-weboberflaeche.md)).
8. **Configuration, profiles, portal.** Data driven display/touch configuration, board
   profiles filtered by chip, drivers loaded at runtime from `/drv`, and an open access
   point with a captive portal for the unconfigured board ([`docs/13-configuration-and-portal.md`](13-configuration-and-portal.md)).
9. **Example applications.** Eight apps plus a loader that can switch them at runtime;
   verified by starting each on the board and comparing framebuffer signatures ([`docs/14-apps.md`](14-apps.md)).
10. **Language sweep and visible boot.** All texts to English (docs, server, web UI,
    tests), a bright splash, a light launcher, and the boot-timeout bug that had made the
    board look dead ([`docs/15-lessons-learned.md`](15-lessons-learned.md)).

## Decisions that were reversed (do not re-open them without new facts)

| Decision | Why it was changed |
|----------|--------------------|
| Build the vendor fork | It does not compile against the pinned `esp_tinyusb`; transplanting `SPIBusFast` into the mainline tree was smaller than fixing the fork |
| BASIC as the programming model | Dropped in favour of MicroPython + LVGL (web UI, REPL, ecosystem) |
| USB audio | Parked: the board has I2S audio, and the UAC work only made sense inside Annex |
| EditArea as the editor | Unmaintained since ~2012, a 115 KB monolith; CodeMirror 5.65.16 is smaller, maintained and searchable |
| Fallback into setup mode when the WiFi join timed out | It replaced the running application with a configuration page; a slow DHCP lease made a healthy board look dead |
| Dark UI theme (`#101820`) | On the panel it looked like a dead display; splash + light launcher instead |
| Downscaling screenshots on the device | The device-side pixel loop is slower than sending full frames (1.2 s vs 0.45 s) |
| `enable_input_priority()` | Switches LVGL's indev to EVENT mode and stops touch polling |
| A reset theory for the touch controller | The vendor BSP states `TOUCH_RST (-1)`; the assumption was withdrawn |

## Working rules that emerged

* Measure on the device; write the measurement into `docs/`, not into a session.
* Host-test everything that can be tested without hardware - and make the tests catch
  device-only traps (missing `os.path`, restricted routes).
* Keep the board diagnosable at every step: the debug server, the log ring, the console
  reader and the camera eye were worth their build time several times over.
* Small, reasoned commits: the message says *why*, so the history is readable later.
