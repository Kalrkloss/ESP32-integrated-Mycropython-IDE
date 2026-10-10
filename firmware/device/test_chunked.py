# test_chunked.py -- Panel-Test mit dem stueckweisen Flush (per `tools/deploy.sh run ...`).
# Erwartung: Der 307-KB-Frame wird in 32-KB-Bloecken gesendet und kommt durch.

import time

import lcd_bus
import machine
import lvgl as lv
from axs15231b_chunked import AXS15231B as AXS15231BChunked

WIDTH = 320
HEIGHT = 480

print("test_chunked: start")

spi_bus = machine.SPI.Bus(host=1, sck=47, quad_pins=(21, 48, 40, 39))
bus = lcd_bus.SPIBus(spi_bus=spi_bus, dc=8, cs=45, freq=40_000_000,
                     spi_mode=3, quad=True)
fb = bus.allocate_framebuffer(WIDTH * HEIGHT * 2, lcd_bus.MEMORY_SPIRAM)
print("test_chunked: framebuffer", len(fb), "Bytes")

display = AXS15231BChunked(
    bus, WIDTH, HEIGHT, frame_buffer1=fb,
    backlight_pin=1, color_space=lv.COLOR_FORMAT.RGB565,
    rgb565_byte_swap=True)
print("test_chunked: Treiber erzeugt, Chunk", display._chunk_bytes, "Bytes")

display.set_power(True)
display.set_backlight(80)
display.init()
print("test_chunked: panel initialisiert")

scr = lv.screen_active()
ok = 0
for name, color in (("rot", 0xFF0000), ("gruen", 0x00FF00), ("blau", 0x0000FF),
                    ("dunkelgrau", 0x202020)):
    try:
        t0 = time.ticks_ms()
        scr.set_style_bg_color(lv.color_hex(color), 0)
        for _ in range(25):
            lv.timer_handler()
            time.sleep_ms(20)
        dt = time.ticks_diff(time.ticks_ms(), t0)
        print("test_chunked: %s gezeichnet (%d ms)" % (name, dt))
        ok += 1
    except Exception as exc:  # noqa: BLE001
        print("test_chunked: %s FEHLGESCHLAGEN: %s: %s" % (name, type(exc).__name__, exc))
        break

pixel = fb[0] | (fb[1] << 8)
r = ((pixel >> 11) & 0x1F) << 3
g = ((pixel >> 5) & 0x3F) << 2
b = (pixel & 0x1F) << 3
print("test_chunked: Pixel(0,0) = R%d G%d B%d (erwartet ~32/32/32)" % (r, g, b))

try:
    i2c = machine.I2C(0, sda=4, scl=8, freq=400_000)
    print("test_chunked: I2C-Geraete:", ["0x%02x" % a for a in i2c.scan()])
except Exception as exc:  # noqa: BLE001
    print("test_chunked: I2C-Scan fehlgeschlagen:", exc)

print("test_chunked: fertig, %d von 4 Farben ok" % ok)
