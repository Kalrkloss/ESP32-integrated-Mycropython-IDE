# probe_touch4.py -- letzte Zugriffsvarianten: Register-/Sub-Adress-Zugriff und
# Wartezeit zwischen Kommando und Lesen.
#
# Bisher liefert der Controller bei jedem Zugriff konstant 0x85. Diese Varianten
# pruefen, ob er statt des Pseudo-Kommandos eine Registeradresse erwartet bzw.
# eine Pause zwischen Schreiben und Lesen braucht.

import time

import machine

import i2c

pins = [machine.Pin(11, machine.Pin.IN, machine.Pin.PULL_UP),
        machine.Pin(12, machine.Pin.OUT)]
pins[1].value(0)
time.sleep_ms(200)
pins[1].value(1)
time.sleep_ms(200)

bus = i2c.I2C.Bus(host=1, sda=4, scl=8)
dev = i2c.I2C.Device(bus, 0x3B, 8)
print("scan:", [hex(a) for a in bus.scan()])

KOMMANDO = bytearray([0xB5, 0xAB, 0xA5, 0x5A, 0x00, 0x00, 0x00, 0x08, 0x00, 0x00, 0x00])


def zeige(ueberschrift, aufruf):
    print("--- %s ---" % ueberschrift)
    try:
        ergebnis = aufruf()
        print("    %s" % ergebnis)
    except Exception as exc:  # noqa: BLE001
        print("    FEHLER %s: %s" % (type(exc).__name__, exc))


def kommandieren_dann_lesen(pause_ms):
    def lauf():
        dev.write(memoryview(KOMMANDO))
        if pause_ms:
            time.sleep_ms(pause_ms)
        rx = bytearray(8)
        dev.read(buf=memoryview(rx))
        return bytes(rx).hex()
    return lauf


for pause in (0, 5, 20, 100):
    zeige("Kommando, dann %d ms Pause, dann lesen" % pause,
          kommandieren_dann_lesen(pause))

# Registerzugriffe: Sub-Adresse schreiben, dann lesen (read_mem bzw. write_mem+read)
for adresse in (0x00, 0x01, 0xB5, 0xFC):
    zeige("read_mem(0x%02X, 8)" % adresse,
          lambda a=adresse: dev.read_mem(a, 8).hex())

for adresse in (0xB5, 0x00):
    zeige("write_mem(0x%02X, ...) + read" % adresse,
          lambda a=adresse: (dev.write_mem(a, bytearray([0xAB, 0xA5, 0x5A, 0x00, 0x00, 0x00, 0x08])),
                             dev.read(8).hex())[1])

# Kombiniert: Kommandobytes ausser dem ersten als Daten zur Adresse 0xB5
zeige("write_mem(0xB5, Rest des Kommandos) + read(8)",
      lambda: (dev.write_mem(0xB5, bytearray([0xAB, 0xA5, 0x5A, 0x00, 0x00, 0x00, 0x08, 0x00, 0x00, 0x00])),
               dev.read(8).hex())[1])

pins[1].value(0)
time.sleep_ms(200)
pins[1].value(1)
time.sleep_ms(200)
print("RST am Ende:", pins[1].value(), "INT:", pins[0].value())
print("probe_touch4: ende")
