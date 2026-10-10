# probe_touch3.py -- verbleibende Variablen des Touch-Zugriffs durchtesten.
#
# Nach den Korrekturen (dc=-1, RST gepulst und HIGH) antwortet der Controller
# weiter mit konstanten Bytes. Hier werden die naheliegenden Variablen
# abgearbeitet: Bustakt, Leselaenge, Kommandovariante, Pulsdauer des Resets.
# Jeder Schritt einzeln abgesichert, damit ein Fehler den Rest nicht abbricht.

import time

import machine

import i2c

pins = [machine.Pin(11, machine.Pin.IN, machine.Pin.PULL_UP),
        machine.Pin(12, machine.Pin.OUT)]

KOMMANDO_11 = bytearray([0xB5, 0xAB, 0xA5, 0x5A, 0x00, 0x00, 0x00, 0x08, 0x00, 0x00, 0x00])
KOMMANDO_8 = bytearray([0xB5, 0xAB, 0xA5, 0x5A, 0x00, 0x00, 0x00, 0x08])
KOMMANDO_1 = bytearray([0xB5])
i2c_bus = None
geraet = None


def reset_puls(dauer_ms=200):
    pins[1].value(0)
    time.sleep_ms(dauer_ms)
    pins[1].value(1)
    time.sleep_ms(dauer_ms)


def lesen(kommando, laenge, n=4, ueberschrift=""):
    print("--- %s ---" % ueberschrift)
    for _ in range(n):
        try:
            if kommando:
                geraet.write(memoryview(kommando))
            rx = bytearray(laenge)
            geraet.read(buf=memoryview(rx))
            print("    %s" % bytes(rx).hex())
        except Exception as exc:  # noqa: BLE001
            print("    FEHLER %s: %s" % (type(exc).__name__, exc))
        time.sleep_ms(120)


reset_puls()

for takt in (100_000, 400_000, 50_000):
    try:
        i2c_bus = i2c.I2C.Bus(host=1, sda=4, scl=8, freq=takt)
        geraet = i2c.I2C.Device(i2c_bus, 0x3B, 8)
        print("scan bei %d Hz: %s" % (takt, [hex(a) for a in i2c_bus.scan()]))
        lesen(KOMMANDO_11, 8, 3, "Takt %d Hz" % takt)
    except Exception as exc:  # noqa: BLE001
        print("Takt %d Hz: FEHLER %s: %s" % (takt, type(exc).__name__, exc))

if geraet is not None:
    for laenge in (8, 14, 22, 32):
        lesen(KOMMANDO_11, laenge, 2, "Leselaenge %d" % laenge)
    lesen(KOMMANDO_8, 8, 2, "Kommando 8 Byte")
    lesen(KOMMANDO_1, 8, 2, "Kommando 1 Byte")
    lesen(None, 8, 2, "ohne Kommando")

for dauer in (10, 500):
    reset_puls(dauer)
    lesen(KOMMANDO_11, 8, 2, "Reset-Puls %d ms" % dauer)

pins[1].value(0)
time.sleep_ms(200)
pins[1].value(1)
time.sleep_ms(200)
print("RST am Ende:", pins[1].value(), "INT:", pins[0].value())
print("probe_touch3: ende")
