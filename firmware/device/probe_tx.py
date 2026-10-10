# probe_tx.py -- tx_color-Limit messen: Groesse und Speicherart (PSRAM vs. internes DMA).
# Ziel: klaeren, warum 32000 Byte mit "OSError: 257" scheitern.

import lcd_bus
import machine

print("probe_tx: start")

spi_bus = machine.SPI.Bus(host=1, sck=47, quad_pins=(21, 48, 40, 39))
bus = lcd_bus.SPIBus(spi_bus=spi_bus, dc=8, cs=45, freq=40_000_000,
                     spi_mode=3, quad=True)
print("probe_tx: bus ok")

SIZES = (640, 4096, 8192, 16384, 32000, 32768, 40000, 65536)


def try_tx(label, buf, size):
    view = memoryview(buf)[:size]
    try:
        bus.tx_color(0x2C, view, 0, 0, 319, size // 640 - 1 if size % 640 == 0 else 479, 0, False)
        print("  OK   %-34s %6d Bytes" % (label, size))
        return True
    except Exception as exc:  # noqa: BLE001
        print("  FEHL %-34s %6d Bytes -> %s: %s" % (label, size, type(exc).__name__, exc))
        return False


print("== PSRAM-Puffer ==")
psram = bus.allocate_framebuffer(320 * 480 * 2, lcd_bus.MEMORY_SPIRAM)
for size in SIZES:
    try_tx("PSRAM", psram, size)

print("== internes DMA-Puffer ==")
internal = bus.allocate_framebuffer(65536, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)
for size in SIZES:
    try_tx("intern+DMA", internal, size)

print("== intern ohne DMA-Flag ==")
plain = bus.allocate_framebuffer(65536, lcd_bus.MEMORY_INTERNAL)
for size in (640, 32000):
    try_tx("intern", plain, size)

print("probe_tx: fertig")
