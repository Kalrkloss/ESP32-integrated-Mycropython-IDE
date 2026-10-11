# 15 - Lessons learned

Every rule here cost time on this board. They are written as rules with the reason and
the measurement, so the next person can recognise the *symptom* rather than having to
rediscover the cause. Values were measured on the JC3248W535 unless noted.

## Display bring-up

| Symptom | Cause | Rule |
|---------|-------|------|
| Panel stays black, no error | A full frame (307200 B) exceeds the SPI bus limit (32768 B) | Use a bus driver that chunks large transfers (`lcd_bus.SPIBusFast`); otherwise the panel silently shows nothing |
| Panel stays black with two full framebuffers | Partial render is active while full frames are configured | Either full-frame render *with* the chunking bus driver, or partial render without full framebuffers - not a mix |
| Colours look wrong, "bands" appear that are not there | Judging colours from a webcam frame (auto exposure, white balance) | Read colours from the framebuffer (`/screen.raw`) or use a test pattern; the camera is for *whether* something is visible, not for *which* colour |

* The bus limit is 32768 B, the frame is 320x480x2 = 307200 B, so the frame has to be
  sent in pieces (30720 B = 48 lines).
* The panel is RGB565 with `rgb565_byte_swap=True`. `/screen.raw` returns the framebuffer
  bytes; read them **big endian** to get the colour on the glass
  (`(raw[i] << 8) | raw[i+1]`).
* `dc=-1` in QSPI mode: the data/command line is unused there, and GPIO 8 - which the
  vendor uses as touch SCL - must not be driven by the display.

## Touch bring-up

| Symptom | Cause | Rule |
|---------|-------|------|
| Touch "dead", driver never reads | `lv.tick_get()` stayed 0, so `lv.timer_handler()` ran no timer at all | Feed the tick every loop iteration: `lv.tick_inc(time.ticks_diff(now, last))` |
| Touch dead after switching input priority on | `enable_input_priority()` sets the indev to `INDEV_MODE_EVENT`; LVGL stops polling and the replacement timer failed silently in a `try/except pass` | Do not call `enable_input_priority()` in this binding |
| Touch dead, `ETIMEDOUT` on the I2C bus | GPIO 8 was display DC *and* touch SCL; the display init left the bus unusable | Give a pin to one peripheral; `dc=-1` |
| Raw reads look like an error (`85...` before the first touch, `42...` after) | That is the **idle answer** of this controller (byte 1 = number of points; the vendor discards `> 1`) | Do not treat it as a fault; check `_get_coords` counts instead |
| "Touch in reset" theory | Vendor BSP says `TOUCH_RST (-1)` and `TOUCH_INT (-1)`; GPIO 12 is the SD clock | Read the vendor BSP before inventing a reset theory |

* Verified afterwards: 262 touch points in 300 s (~28 Hz), the UI counter increments.
* Use the `i2c` module (`i2c.I2C.Bus` / `i2c.I2C.Device`) - a raw `machine.I2C` fails with
  "I2C operation not supported". Port 0, 400 kHz, address `0x3B`, 8 bit.

## Boot, WiFi and the setup portal

| Symptom | Cause | Rule |
|---------|-------|------|
| Board looks dead after a power cycle, display black, still pingable | The WiFi join took longer than the 20 s timeout, so `boot.py` fell back into setup mode and served the configuration page instead of the application | A timeout must **not** change the mode: stay normal, retry the join from the main loop (`portal.STA_RETRY`, every 15 s). Fallback to the portal only when the board is really unconfigured |
| LED/portal "web UI" behaves strangely, `/status` returns a redirect | The setup-mode route table is restricted (configuration only) and every unknown path redirects to `/setup` | If a request redirects to `192.168.4.1/setup`, the board is in setup mode - read `/api/log` (allowed there) before touching anything |
| Changing the board profile has no effect on the pins | `config.json` was written by merging the full display section, which then always won over the profile | Store only what the caller sent; keep `config.json` a delta over the profile |
| Setup page offers a driver that does not exist | The list was hard coded | Derive the selection lists from the file system (`/drv/display/*`, `/drv/indev/*.py`) |
| The board cannot reach its own access point address | Connecting from the device to `192.168.4.1:80` gives `ECONNRESET` (LwIP routing, no station route) | Test the portal from a client or on the host; it is not a server fault |

* Credential rule: `config.json` wins, the legacy `wifi.json` only fills empty fields -
  identical in `boot.py` and the web UI, so both see the same effective configuration.
* "Configured" means: the `configured` flag is set **and** an SSID is present.
* Setup mode order matters: access point, DNS hijack and server first, display last. A
  wrong display configuration can block in a C call; the user must still be able to fix
  it in the browser.
* DNS hijack: answer A queries with the board address, other record types with a valid
  zero-record answer, and reject responses/truncated/malformed packets instead of
  crashing the thread. Detect a captive-portal probe by path or by a `Host` that is not
  the AP address and not `.local`.

## The web UI

| Symptom | Cause | Rule |
|---------|-------|------|
| Page loads, no button works, `x is not defined` | The JavaScript was embedded in a Python string; `\n` became a real newline and broke the script | Keep HTML/CSS/JS as real files on the device, and run `node --check` in the test suite |
| Server stops answering during a large file read (the accept thread dies) | A 174 KB read in one piece | Deliver in 2 KB chunks, and supervise the accept loop so it restarts |
| A route with a `*` never matched | The comparison prefix kept the `*` | Strip it: `k_prefix = k_prefix[:-1]` |
| Preview is slower at a smaller scale | The device-side downscale is a Python pixel loop | Send full frames and scale in the browser (0.45 s vs 1.2 s for scale=4) |

* No CDN: CodeMirror 5.65.16 is vendored on the board (9 files, MIT), so the UI works
  without internet access.
* The UI and the debug server have no authentication and execute code - trusted LAN only.
* Setup mode serves a restricted table (no `/api/exec`, no file access) plus a catch-all
  redirect; `/api/log` stays available for diagnosis.

## The device's own limits

* **No `os.path` in this MicroPython build.** `os.path.isdir` works on CPython and raises
  `AttributeError: 'module' object has no attribute 'path'` on the board. Detect a
  directory by listability. The host test emulates an `os` without `path` so the trap
  cannot come back.
* **`mpremote exec` soft-resets and interrupts the running program.** Do not use it to
  inspect a live mode - read the console instead (`tools/serial_boot.py`). Reading the
  USB CDC port alone does *not* reset an S3; the power cycle does.
* **`mpremote fs cp <file> :dir/` needs `dir` to exist**, and `fs mkdir` creates no
  parents.
* **Internal SRAM is the scarce resource** (~32 KB free), PSRAM has megabytes. Put large
  buffers (framebuffers, send buffers) in PSRAM and reuse them.
* `uptime_s` from the debug server is not a reliable "since boot" value - do not use it to
  decide whether a reset happened. Use the log ring: it is cleared by a boot.

## Verification and process

* **Never judge the glass from a framebuffer read.** Two full framebuffers make the
  capture lag one frame, and a dead backlight looks exactly like black content. Use the
  camera and reduce the frame to text (`tools/camtext.py`): a lit dark screen and an
  unlit panel are easy to tell apart that way.
* **A screen built before the main loop runs is not flushed.** Drive the LVGL timers
  explicitly (`main.pump()`), otherwise the previous frame stays on the glass.
* **A dark theme reads as a dead panel.** The first launcher (`#101820`, cards
  `#24384F`) was lit but looked black. Post a bright splash at every boot and keep the
  default screen light.
* **Host tests first, and make them catch device-only traps.** The five suites
  (51 + 190 + 13 + 48 + 119 checks) run in seconds; two real bugs were only found because
  a test emulated the device's missing `os.path` and the restricted route table.
* **Do not trust a report over a measurement.** Subagent summaries, API answers and one's
  own earlier conclusions were wrong several times here (a "touch defect" that was an idle
  answer, "6 bands" when the test never ran, a "dead display" that was a slow DHCP lease).
  Re-measure before acting.
* **Write the trap down where the next person reads it**: the command, the file, the
  reason. Every section above started as a confusing hour.
