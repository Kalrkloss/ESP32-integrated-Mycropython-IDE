# Way C: MicroPython + LVGL as the basis for an "Annex-like" system

Question: how much effort is it to build, on the basis of MicroPython + LVGL, a firmware with
web server, WebREPL, web editor and config page for various boards and
custom display/pin configuration?

Short answer: considerably less than a custom BASIC interpreter, because a large part of the
system already exists. Effortful remain exactly those parts that Annex also built
itself: web editor UI, config UI, board/display matrix and the USB audio driver.

Status of the examined building blocks: 2026-10-10.

## What MicroPython brings (no effort)

| Building block | Source | Note |
|---|---|---|
| REPL over UART **and** native USB | esp32 port | on the S3 as a USB-Serial-JTAG console |
| WebREPL (REPL in the browser + file transfer) | `webrepl` module, in the standard build | `webrepl.html` is delivered by the device; password protection built in |
| File system, `os`, frozen bytecode, `mip` (package manager) | MicroPython core | Annex has its own file/OTA logic for this |
| WLAN, sockets, TLS, `asyncio`, `_thread` (real FreeRTOS tasks) | MicroPython core | `_thread` is the reason why "hook in a task" works **here**: we own the build |
| Board system with variants for flash size/PSRAM | `ports/esp32/boards/*`, `mpconfigboard.cmake`, `pins.csv` | incl. `ESP32_GENERIC_S3` with `SPIRAM_OCT` |
| LVGL bindings + display drivers | <https://github.com/lvgl/lv_micropython> | `lvgl` module in Python, `lcd_bus`, `task_handler` |
| Licenses | MicroPython MIT, LVGL MIT, Microdot MIT, ViperIDE MIT, Espressif components Apache-2.0 | no license problem — unlike with Annex |

Effort for the skeleton on the S3: **under one day** (IDF v5.5.5 + MicroPython,
`make BOARD=ESP32_GENERIC_S3 BOARD_VARIANT=SPIRAM_OCT`).

## What one must build oneself (estimate, full time, one person)

| Building block | Effort | Note |
|---|---|---|
| Web server + config page (WLAN scan/connect, pin assignment, module/panel selection, restart, safe mode); config as JSON in flash | 3–6 days | [Microdot](https://github.com/miguelgrinberg/microdot) (Flask-like, async, MIT) covers routing, WebSocket and auth |
| Web editor | 1–3 days with [ViperIDE](https://github.com/vshymanskyy/ViperIDE) (MIT, connects via WebREPL/USB, file manager + package manager + terminal); built oneself: 7–12 days | the editor is the largest single item if one writes it oneself |
| LVGL build + first display (SPI-TFT + touch), memory tuning | 3–7 days | PSRAM practically mandatory |
| each further board variant | 0.5–2 days per definition | pins, `sdkconfig`, flash/PSRAM variant, deploy guide |
| RGB/parallel panels, further panel types | 3–8 days per panel type | panel timings, `esp_lcd`, PSRAM wiring |
| Runtime configuration of displays (one image for many panels) | 5–10 days | panel timings and bus as data instead of compile-time constant — Annex does **not** do this, there a separate firmware is flashed per module |
| **USB audio (UAC host) as a C module** | 4–8 days | own module around `espressif/usb_host_uac`: ring buffer, task, I2S/DAC output, Python API `uac.play()`/`uac.rec()` |
| OTA, recovery, release packaging, docs | 3–6 days | |
| **Total until "usable"** (1 board, 1 display, 1 sound card) | **4–7 weeks** | |
| Additionally for the variant diversity à la Annex | + weeks, predominantly panel/board work | Annex' matrix emerged over years |

The numbers are rules of thumb for the amount of work, not measured values. They contain
no hardware iterations (board revisions, timing problems) — by experience those cost the most
with displays.

## Comparison of the ways

| | Way B: own BASIC interpreter | Way C: MicroPython + LVGL |
|---|---|---|
| Interpreter/REPL/FS/drivers | write yourself (weeks) | present |
| Language for user programs | BASIC (Annex programs run) | Python (Annex programs do **not** run) |
| Web editor | build yourself | ViperIDE present |
| LVGL | C, direct, fast | via bindings, slower |
| RAM requirement | lower | higher (PSRAM needed) |
| USB audio | write yourself | write yourself (same effort) |
| Conclusion | more work, full control, close to Annex | less work, Python ecosystem, more sluggish with GUIs |

## Pitfalls

1. **PHY sharing on the S3.** USB-OTG and USB-Serial-JTAG share one PHY: as long as
   USB host runs (i.e. the sound card), USB debug/flash is gone. Debug then via UART,
   or an external PHY (SP5301 / TUSB1106) per datasheet. Directly relevant for the
   USB audio goal.
2. **PSRAM is mandatory** for LVGL + web server + TLS. Plan for an S3 with 8 MB PSRAM.
3. **Performance:** LVGL via Python bindings is noticeably slower than Annex's C path;
   a compromise for elaborate GUIs.
4. **WebREPL is unencrypted** (`ws`, password protection present) — operate only on the LAN,
   do not expose to the internet. Annex' web UI has its own auth logic here.
5. **Firmware size** with LVGL: ~4 MB, thus a 16 MB flash module.
6. **Modifying foreign firmware afterwards** remains impossible — this way delivers a
   *own* firmware. The advantage over Annex: here one may hook in C modules.

## Recommended milestones

- **M1** Build MicroPython for `ESP32_GENERIC_S3`/`SPIRAM_OCT`, flash, open WebREPL in the
  browser and transfer a file. (verifiable in one day)
- **M2** Config page with Microdot: WLAN, pins, module/panel selection, config in flash.
- **M3** Use ViperIDE over WebREPL as editor (no own editor needed).
- **M4** LVGL on a TFT (SPI + touch), PSRAM tuning.
- **M5** USB audio C module (`usb_host_uac`) + Python API + I2S/DAC output.
- **M6** OTA, recovery, release packages, docs.
