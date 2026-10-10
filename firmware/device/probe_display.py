# probe_display.py -- Displayaufbau mit SPIBusFast Schritt fuer Schritt.
# Voraussetzung: main.py ist NICHT aktiv (sonst ist der SPI-Bus schon belegt).

import sys

import lcd_bus
import machine
import lvgl as lv

print("1: imports ok, SPIBusFast =", hasattr(lcd_bus, "SPIBusFast"))

try:
    spi_bus = machine.SPI.Bus(host=1, sck=47, quad_pins=(21, 48, 40, 39))
    print("2: machine.SPI.Bus ok")
except Exception as exc:  # noqa: BLE001
    print("2: FEHLER"); sys.print_exception(exc); raise SystemExit

try:
    bus = lcd_bus.SPIBusFast(spi_bus=spi_bus, dc=8, cs=45,
                             freq=40_000_000, spi_mode=3, quad=True)
    print("3: SPIBusFast ok ->", bus)
except Exception as exc:  # noqa: BLE001
    print("3: FEHLER"); sys.print_exception(exc); raise SystemExit

for label, flags in (("MEMORY_SPIRAM", lcd_bus.MEMORY_SPIRAM),
                     ("SPIRAM|DMA", lcd_bus.MEMORY_SPIRAM | lcd_bus.MEMORY_DMA),
                     ("INTERNAL|DMA", lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)):
    try:
        fb = bus.allocate_framebuffer(320 * 480 * 2, flags)
        print("4: allocate_framebuffer(%s) ok -> %d Byte" % (label, len(fb)))
        try:
            bus.free_framebuffer(fb)
            print("   (wieder freigegeben)")
        except Exception as exc:  # noqa: BLE001
            print("   free_framebuffer:", exc)
    except Exception as exc:  # noqa: BLE001
        print("4: allocate_framebuffer(%s) FEHLER: %s" % (label, exc))

size = 320 * 480 * 2
fb1 = bus.allocate_framebuffer(size, lcd_bus.MEMORY_SPIRAM)
fb2 = bus.allocate_framebuffer(size, lcd_bus.MEMORY_SPIRAM)
print("5: zwei Puffer ok (%d + %d Byte)" % (len(fb1), len(fb2)))

import axs15231b

try:
    display = axs15231b.AXS15231B(
        bus, 320, 480, frame_buffer1=fb1, frame_buffer2=fb2,
        backlight_pin=1, color_space=lv.COLOR_FORMAT.RGB565, rgb565_byte_swap=True)
    print("6: Treiber erzeugt")
    display.set_power(True)
    display.set_backlight(60)
    display.init()
    print("7: init ok")
    scr = lv.screen_active()
    print("8: screen_active =", scr)
    scr.set_style_bg_color(lv.color_hex(0x00FF00), 0)
    import time
    for _ in range(30):
        lv.timer_handler()
        time.sleep_ms(20)
    print("9: gruen gezeichnet -- bleibt 90 s stehen")
    time.sleep(90)
except Exception as exc:  # noqa: BLE001
    print("6-9: FEHLER"); sys.print_exception(exc)

print("probe_display: ende")
