# probe_touch2.py -- Touch-Kette mit korrigierter Display-Konfiguration pruefen.
#
# Reihenfolge wie in der App: Steuerleitungen -> Display -> Touch. Geprueft wird
# nach jedem Schritt, was der Touch-Controller liefert. Erwartung nach den
# Korrekturen: keine Zeitueberschreitung mehr (dc=-1 laesst GPIO 8 dem Touch-Takt),
# und gueltige Daten statt Konstanten.

import time

import display_config

TX = bytearray([0xB5, 0xAB, 0xA5, 0x5A, 0x00, 0x00, 0x00, 0x08, 0x00, 0x00, 0x00])


def lesen(dev, n=5, ueberschrift=""):
    print("--- %s ---" % ueberschrift)
    for _ in range(n):
        try:
            dev.write(memoryview(TX))
            rx = bytearray(8)
            dev.read(buf=memoryview(rx))
            print("    %s" % bytes(rx).hex())
        except Exception as exc:  # noqa: BLE001
            print("    FEHLER %s: %s" % (type(exc).__name__, exc))
        time.sleep_ms(150)


display_config.prepare_touch_pins()

import i2c  # noqa: E402

bus = i2c.I2C.Bus(host=display_config.TOUCH_I2C_HOST,
                  sda=display_config.TOUCH_SDA, scl=display_config.TOUCH_SCL)
print("scan:", [hex(a) for a in bus.scan()])
dev = i2c.I2C.Device(bus, 0x3B, 8)

lesen(dev, 5, "ohne Display")

display_config.create_display(full_frames=True, brightness=30)

lesen(dev, 5, "mit Display (dc=-1)")

treiber = display_config.create_touch()
print("--- ueber den Treiber ---")
for _ in range(5):
    punkte = treiber._read_data()
    print("    %s   Punkte=%d" % (bytes(treiber._rx_buf).hex(), len(punkte)))
    time.sleep_ms(150)

pins = display_config.LAST_TOUCH_PINS
print("Steuerleitungen am Ende: INT=%d RST=%d" % (pins[0].value(), pins[1].value()))
print("probe_touch2: ende")
