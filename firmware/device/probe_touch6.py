# probe_touch6.py -- Gegenprobe mit machine.I2C statt des i2c-Moduls.
#
# Das i2c-Modul (i2c.py) und machine.I2C sind zwei verschiedene Implementierungen
# auf demselben Chip. Liefert machine.I2C gueltige Daten, liegt es an der
# Zugriffsschicht und nicht an der Hardware.

import time

import machine

pins = [machine.Pin(11, machine.Pin.IN, machine.Pin.PULL_UP),
        machine.Pin(12, machine.Pin.OUT)]
pins[1].value(0)
time.sleep_ms(200)
pins[1].value(1)
time.sleep_ms(200)

cmd = bytes([0xB5, 0xAB, 0xA5, 0x5A, 0x00, 0x00, 0x00, 0x08, 0x00, 0x00, 0x00])

for takt in (400_000, 100_000):
    try:
        bus = machine.I2C(0, sda=machine.Pin(4), scl=machine.Pin(8), freq=takt)
        print("scan bei %d Hz:" % takt, [hex(a) for a in bus.scan()])
        for _ in range(3):
            try:
                bus.writeto(0x3B, cmd)
                print("    ", bus.readfrom(0x3B, 8).hex())
            except Exception as exc:  # noqa: BLE001
                print("     FEHLER %s: %s" % (type(exc).__name__, exc))
            time.sleep_ms(100)
        try:
            bus.deinit()
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        print("machine.I2C bei %d Hz: FEHLER %s: %s" % (takt, type(exc).__name__, exc))

print("probe_touch6: ende")
