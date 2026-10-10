#!/usr/bin/env python3
"""Touch-Messung mit korrekt gehaltenen Steuerleitungen.

Setzt RST (GPIO12) dauerhaft HIGH und INT (GPIO11) als Eingang mit Pull-Up --
beides muss gehalten werden, sonst gibt der Garbage Collector die Pins frei und
der Controller faellt zurueck in den Reset (gemessen: RST haengt von Haus aus
auf LOW).

Beobachtet werden:
  * Rohdaten und erkannte Punkte aus LVGLs eigener Abfrage (kein zweiter Leser)
  * Pegelwechsel der INT-Leitung (Hardwaresignal, unabhängig vom I2C)
  * die UI-Beschriftung "Touch: n"

Aufruf:  python3 tools/touch_probe_rst.py [sekunden]
"""

import json
import sys
import time
import urllib.request

HOST = "192.168.1.168"
OUT = "/tmp/touchrst.txt"

CODE = """
import display_config
import machine
import time

# Steuerleitungen anlegen und FESTHALTEN (sonst GC -> Pin frei -> Reset).
_PINS = [machine.Pin(11, machine.Pin.IN, machine.Pin.PULL_UP),
         machine.Pin(12, machine.Pin.OUT)]
_RST = _PINS[1]
_RST.value(0)
time.sleep_ms(200)
_RST.value(1)
time.sleep_ms(200)
display_config._HALTEPINS = _PINS
print("Steuerleitungen: INT=%d (Pull-Up), RST=%d" % (_PINS[0].value(), _RST.value()))

t = display_config.LAST_TOUCH
cls = type(t)
_orig = cls._read_data
beob = {"aufrufe": 0, "punkte": [], "roh": {}}

def _obs(self):
    pts = _orig(self)
    beob["aufrufe"] += 1
    raw = bytes(self._rx_buf).hex()
    beob["roh"][raw] = beob["roh"].get(raw, 0) + 1
    if pts:
        beob["punkte"].append((pts[0].x, pts[0].y, pts[0].event))
    return pts

cls._read_data = _obs

print("Messung laeuft -- bitte jetzt aufs Display tippen (%.0f s)" % SECONDS)
t0 = time.time()
letzter_int = _PINS[0].value()
int_wechsel = []
while time.time() - t0 < SECONDS:
    wert = _PINS[0].value()
    if wert != letzter_int:
        int_wechsel.append((round(time.time() - t0, 2), wert))
        print("%5.1fs  INT %d -> %d" % (time.time() - t0, letzter_int, wert))
        letzter_int = wert
    time.sleep_ms(20)

print()
print("RST waehrend der Messung: %d" % _RST.value())
print("Treiberlesevorgaenge: %d" % beob["aufrufe"])
print("erkannte Beruehrungspunkte: %d" % len(beob["punkte"]))
if beob["punkte"]:
    print("Punkte:", beob["punkte"][:12])
print("INT-Wechsel: %d %s" % (len(int_wechsel), int_wechsel[:15]))
print("verschiedene Rohdaten:")
for raw, count in sorted(beob["roh"].items(), key=lambda kv: -kv[1])[:10]:
    print("   %s  x%d" % (raw, count))
"""


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 40.0
    code = CODE.replace("SECONDS", str(seconds))
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "exec_python", "arguments": {"code": code}}}
    request = urllib.request.Request(
        "http://%s/mcp" % HOST, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json"})
    started = time.time()
    with urllib.request.urlopen(request, timeout=seconds + 60) as response:
        reply = json.loads(response.read().decode())
    text = reply["result"]["content"][0]["text"]
    print(text)
    with open(OUT, "w") as handle:
        handle.write(text)
    print("(Protokoll: %s, Dauer %.1f s)" % (OUT, time.time() - started))
    return 0


if __name__ == "__main__":
    sys.exit(main())
