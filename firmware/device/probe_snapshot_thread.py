# probe_snapshot_thread.py -- kompletter Screenshot-Pfad isoliert:
# Hilfs-Thread stellt die Anforderung, die Hauptschleife fuehrt sie aus.
# Diagnose-Ausgaben zeigen, wo es klemmt.

import sys
import time

import _thread
import lcd_bus
import machine
import lvgl as lv
import axs15231b

import mcp_screen

spi_bus = machine.SPI.Bus(host=1, sck=47, quad_pins=(21, 48, 40, 39))
bus = lcd_bus.SPIBus(spi_bus=spi_bus, dc=8, cs=45, freq=40_000_000,
                     spi_mode=2, quad=True) if False else lcd_bus.SPIBus(
    spi_bus=spi_bus, dc=8, cs=45, freq=40_000_000, spi_mode=3, quad=True)
display = axs15231b.AXS15231B(
    bus, 320, 480, backlight_pin=1,
    color_space=lv.COLOR_FORMAT.RGB565, rgb565_byte_swap=True)
display.set_power(True)
display.set_backlight(60)
display.init()
print("probe: display ok")

scr = lv.screen_active()
scr.set_style_bg_color(lv.color_hex(0x2050A0), 0)
label = lv.label(scr)
label.set_text("THREAD-TEST")
label.set_style_text_color(lv.color_hex(0xFFFFFF), 0)
label.center()
for _ in range(20):
    lv.timer_handler()

print("probe: UI ok")


def worker():
    for scale in (4, 2, 1):
        try:
            t0 = time.ticks_ms()
            data, w, h, swap = mcp_screen.capture(scale=scale)
            dt = time.ticks_diff(time.ticks_ms(), t0)
            print("worker: scale=%d ok -- %dx%d, %d Bytes, %d ms"
                  % (scale, w, h, len(data), dt))
        except Exception as exc:  # noqa: BLE001
            print("worker: scale=%d FEHLER %s: %s" % (scale, type(exc).__name__, exc))
    print("worker: fertig")


_thread.stack_size(8192) if hasattr(_thread, "stack_size") else None
_thread.start_new_thread(worker, ())
print("probe: Worker gestartet, Hauptschleife bedient 40 s")

end = time.time() + 40
while time.time() < end:
    lv.timer_handler()
    served = mcp_screen.service_requests()
    if served:
        print("probe: Auftrag serviert")
    time.sleep_ms(20)
print("probe: ende")
