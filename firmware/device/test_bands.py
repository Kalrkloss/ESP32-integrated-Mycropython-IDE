# test_bands.py -- Farbbänder-Test: prueft Farbanordnung UND Geometrie des Panels.
# Drei Baender ueber die volle Breite: oben rot, Mitte gruen, unten blau.
# Helligkeit absichtlich niedrig (30 %), damit eine Kamera die Farben nicht ueberstrahlt.

import time

import lcd_bus
import machine
import lvgl as lv

WIDTH = 320
HEIGHT = 480
HOLD_SECONDS = 240

print("test_bands: start")

spi_bus = machine.SPI.Bus(host=1, sck=47, quad_pins=(21, 48, 40, 39))
bus = lcd_bus.SPIBusFast(spi_bus=spi_bus, dc=8, cs=45, freq=40_000_000,
                         spi_mode=3, quad=True)
size = WIDTH * HEIGHT * 2
fb1 = bus.allocate_framebuffer(size, lcd_bus.MEMORY_SPIRAM)
fb2 = bus.allocate_framebuffer(size, lcd_bus.MEMORY_SPIRAM)

import axs15231b  # noqa: E402  (Dateisystem-Fassung mit SPIBusFast-Unterstuetzung)

display = axs15231b.AXS15231B(
    bus, WIDTH, HEIGHT, frame_buffer1=fb1, frame_buffer2=fb2,
    backlight_pin=1, color_space=lv.COLOR_FORMAT.RGB565, rgb565_byte_swap=True)
display.set_power(True)
display.set_backlight(30)   # bewusst dunkel
display.init()
print("test_bands: init ok")

scr = lv.screen_active()
scr.set_style_bg_color(lv.color_hex(0x000000), 0)

for i, (name, color) in enumerate((("rot", 0xFF0000), ("gruen", 0x00FF00), ("blau", 0x0000FF))):
    band = lv.obj(scr)
    band.set_size(WIDTH, HEIGHT // 3)
    band.set_pos(0, i * (HEIGHT // 3))
    band.set_style_bg_color(lv.color_hex(color), 0)
    band.set_style_border_width(0, 0)
    band.set_style_radius(0, 0)
    print("test_bands: Band", name)

for _ in range(40):
    lv.timer_handler()
    time.sleep_ms(20)
print("test_bands: gezeichnet -- bleibt %d s" % HOLD_SECONDS)

end = time.time() + HOLD_SECONDS
while time.time() < end:
    lv.timer_handler()
    time.sleep_ms(30)
print("test_bands: ende")
