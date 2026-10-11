# Display bring-up JC3248W535 — measured findings

Status: 2026-10-10, everything measured on real hardware (board on dock port 1-4.4.3,
webcam on the server as the "eye", MCP debug server on the board).

## Initial symptom

- Backlight on, panel black.
- On start the panel shows **bright, random coloured pixels** (GRAM noise).
- That means: the panel is being driven (backlight, QSPI communication), but it receives
  no **valid image data**.

## Measurement 1: bus limit

`machine.SPI.Bus` sets `max_transfer_sz = SPI_LL_DMA_MAX_BIT_LEN / 8` = **32768 bytes**
(see `micropy_updates/esp32/machine_hw_spi.c`). A complete frame is
320 × 480 × 2 = **307200 bytes** — as *one* transaction it fails with
`OSError: 257(lcd_panel_io_tx_color)` (ESP_ERR_NO_MEM).

| Size | Result |
|---|---|
| 30720 bytes (48 rows) | works |
| 32000 bytes (50 rows) | fails (257) |

From the framework's automatic buffer scheme: it allocates **2 × 30720 bytes** and
thus chooses partial render.

## Measurement 2: partial render runs without errors but shows nothing

With framework-managed buffers (2 × 30720 bytes, internal DMA) all flushes run
**error-free** — the panel nevertheless stayed black (camera image: only reflections).
Reason: in QSPI mode the driver sets only **CASET** in `_set_memory_location` and
relies on the panel's address counter. LVGL partial render, however, writes
48-row bands at arbitrary positions; the row address (RASET) is never set.
Without a full-frame refresh the counter runs out of sync.

## Measurement 3: full frame with own chunking aborts

Own framebuffer in PSRAM (307200 bytes) + derived driver that splits the frame into
10 × 30720-byte chunks (first block with command, further ones with `cmd=-1`):
panel init ok, then **USB connection gone (EIO)** → the board restarts (panic/reset)
on the first flush. In addition, in full-frame mode the framework supplies only
`_dummy_set_memory_location` for `_set_memory_location` → **`_RAMWR = 0x2C` without the
QSPI encoding** (`(0x32 << 24) | (cmd << 8)`) that this driver needs in quad mode.

## Consequence and solution

The mainline build of `lvgl_micropython` cannot drive this panel: it lacks the
DMA bus driver that chunks large transfers (`SPIBusFast`).

**Viable path (implemented this way):** take only this one feature into the tree that
builds cleanly. The entire difference between fork and mainline lies in
`ext_mod/lcd_bus/`:

- new: `esp32_src/spi_bus_fast.c`, `spi_bus_fast_task.c`, `spi_bus_fast_rotation.c`
  and the associated headers
- changed: `modlcd_bus.c` (15 lines), `esp32_src/i80_bus.c` (7), `esp32_include/rgb_bus.h` (3),
  `micropython.cmake` (3 entries for the new source files)

So: copy `ext_mod/lcd_bus/` from the fork (backup as `lcd_bus.orig`), keep the rest of
the mainline tree, rebuild. No fork build needed — its compilation fails
anyway on a version conflict of the components (`espressif__esp_tinyusb` new, but
`espressif__tinyusb` old: `error: 'CFG_TUD_CDC_EP_BUFSIZE' undeclared`).

**Second necessary patch:** `lcd_bus.SPIBusFast` is a **separate type** in the C module
(`isinstance(bus, lcd_bus.SPIBus)` is `False`). The display driver checks exactly for that and
rejects it with `RuntimeError: incompatable bus driver`; moreover the
QSPI detection then fails (32-bit commands instead of 8). Therefore a copy lies in
`firmware/device/drivers/axs15231b.py` that treats `SPIBusFast` like `SPIBus`
(the filesystem shadows the frozen module).

**Result (confirmed on the device and via camera):** `SPIBusFast` + two full PSRAM framebuffers
(307200 bytes each) + patched driver → panel shows the LVGL content correctly, colours are
correct (red/green/blue in the drawn order). The camera white balance turns
pure red into "orange/yellow" and green into "white" — so for colour statements on the panel
the eye (or the MCP screenshot) is authoritative, not the camera image.

```python
spi_bus = machine.SPI.Bus(host=1, sck=47, quad_pins=(21, 48, 40, 39))
bus = lcd_bus.SPIBusFast(spi_bus=spi_bus, dc=8, cs=45,
                         freq=40_000_000, spi_mode=3, quad=True)
fb1 = bus.allocate_framebuffer(320 * 480 * 2, lcd_bus.MEMORY_SPIRAM)
fb2 = bus.allocate_framebuffer(320 * 480 * 2, lcd_bus.MEMORY_SPIRAM)
display = axs15231b.AXS15231B(bus, 320, 480, frame_buffer1=fb1, frame_buffer2=fb2,
                              backlight_pin=1, color_space=lv.COLOR_FORMAT.RGB565,
                              rgb565_byte_swap=True)
```

Build: `tools/build_fork.sh` or directly in the mainline tree
(`python3 make.py esp32 BOARD=ESP32_GENERIC_S3 BOARD_VARIANT=SPIRAM_OCT --flash-size=16
DISPLAY=axs15231b INDEV=axs15231 --ota --partition-size=4194304`).
Panel + UI + debug server come up this way on cold start (`main.py`).

## What else was measured on the board

- **Touch**: I2C address `0x3B`, pins SDA=4, SCL=8 — connected with the `i2c` module (`I2C.Bus`,
  `I2C.Device`). With `machine.I2C` the driver fails with
  `OSError: I2C operation not supported`.
- **Order**: the touch driver must be created **after** the display, otherwise
  `RuntimeError: the display driver must be initilized before the pointer driver`.
- **Driver bug upstream**: `api_drivers/.../indev/axs15231.py` uses a bare
  `lv.DISPLAY_ROTATION._0` without importing `lvgl` → `NameError`. Therefore a copy with
  the added import lies in `firmware/device/drivers/axs15231.py` (the filesystem
  shadows the frozen module).
- **SPI bus stays occupied**: a script that creates `machine.SPI.Bus(host=1, …)` leaves
  the bus initialised on the C side. The next `machine.SPI.Bus(host=1, …)` in the
  same boot fails and takes the interpreter down with it (ugly `TypeError:
  can't convert module to int`). So **reset** before every device script.
- **native USB**: after a reset `/dev/…ttyACM*` briefly disappears; wait actively
  before accesses (do not blindly `sleep`).
- **by-id changes with the firmware**: factory/Annex report
  `USB JTAG/serial debug unit`, MicroPython `Espressif Device`. Therefore the port
  is determined via the USB path (`…-usb-0:4.4.3:1.0`), with by-id as fallback.
