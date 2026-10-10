# snapshot_test.py -- Sichtpruefung: Testmuster zeichnen, LVGL-Snapshot, PNG ausgeben.
# Der Host (tools/snapshot.py) holt das PNG ueber die serielle Konsole und legt es ab.
# Ausgabeformat:  SNAP_BEGIN <scale>\n<base64>\nSNAP_END

import time

import lcd_bus
import machine
import lvgl as lv
import axs15231b

import mcp_png
import mcp_screen

WIDTH = 320
HEIGHT = 480
SCALE = 2  # 160x240 halbiert die Datenmenge fuer die serielle Uebertragung


def build_display():
    spi_bus = machine.SPI.Bus(host=1, sck=47, quad_pins=(21, 48, 40, 39))
    bus = lcd_bus.SPIBus(spi_bus=spi_bus, dc=8, cs=45, freq=40_000_000,
                         spi_mode=3, quad=True)
    display = axs15231b.AXS15231B(
        bus, WIDTH, HEIGHT,
        backlight_pin=1, color_space=lv.COLOR_FORMAT.RGB565, rgb565_byte_swap=True)
    display.set_power(True)
    display.set_backlight(80)
    display.init()
    return display


def draw_pattern():
    scr = lv.screen_active()
    scr.set_style_bg_color(lv.color_hex(0x0A0F14), 0)

    title = lv.label(scr)
    title.set_text("SNAPSHOT-TEST")
    title.set_style_text_color(lv.color_hex(0xFFFFFF), 0)
    title.align(lv.ALIGN.TOP_MID, 0, 30)

    box = lv.obj(scr)
    box.set_size(120, 120)
    box.center()
    box.set_style_bg_color(lv.color_hex(0xFF0000), 0)
    box.set_style_border_width(4, 0)
    box.set_style_border_color(lv.color_hex(0xFFFFFF), 0)

    count = lv.label(scr)
    count.set_text("1 2 3 4 5")
    count.set_style_text_color(lv.color_hex(0x00FF00), 0)
    count.align(lv.ALIGN.BOTTOM_MID, 0, -40)

    # Zeilenkontrast fuer die Ausrichtung
    for i, color in enumerate((0xFF0000, 0x00FF00, 0x0000FF, 0xFFFF00, 0xFF00FF, 0x00FFFF)):
        bar = lv.obj(scr)
        bar.set_size(40, 20)
        bar.set_style_bg_color(lv.color_hex(color), 0)
        bar.set_style_border_width(0, 0)
        bar.align(lv.ALIGN.BOTTOM_LEFT, 10, -80 - i * 0)
        bar.set_pos(10 + i * 50, 380)

    for _ in range(40):
        lv.timer_handler()
        time.sleep_ms(20)


def snapshot_info():
    scr = lv.screen_active()
    snap = lv.snapshot_take(scr, lv.COLOR_FORMAT.RGB565)
    header = getattr(snap, "header", None)
    print("snapshot: type=%s data_size=%s" % (type(snap).__name__, getattr(snap, "data_size", "?")))
    if header is not None:
        attrs = [a for a in dir(header) if not a.startswith("__")]
        print("snapshot: header-Attribute:", attrs)
        for attr in ("w", "h", "stride", "cf", "magic", "flags"):
            try:
                print("snapshot:   header.%s = %s" % (attr, getattr(header, attr)))
            except Exception as exc:  # noqa: BLE001
                print("snapshot:   header.%s -> %s" % (attr, exc))
    data = getattr(snap, "data", None)
    print("snapshot: data-Objekt:", type(data).__name__, "len-ish:", getattr(data, "__len__", None))
    return snap


def main():
    display = build_display()
    print("snapshot_test: display ok, fb1 =",
          len(getattr(display, "_frame_buffer1", b"")))
    draw_pattern()
    print("snapshot_test: Muster gezeichnet")

    snap = snapshot_info()
    header = getattr(snap, "header", None)
    w = int(getattr(header, "w", WIDTH))
    h = int(getattr(header, "h", HEIGHT))
    stride = int(getattr(header, "stride", w * 2))
    print("snapshot_test: %dx%d stride=%d" % (w, h, stride))

    image = snap
    data, sw, sh, swap = mcp_screen._capture_snapshot()
    if data is None:
        print("snapshot_test: Snapshot-Pfad in mcp_screen lieferte nichts -- Fallback")
        raw = bytes(snap.data)
        if stride != w * 2:
            # Zeilen enger packen (stride kann groesser sein als die Zeilenbreite)
            packed = bytearray()
            for y in range(h):
                packed += raw[y * stride:y * stride + w * 2]
            raw = packed
        data, sw, sh, swap = raw, w, h, True

    blob = mcp_png.encode_rgb565_png(data, sw, sh, byte_swap=swap)
    print("snapshot_test: PNG %d Bytes (%dx%d)" % (len(blob), sw, sh))
    import binascii
    print("SNAP_BEGIN %d %d" % (sw, sh))
    encoded = binascii.b2a_base64(blob).decode()
    print(encoded)
    print("SNAP_END")


main()
