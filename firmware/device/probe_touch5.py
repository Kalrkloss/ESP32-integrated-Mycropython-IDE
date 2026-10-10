# probe_touch5.py -- Identitaetspruefung: reagiert das Geraet an 0x3B auf RST?
#
# Wenn sich die Antwort reproduzierbar mit dem Reset-Pegel aendert, ist 0x3B
# tatsaechlich der Touch-Controller. Bleibt sie unabhaengig davon gleich, ist es
# ein anderes I2C-Geraet (z. B. ein Expander) und der Touch sitzt woanders.

import time

import machine

import i2c

pins = [machine.Pin(11, machine.Pin.IN, machine.Pin.PULL_UP),
        machine.Pin(12, machine.Pin.OUT)]

bus = i2c.I2C.Bus(host=1, sda=4, scl=8)
dev = i2c.I2C.Device(bus, 0x3B, 8)
KOMMANDO = memoryview(bytearray([0xB5, 0xAB, 0xA5, 0x5A, 0x00, 0x00, 0x00, 0x08, 0x00, 0x00, 0x00]))

for runde in range(3):
    for pegel, name in ((0, "RST LOW"), (1, "RST HIGH")):
        pins[1].value(pegel)
        time.sleep_ms(300)
        geraete = []
        try:
            geraete = [hex(a) for a in bus.scan()]
        except Exception as exc:  # noqa: BLE001
            geraete = ["scan FEHLER %s" % type(exc).__name__]
        werte = []
        for _ in range(3):
            try:
                dev.write(KOMMANDO)
                rx = bytearray(8)
                dev.read(buf=memoryview(rx))
                werte.append(bytes(rx).hex())
            except Exception as exc:  # noqa: BLE001
                werte.append("FEHLER %s" % type(exc).__name__)
            time.sleep_ms(60)
        print("Runde %d  %-8s  scan=%s  INT=%d  Daten=%s"
              % (runde, name, geraete, pins[0].value(), werte))

pins[1].value(1)
time.sleep_ms(300)
print("probe_touch5: ende (RST=%d)" % pins[1].value())
