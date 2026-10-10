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

import lvgl as lv

import display_config
import mcp_logbuf
import mcp_screen
import mcp_serve

WIDTH = display_config.WIDTH
HEIGHT = display_config.HEIGHT

# Gehaltene Referenzen: ohne sie kann der GC Treiberobjekte wegraeumen.
_DISPLAY = None
_TOUCH = None


def report(step, exc):
    mcp_logbuf.log("main: %s fehlgeschlagen -- %s: %s" % (step, type(exc).__name__, exc))


def start_display():
    global _DISPLAY
    _DISPLAY, _bus = display_config.create_display(full_frames=True,
                                                   brightness=config_brightness())
    return _DISPLAY


def config_brightness(default=70):
    """Helligkeit aus config.json (Weboberflaeche) -- sonst Standardwert."""
    try:
        import json
        with open("config.json") as fh:
            wert = int(json.load(fh).get("brightness", default))
        return max(0, min(100, wert))
    except (OSError, ValueError, TypeError):
        return default


def start_touch():
    global _TOUCH
    _TOUCH = display_config.create_touch()
    mcp_logbuf.log("main: Touch ok")
    return _TOUCH


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
        mcp_logbuf.log("main: Touch %d bei x=%d y=%d"
                       % (counter["n"], box.get_x(), box.get_y()))

    try:
        box.add_flag(lv.obj.FLAG.CLICKABLE)
    except Exception:  # noqa: BLE001
        pass
    box.add_event_cb(on_click, lv.EVENT.CLICKED, None)

    # Zusaetzlich auf druchgehende Ereignisse reagieren (auch ohne Klick-Treffer),
    # damit ein funktionierender Touch sichtbar wird.
    def on_press(_event):
        mcp_logbuf.log("main: PRESS-Ereignis")

    try:
        scr.add_event_cb(on_press, lv.EVENT.PRESSED, None)
        scr.add_flag(lv.obj.FLAG.CLICKABLE)
    except Exception:  # noqa: BLE001
        pass

    bar = lv.bar(scr)
    bar.set_size(280, 18)
    bar.align(lv.ALIGN.BOTTOM_MID, 0, -30)
    bar.set_value(60, 0)
    mcp_logbuf.log("main: UI ok")


def main():
    ip = device_ip()
    try:
        start_display()
        mcp_screen.attach_framebuffer()
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

    # Hauptschleife. Zwei Dinge sind hier wesentlich:
    #
    # 1. LVGL braucht einen fortlaufenden Zeittakt. Ohne `lv.tick_inc()` bleibt
    #    `lv.tick_get()` auf 0 stehen und `lv.timer_handler()` fuehrt dann KEINEN
    #    Timer aus -- Folge: keine Touch-Abfrage, kein Refresh, keine Animation.
    # 2. KeyboardInterrupt NICHT verschlucken -- in MicroPython erbt es von
    #    Exception, und ohne Durchreichen waere das Board per Ctrl-C (also auch
    #    mit mpremote) nicht mehr erreichbar.
    last_tick = time.ticks_ms()
    while True:
        try:
            now = time.ticks_ms()
            lv.tick_inc(time.ticks_diff(now, last_tick))
            last_tick = now
            lv.timer_handler()
            mcp_screen.service_requests()
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # noqa: BLE001
            print("main: Schleife -- %s: %s" % (type(exc).__name__, exc))
        time.sleep_ms(5)


main()
