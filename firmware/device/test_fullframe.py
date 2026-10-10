# test_fullframe.py -- Full-Frame-Ausgabe mit stueckweisem Flush.
# Bleibt am Ende stehen, damit das Bild am Panel geprueft werden kann.
#
# Warum Full-Frame: Der Treiber setzt im QSPI-Modus nur CASET und verlaesst sich auf
# den Adresszaehler des Panels. LVGL-Partial-Render (48-Zeilen-Baender) laeuft damit
# auseinander -> das Panel bleibt schwarz. Full-Frame mit gestueckeltem Datenstrom
# (erster Block mit Kommando, weitere mit cmd=-1) ist der vom Treiber vorgesehene Weg.

import time

import lcd_bus
import machine
import lvgl as lv

from axs15231b_chunked import AXS15231B

WIDTH = 320
HEIGHT = 480
HOLD_SECONDS = 240

print("test_fullframe: start")

spi_bus = machine.SPI.Bus(host=1, sck=47, quad_pins=(21, 48, 40, 39))
bus = lcd_bus.SPIBus(spi_bus=spi_bus, dc=8, cs=45, freq=40_000_000,
                     spi_mode=3, quad=True)

fb = bus.allocate_framebuffer(WIDTH * HEIGHT * 2, lcd_bus.MEMORY_SPIRAM)
print("test_fullframe: framebuffer %d Bytes in PSRAM" % len(fb))

display = AXS15231B(
    bus, WIDTH, HEIGHT, frame_buffer1=fb,
    backlight_pin=1, color_space=lv.COLOR_FORMAT.RGB565, rgb565_byte_swap=True)
print("test_fullframe: Chunk %d Bytes -> %d Bloecke pro Frame"
      % (display._chunk_bytes, (len(fb) + display._chunk_bytes - 1) // display._chunk_bytes))

display.set_power(True)
display.set_backlight(80)
display.init()
print("test_fullframe: init ok")

scr = lv.screen_active()

# 1) Vollflaechig rot -- der einfachste Test: kommt ueberhaupt etwas an?
scr.set_style_bg_color(lv.color_hex(0xFF0000), 0)
t0 = time.ticks_ms()
for _ in range(20):
    lv.timer_handler()
    time.sleep_ms(20)
print("test_fullframe: rot gezeichnet (%d ms)" % time.ticks_diff(time.ticks_ms(), t0))
time.sleep_ms(1500)

# 2) Endbild: dunkler Grund, grosser weisser Text, gruener Balken, blaues Feld
scr.set_style_bg_color(lv.color_hex(0x000080), 0)

title = lv.label(scr)
title.set_text("FULLFRAME")
title.set_style_text_color(lv.color_hex(0xFFFFFF), 0)
title.align(lv.ALIGN.TOP_MID, 0, 40)

sub = lv.label(scr)
sub.set_text("JC3248W535 / chunked flush")
sub.set_style_text_color(lv.color_hex(0xFFFF00), 0)
sub.align(lv.ALIGN.TOP_MID, 0, 80)

bar = lv.bar(scr)
bar.set_size(280, 24)
bar.align(lv.ALIGN.BOTTOM_MID, 0, -60)
bar.set_value(100, 0)

box = lv.obj(scr)
box.set_size(80, 80)
box.align(lv.ALIGN.CENTER, 0, 40)
box.set_style_bg_color(lv.color_hex(0x00FF00), 0)

print("test_fullframe: Endbild gesetzt -- bleibt %d s stehen" % HOLD_SECONDS)
end = time.time() + HOLD_SECONDS
while time.time() < end:
    lv.timer_handler()
    time.sleep_ms(30)
print("test_fullframe: ende")
