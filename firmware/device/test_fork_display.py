# test_fork_display.py -- Konfiguration, mit der dieses Panel nachweislich laeuft.
#
# Gegenueber dem Mainline-Build sind zwei Dinge anders:
#   1. lcd_bus.SPIBusFast statt SPIBus  (DMA + gestueckelte Transfers; der Fork-Branch
#      feature/spi_bus_fast von straga bringt diesen Bustreiber mit)
#   2. ZWEI volle Framebuffer in PSRAM (je 320*480*2 = 307200 Byte) -> LVGL-Full-Refresh,
#      wie es das QSPI-Panel braucht
#
# Der Mainline-Baustein konnte den Frame nur in einem Block senden und stiess dabei an
# max_transfer_sz (32768 Byte); Partial-Render mit kleinen Baendern laeuft mit dem
# QSPI-Adresszaehler des Panels auseinander (Panel bleibt schwarz bzw. zeigt GRAM-Rauschen).

import time

import lcd_bus
import machine
import lvgl as lv
import axs15231b

WIDTH = 320
HEIGHT = 480
HOLD_SECONDS = 300

print("test_fork_display: start")

spi_bus = machine.SPI.Bus(host=1, sck=47, quad_pins=(21, 48, 40, 39))
display_bus = lcd_bus.SPIBusFast(
    spi_bus=spi_bus, dc=8, cs=45, freq=40_000_000, spi_mode=3, quad=True)
print("test_fork_display: SPIBusFast ok")

size = WIDTH * HEIGHT * 2
fb1 = display_bus.allocate_framebuffer(size, lcd_bus.MEMORY_SPIRAM)
fb2 = display_bus.allocate_framebuffer(size, lcd_bus.MEMORY_SPIRAM)
print("test_fork_display: Framebuffer %d + %d Bytes" % (len(fb1), len(fb2)))

display = axs15231b.AXS15231B(
    display_bus, WIDTH, HEIGHT,
    frame_buffer1=fb1, frame_buffer2=fb2,
    backlight_pin=1, color_space=lv.COLOR_FORMAT.RGB565,
    rgb565_byte_swap=True, backlight_on_state=axs15231b.STATE_PWM)

display.set_power(True)
display.set_backlight(80)
display.init()
print("test_fork_display: init ok")

scr = lv.screen_active()

# 1) Vollflaechig rot -- einfachster Nachweis, dass Daten ankommen
scr.set_style_bg_color(lv.color_hex(0xFF0000), 0)
t0 = time.ticks_ms()
for _ in range(30):
    lv.timer_handler()
    time.sleep_ms(20)
print("test_fork_display: rot gezeichnet (%d ms)" % time.ticks_diff(time.ticks_ms(), t0))
time.sleep_ms(2000)

# 2) Endbild, bleibt stehen
scr.set_style_bg_color(lv.color_hex(0x000080), 0)

title = lv.label(scr)
title.set_text("DISPLAY OK")
title.set_style_text_color(lv.color_hex(0xFFFFFF), 0)
title.align(lv.ALIGN.TOP_MID, 0, 40)

sub = lv.label(scr)
sub.set_text("JC3248W535")
sub.set_style_text_color(lv.color_hex(0xFFFF00), 0)
sub.align(lv.ALIGN.TOP_MID, 0, 80)

box = lv.obj(scr)
box.set_size(90, 90)
box.align(lv.ALIGN.CENTER, 0, 30)
box.set_style_bg_color(lv.color_hex(0x00FF00), 0)

bar = lv.bar(scr)
bar.set_size(280, 24)
bar.align(lv.ALIGN.BOTTOM_MID, 0, -60)
bar.set_value(100, 0)

print("test_fork_display: Endbild steht %d s" % HOLD_SECONDS)
end = time.time() + HOLD_SECONDS
while time.time() < end:
    lv.timer_handler()
    time.sleep_ms(30)
print("test_fork_display: ende")
