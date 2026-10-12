# 10 -- Touch bring-up (AXS15231B, JC3248W535)

Result: **the touch works.** Measured on the running system: 8419
driver reads in 300 s (~28 Hz), **262 detected touch points** with
real coordinates, UI counter from `Touch: 0` to `Touch: 1`.

There were **four independent bugs** -- each one alone is enough for the touch
to appear dead:

## 1. LVGL received no time tick (the actual root cause)

`lv.tick_get()` stood constantly at 0. An `lv.timer_handler()` without a running
tick executes **not a single timer** -- that is why the input driver was never
polled (measurement: 0 calls of `_get_coords` in 60 s), there was no animation
and no refresh. The panel still showed its image because the bus driver writes the
framebuffer out itself -- that misled the diagnosis for a long time.

```python
last_tick = time.ticks_ms()
while True:
    now = time.ticks_ms()
    lv.tick_inc(time.ticks_diff(now, last_tick))   # <-- was missing
    last_tick = now
    lv.timer_handler()
    mcp_screen.service_requests()
    time.sleep_ms(5)
```

After the fix: the tick runs (20960 -> 21857), LVGL polls the driver 41x in 1.5 s
(~27 Hz).

## 2. `enable_input_priority()` silences the touch

The call comes from the reference configuration (`straga/micropython_lcd`) and
switches the indev to `lv.INDEV_MODE.EVENT`. In `lv_indev.c`, **`lv_indev_set_mode`
thereby pauses LVGL's own polling timer** and relies on the 33-ms timer of the
driver. If its creation fails (hidden in a `try/except pass` in our case),
the touch is never read.

Solution: remove the call, use the default mode (TIMER, value 1) -- LVGL polls
itself every 33 ms.

## 3. GPIO 8 assigned twice: display DC = touch SCL

The reference configuration passes `dc=8` to the display bus -- and GPIO 8 is
at the same time the touch's I2C clock. Measurement: without display the touch
reads (still) constants, **with the display initialised the bus aborts**
(`OSError: [Errno 116] ETIMEDOUT`).

In QSPI mode the panel needs no DC: the command is in the opcode
(`0x02` write command, `0x32` write pixel). The vendor BSP accordingly passes
`NULL`. Solution: `dc=-1` ("no DC pin" in ESP-IDF).
After that the touch bus remains usable after the display initialisation.

## 4. The reset/interrupt theory was wrong (and was discarded)

At times it looked as though the controller were stuck in reset (GPIO 12
floats to LOW, `RST` seemed to be the data situation). The vendor BSP says:

```c
#define EXAMPLE_PIN_NUM_QSPI_TOUCH_RST  (-1)   // keine Reset-Leitung
#define EXAMPLE_PIN_NUM_QSPI_TOUCH_INT  (-1)   // keine Interrupt-Leitung
#define BSP_I2C_NUM                     (I2C_NUM_0)
#define BSP_I2C_CLK_SPEED_HZ            400000
```

GPIO 12 is the SD-card clock line, GPIO 11 not the touch INT. The
controller is read purely by polling. Our configuration now follows the
vendor values: **I2C port 0, 400 kHz, no RST/INT**.

## Data format (for verification)

The idle response is a constant byte pattern -- **not a fault**, but
"nothing touched" (byte 1 = point count; the vendor code discards `> 1` just like
our driver). Measured: `85 85 85 85 85 85 85 85` before the first touch,
afterwards `42 42 42 42 42 42 42 42`. Both patterns are idle -- do not read them as a defect.
A real data record looks like this:

```
00 01 80 45 01 b4 38 39
 |  |  |  |  |  |  |  +-- y_l
 |  |  |  |  |  |  +----- y_h (only lower 4 bits)
 |  |  |  |  |  +-------- unused
 |  |  |  |  +----------- x_l
 |  |  |  +-------------- x_h (lower 4 bits) + event bits (top)
 |  |  +----------------- 1 = one touch point
 |  +-------------------- point count
 +----------------------- gesture
```

Decoded: x = 0x45 = 69, y = 0x1b4 = 436, event "pressed". Release frames
begin with `ff`, idle with `85`.

## Test tools (in the repo)

| Tool | Purpose |
|---|---|
| `tools/touch_long.py [s]` | long observation: logs every response deviating from the idle response, detected points and the UI label. Does **not** itself read on I2C (two readers on the same device destroy the responses). |
| `tools/touch_probe_rst.py` | reset/INT variant (only sensible for other board revisions). |
| `tools/mcp_call.py <tool> [json]` | single MCP call, also for `exec_python`. |
| `firmware/device/probe_touch*.py` | isolated bring-up probes (without/with display, bus clock, read length, command variants, register access). |

## What was ruled out

* **Command protocol:** identical in all references (11 bytes
  `b5 ab a5 5a 00 00 00 08 00 00 00`, then read 8 bytes).
* **Access layer:** `i2c` module and `machine.I2C` deliver identically -- the
  software layer is not it.
* **Bus clock / read length / command variants / register access / wait times:**
  tested through, no difference.
* **Hardware:** the vendor's demo software can do touch -- the hardware is
  fine. The details from the vendor BSP (pins, I2C port, no DC) were
  the key in the end.
