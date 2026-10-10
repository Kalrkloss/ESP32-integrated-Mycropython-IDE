# Bring-up-Test fuer das Panel (per `tools/deploy.sh run firmware/device/test_screen.py`).
# Zweck: Panel-Init und Farbausgabe isoliert pruefen, ohne den MCP-Server.
# Prueft zusaetzlich, ob der Framebuffer das enthaelt, was LVGL gezeichnet hat --
# das ist die Voraussetzung fuer die Screenshots des Debug-Servers.

import time

import lcd_bus
import machine
import lvgl as lv
import axs15231b

WIDTH = 320
HEIGHT = 480

print("test_screen: start")

spi_bus = machine.SPI.Bus(host=1, sck=47, quad_pins=(21, 48, 40, 39))
display_bus = lcd_bus.SPIBus(
    spi_bus=spi_bus, dc=8, cs=45, freq=40_000_000, spi_mode=3, quad=True)

fb = display_bus.allocate_framebuffer(WIDTH * HEIGHT * 2, lcd_bus.MEMORY_SPIRAM)
print("test_screen: framebuffer", len(fb), "Bytes")

display = axs15231b.AXS15231B(
    display_bus, WIDTH, HEIGHT, frame_buffer1=fb,
    backlight_pin=1, color_space=lv.COLOR_FORMAT.RGB565,
    rgb565_byte_swap=True, backlight_on_state=axs15231b.STATE_PWM)
display.set_power(True)
display.set_backlight(80)
display.init()
print("test_screen: panel initialisiert")

scr = lv.screen_active()
for name, color in (("rot", 0xFF0000), ("gruen", 0x00FF00), ("blau", 0x0000FF),
                    ("weiss", 0xFFFFFF), ("dunkelgrau", 0x202020)):
    scr.set_style_bg_color(lv.color_hex(color), 0)
    for _ in range(25):
        lv.timer_handler()
        time.sleep_ms(20)
    print("test_screen: Farbe", name, "gezeichnet")

# Rueckleseprobe: LVGL hat Dunkelgrau gezeichnet -- steht das im Puffer?
pixel = fb[0] | (fb[1] << 8)
r, g, b = ((pixel >> 11) & 0x1F) << 3, ((pixel >> 5) & 0x3F) << 2, (pixel & 0x1F) << 3
print("test_screen: Pixel(0,0) = R%d G%d B%d (erwartet ~32/32/32)" % (r, g, b))

# Touch pruefen
try:
    i2c = machine.I2C(0, sda=4, scl=8, freq=400_000)
    print("test_screen: I2C-Geraete:", ["0x%02x" % a for a in i2c.scan()])
except Exception as exc:  # noqa: BLE001
    print("test_screen: I2C-Scan fehlgeschlagen:", exc)

print("test_screen: fertig")
