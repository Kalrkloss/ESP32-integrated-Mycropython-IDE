# Panel-Konfiguration des JC3248W535 -- an EINER Stelle.
#
# Wichtig (gemessen, siehe docs/09-display-bringup.md):
#   * Das QSPI-Panel braucht LVGL-Full-Refresh mit vollem Framebuffer (307200 Byte).
#   * Der Mainline-Baustein kann so einen Block nicht senden (Buslimit 32768 Byte) und
#     hat kein DMA-Chunking -> Panel bleibt schwarz. Dafuer gibt es `lcd_bus.SPIBusFast`
#     im Fork-Branch feature/spi_bus_fast. Dieses Modul nimmt ihn, wenn vorhanden, und
#     sagt sonst ausdruecklich, dass die Anzeige so nicht funktionieren wird.

import time

import lcd_bus
import machine
import lvgl as lv
import axs15231b

WIDTH = 320
HEIGHT = 480

QSPI_SCK = 47
QSPI_PINS = (21, 48, 40, 39)
QSPI_CS = 45
QSPI_DC = 8
BACKLIGHT = 1
FREQ = 40_000_000

TOUCH_SDA = 4
TOUCH_SCL = 8
TOUCH_I2C_HOST = 1


def bus_fast_available():
    return getattr(lcd_bus, "SPIBusFast", None) is not None


def create_display(full_frames=True, brightness=70):
    """Bus + Display erzeugen und initialisieren. Rueckgabe: (display, bus)."""
    spi_bus = machine.SPI.Bus(host=1, sck=QSPI_SCK, quad_pins=QSPI_PINS)

    fast = getattr(lcd_bus, "SPIBusFast", None)
    if fast is not None:
        bus = fast(spi_bus=spi_bus, dc=QSPI_DC, cs=QSPI_CS,
                   freq=FREQ, spi_mode=3, quad=True)
        print("display_config: SPIBusFast (DMA, gestueckelte Transfers)")
    else:
        bus = lcd_bus.SPIBus(spi_bus=spi_bus, dc=QSPI_DC, cs=QSPI_CS,
                             freq=FREQ, spi_mode=3, quad=True)
        print("display_config: WARNUNG -- nur SPIBus vorhanden (Mainline-Bau). "
              "Ein voller Frame (307200 Byte) kann damit nicht gesendet werden; "
              "das Panel wird vermutlich schwarz bleiben (Buslimit 32768 Byte).")

    kwargs = {}
    if full_frames:
        size = WIDTH * HEIGHT * 2
        kwargs["frame_buffer1"] = bus.allocate_framebuffer(size, lcd_bus.MEMORY_SPIRAM)
        kwargs["frame_buffer2"] = bus.allocate_framebuffer(size, lcd_bus.MEMORY_SPIRAM)
        print("display_config: 2 volle Framebuffer (%d Byte je)" % size)

    extra = {}
    try:
        extra["backlight_on_state"] = axs15231b.STATE_PWM
    except AttributeError:
        pass

    display = axs15231b.AXS15231B(
        bus, WIDTH, HEIGHT,
        backlight_pin=BACKLIGHT,
        color_space=lv.COLOR_FORMAT.RGB565,
        rgb565_byte_swap=True,
        **kwargs, **extra)

    display.set_power(True)
    display.set_backlight(brightness)
    display.init()
    print("display_config: init ok (fb1=%d Byte)" % len(display._frame_buffer1))
    return display, bus


def create_touch():
    """Touch-Treiber -- MUSS nach dem Display erzeugt werden."""
    import i2c
    import axs15231
    bus = i2c.I2C.Bus(host=TOUCH_I2C_HOST, sda=TOUCH_SDA, scl=TOUCH_SCL)
    device = i2c.I2C.Device(bus, axs15231.I2C_ADDR, axs15231.BITS)
    indev = axs15231.AXS15231(device)
    try:
        indev.enable_input_priority()
    except Exception:  # noqa: BLE001
        pass
    return indev
