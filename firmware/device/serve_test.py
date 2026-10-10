# serve_test.py -- Display + Touch + MCP-Server hochziehen und laufen lassen.
# Zweck: Server von aussen per HTTP pruefen (curl vom Server aus).
# Laeuft SERV_SECONDS lang, damit man waehrenddessen testen kann.

import sys
import time

import lcd_bus
import machine
import lvgl as lv
import axs15231b

import mcp_screen
import mcp_serve

WIDTH = 320
HEIGHT = 480
SERV_SECONDS = 240

print("serve_test: start")

# 1) Display -- ohne eigenen Framebuffer: das Framework waehlt Partial-Render mit
#    Puffern, die unter dem Buslimit bleiben (2 x 30720 Byte).
spi_bus = machine.SPI.Bus(host=1, sck=47, quad_pins=(21, 48, 40, 39))
bus = lcd_bus.SPIBus(spi_bus=spi_bus, dc=8, cs=45, freq=40_000_000,
                     spi_mode=3, quad=True)
display = axs15231b.AXS15231B(
    bus, WIDTH, HEIGHT,
    backlight_pin=1, color_space=lv.COLOR_FORMAT.RGB565, rgb565_byte_swap=True)
display.set_power(True)
display.set_backlight(70)
display.init()
print("serve_test: display ok, fb1=%d Bytes" % len(display._frame_buffer1))

# 2) Touch -- muss NACH dem Display erzeugt werden (pointer_framework prueft das)
try:
    import i2c
    import axs15231
    i2c_bus = i2c.I2C.Bus(host=1, sda=4, scl=8)
    i2c_dev = i2c.I2C.Device(i2c_bus, axs15231.I2C_ADDR, axs15231.BITS)
    indev = axs15231.AXS15231(i2c_dev)
    try:
        indev.enable_input_priority()
    except Exception:  # noqa: BLE001
        pass
    print("serve_test: touch ok")
except Exception as exc:  # noqa: BLE001
    print("serve_test: touch fehlgeschlagen --", type(exc).__name__, exc)

# 3) UI
scr = lv.screen_active()
scr.set_style_bg_color(lv.color_hex(0x101820), 0)
title = lv.label(scr)
title.set_text("ESP32-S3 DEBUG")
title.set_style_text_color(lv.color_hex(0xFFFFFF), 0)
title.align(lv.ALIGN.TOP_MID, 0, 20)
info = lv.label(scr)
info.set_style_text_color(lv.color_hex(0x8FD4FF), 0)
info.align(lv.ALIGN.TOP_LEFT, 12, 70)

ip = "offline"
try:
    import network
    sta = network.WLAN(network.STA_IF)
    if sta.isconnected():
        ip = sta.ifconfig()[0]
except Exception:  # noqa: BLE001
    pass
info.set_text("IP: %s\nMCP: http://%s/mcp\nBoot: %d s" % (ip, ip, int(time.time())))

box = lv.obj(scr)
box.set_size(100, 100)
box.center()
box.set_style_bg_color(lv.color_hex(0xE03030), 0)

bar = lv.bar(scr)
bar.set_size(280, 20)
bar.align(lv.ALIGN.BOTTOM_MID, 0, -40)
# LVGL 9: set_value(value, anim) -- 0 = ohne Animation (lv.ANIM_OFF)
bar.set_value(65, 0)

for _ in range(30):
    lv.timer_handler()
    time.sleep_ms(20)
print("serve_test: UI ok")

# 4) Server
try:
    mcp_serve.start(port=80)
    print("serve_test: server laeuft auf http://%s/" % ip)
except Exception as exc:  # noqa: BLE001
    print("serve_test: server FEHLER")
    sys.print_exception(exc)

print("serve_test: bleibe %d s aktiv" % SERV_SECONDS)
end = time.time() + SERV_SECONDS
while time.time() < end:
    lv.timer_handler()          # LVGL
    mcp_screen.service_requests()   # Auftraege des Debug-Servers (Snapshot, Widget-Baum)
    time.sleep_ms(20)
print("serve_test: ende")
