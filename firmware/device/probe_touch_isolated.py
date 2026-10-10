# probe_touch_isolated.py -- Touch OHNE und MIT initialisiertem Display lesen.
#
# Hintergrund: In der Konfiguration liegt TOUCH_SCL auf GPIO 8 -- demselben Pin,
# den der Display-Treiber als DC (Data/Command) bekommt. Im QSPI-Modus braucht
# das Panel kein DC (das steckt im Opcode), aber der Treiber konfiguriert den Pin
# trotzdem. Dieser Test klaert, ob dadurch der I2C-Verkehr gestoert wird.
#
# Lauf:  ./tools/deploy.sh run firmware/device/probe_touch_isolated.py
# (main.py vorher auf dem Board entfernen, damit nichts vorbelegt ist.)

import machine
import time

import i2c

TX = bytearray([0xB5, 0xAB, 0xA5, 0x5A, 0x00, 0x00, 0x00, 0x08, 0x00, 0x00, 0x00])

# Steuerleitungen: RST ist von Haus aus LOW (Controller im Reset!), INT Pull-Up.
pins = [machine.Pin(11, machine.Pin.IN, machine.Pin.PULL_UP),
        machine.Pin(12, machine.Pin.OUT)]
pins[1].value(0)
time.sleep_ms(200)
pins[1].value(1)
time.sleep_ms(200)
print("Steuerleitungen: INT=%d  RST=%d" % (pins[0].value(), pins[1].value()))


def lesen(dev, n=6, ueberschrift=""):
    print("--- %s ---" % ueberschrift)
    for i in range(n):
        dev.write(memoryview(TX))
        rx = bytearray(8)
        dev.read(buf=memoryview(rx))
        print("    %s   INT=%d  RST=%d"
              % (bytes(rx).hex(), pins[0].value(), pins[1].value()))
        time.sleep_ms(150)


bus = i2c.I2C.Bus(host=1, sda=4, scl=8)
print("scan:", [hex(a) for a in bus.scan()])
dev = i2c.I2C.Device(bus, 0x3B, 8)

lesen(dev, 6, "ohne Display")

import display_config  # noqa: E402

display, _bus = display_config.create_display(full_frames=True, brightness=30)

lesen(dev, 6, "mit Display")

import axs15231  # noqa: E402

treiber = axs15231.AXS15231(dev)
print("--- ueber den Treiber ---")
for _ in range(6):
    punkte = treiber._read_data()
    print("    %s   Punkte=%d" % (bytes(treiber._rx_buf).hex(), len(punkte)))
    time.sleep_ms(150)

print("probe_touch_isolated: ende")
