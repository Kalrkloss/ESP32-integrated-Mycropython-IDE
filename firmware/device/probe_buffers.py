# probe_buffers.py -- Verhalten mit vom Framework verwalteten (partiellen) Puffern
# und Sichtpruefung der LVGL-Snapshot-API (Bildquelle fuer Screenshots).

import time

import lcd_bus
import machine
import lvgl as lv
import axs15231b

print("probe_buffers: start")

spi_bus = machine.SPI.Bus(host=1, sck=47, quad_pins=(21, 48, 40, 39))
bus = lcd_bus.SPIBus(spi_bus=spi_bus, dc=8, cs=45, freq=40_000_000,
                     spi_mode=3, quad=True)

display = axs15231b.AXS15231B(
    bus, 320, 480,
    backlight_pin=1, color_space=lv.COLOR_FORMAT.RGB565, rgb565_byte_swap=True)

fb1 = getattr(display, "_frame_buffer1", None)
fb2 = getattr(display, "_frame_buffer2", None)
print("probe_buffers: auto fb1 = %s Bytes, fb2 = %s Bytes"
      % (len(fb1) if fb1 is not None else None, len(fb2) if fb2 is not None else None))

display.set_power(True)
display.set_backlight(80)
display.init()
print("probe_buffers: init ok")

scr = lv.screen_active()
for name, color in (("rot", 0xFF0000), ("gruen", 0x00FF00), ("blau", 0x0000FF)):
    try:
        scr.set_style_bg_color(lv.color_hex(color), 0)
        for _ in range(25):
            lv.timer_handler()
            time.sleep_ms(20)
        print("probe_buffers: %s ok" % name)
    except Exception as exc:  # noqa: BLE001
        print("probe_buffers: %s FEHLER %s: %s" % (name, type(exc).__name__, exc))
        break

print("== Snapshot-API ==")
print("  lv.snapshot_take vorhanden:", hasattr(lv, "snapshot_take"))
try:
    snap = lv.snapshot_take(scr, lv.COLOR_FORMAT.RGB565)
    print("  snapshot:", type(snap))
    attrs = [a for a in dir(snap) if not a.startswith("__")]
    print("  Attribute:", attrs)
    for attr in ("buf", "data", "stride", "width", "height", "dsc"):
        try:
            print("   .%s = %s" % (attr, getattr(snap, attr)))
        except Exception as exc:  # noqa: BLE001
            print("   .%s -> %s" % (attr, exc))
except Exception as exc:  # noqa: BLE001
    print("  snapshot_take fehlgeschlagen:", type(exc).__name__, exc)

print("probe_buffers: fertig")
