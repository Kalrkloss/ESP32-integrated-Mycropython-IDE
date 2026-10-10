# main.py -- Boardstart: Display, Touch, UI, Debug-MCP-Server.
#
# Verifizierte Reihenfolge (auf dem JC3248W535 getestet):
#   1. SPI-Bus + Display OHNE eigenen Framebuffer -> das Framework waehlt Partial-Render
#      mit 2 x 30720-Byte-Puffern. Ein voller 307200-Byte-Puffer scheitert am
#      SPI-Buslimit (max_transfer_sz = 32768).
#   2. Touch erst NACH dem Display (pointer_framework prueft das) und ueber das
#      i2c-Modul (Bus/Device) -- machine.I2C fuehrt zu "I2C operation not supported".
#   3. Zuletzt der Server; danach laeuft die Schleife, die auch die Bildauftraege
#      des Servers ausfuehrt (LVGL ist nicht thread-sicher).
#
# Fehler in einem Schritt werden gemeldet, aber nicht fatal -- der Debug-Server soll
# moeglichst immer erreichbar sein.

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

# Panel-/Busparameter des JC3248W535
QSPI_SCK = 47
QSPI_PINS = (21, 48, 40, 39)
QSPI_CS = 45
QSPI_DC = 8
BACKLIGHT = 1
TOUCH_SDA = 4
TOUCH_SCL = 8
FREQ = 40_000_000


def report(step, exc):
    print("main: %s fehlgeschlagen -- %s: %s" % (step, type(exc).__name__, exc))


def start_display():
    spi_bus = machine.SPI.Bus(host=1, sck=QSPI_SCK, quad_pins=QSPI_PINS)
    bus = lcd_bus.SPIBus(spi_bus=spi_bus, dc=QSPI_DC, cs=QSPI_CS,
                         freq=FREQ, spi_mode=3, quad=True)
    display = axs15231b.AXS15231B(
        bus, WIDTH, HEIGHT, backlight_pin=BACKLIGHT,
        color_space=lv.COLOR_FORMAT.RGB565, rgb565_byte_swap=True)
    display.set_power(True)
    display.set_backlight(70)
    display.init()
    print("main: Display ok (fb1=%d Bytes)" % len(display._frame_buffer1))
    return display


def start_touch():
    import i2c
    import axs15231
    bus = i2c.I2C.Bus(host=1, sda=TOUCH_SDA, scl=TOUCH_SCL)
    device = i2c.I2C.Device(bus, axs15231.I2C_ADDR, axs15231.BITS)
    indev = axs15231.AXS15231(device)
    try:
        indev.enable_input_priority()
    except Exception:  # noqa: BLE001
        pass
    print("main: Touch ok")
    return indev


def device_ip():
    try:
        import network
        sta = network.WLAN(network.STA_IF)
        if sta.isconnected():
            return sta.ifconfig()[0]
    except Exception:  # noqa: BLE001
        pass
    return "offline"


def build_ui(ip):
    scr = lv.screen_active()
    scr.set_style_bg_color(lv.color_hex(0x101820), 0)

    title = lv.label(scr)
    title.set_text("ESP32-S3 DEBUG")
    title.set_style_text_color(lv.color_hex(0xFFFFFF), 0)
    title.align(lv.ALIGN.TOP_MID, 0, 16)

    info = lv.label(scr)
    info.set_text("IP: %s\nMCP: http://%s/mcp" % (ip, ip))
    info.set_style_text_color(lv.color_hex(0x8FD4FF), 0)
    info.align(lv.ALIGN.TOP_LEFT, 12, 60)

    box = lv.obj(scr)
    box.set_size(100, 100)
    box.center()
    box.set_style_bg_color(lv.color_hex(0xE03030), 0)
    box.set_style_border_width(3, 0)
    box.set_style_border_color(lv.color_hex(0xFFFFFF), 0)

    counter = {"n": 0}
    note = lv.label(scr)
    note.set_text("Touch: 0")
    note.set_style_text_color(lv.color_hex(0x00E070), 0)
    note.align(lv.ALIGN.BOTTOM_LEFT, 12, -70)

    def on_click(_event):
        counter["n"] += 1
        note.set_text("Touch: %d" % counter["n"])
        print("main: Touch %d" % counter["n"])

    try:
        box.add_flag(lv.obj.FLAG.CLICKABLE)
    except Exception:  # noqa: BLE001
        pass
    box.add_event_cb(on_click, lv.EVENT.CLICKED, None)

    bar = lv.bar(scr)
    bar.set_size(280, 18)
    bar.align(lv.ALIGN.BOTTOM_MID, 0, -30)
    bar.set_value(60, 0)
    print("main: UI ok")


def main():
    ip = device_ip()
    try:
        start_display()
    except Exception as exc:  # noqa: BLE001
        report("Display", exc)
    try:
        start_touch()
    except Exception as exc:  # noqa: BLE001
        report("Touch", exc)
    try:
        build_ui(ip)
    except Exception as exc:  # noqa: BLE001
        report("UI", exc)
    try:
        mcp_serve.start(port=80)
        print("main: Debug-Server auf http://%s/" % ip)
    except Exception as exc:  # noqa: BLE001
        report("Server", exc)
        try:
            sys.print_exception(exc)
        except Exception:  # noqa: BLE001
            pass

    # Hauptschleife. Achtung: KeyboardInterrupt NICHT verschlucken -- in MicroPython
    # erbt es von Exception, und ohne Durchreichen waere das Board per Ctrl-C
    # (also auch mit mpremote) nicht mehr erreichbar.
    while True:
        try:
            lv.timer_handler()
            mcp_screen.service_requests()
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # noqa: BLE001
            print("main: Schleife -- %s: %s" % (type(exc).__name__, exc))
        time.sleep_ms(20)


main()
