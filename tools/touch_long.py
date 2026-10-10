#!/usr/bin/env python3
"""Lange Touch-Beobachtung (Standard 300 s) am laufenden Board.

Es wird NICHT selbst am I2C gelesen -- LVGL fragt den Treiber ohnehin ~27x/s ab.
Mitgeschrieben werden:
  * jede Antwort, die von der Ruheantwort (85 85 ...) abweicht, samt Zeitpunkt
  * erkannte Beruehrungspunkte aus dem Treiber
  * die UI-Beschriftung "Touch: n"

Damit ist kein Timing noetig: einfach tippen, wann es passt.

Aufruf:  python3 tools/touch_long.py [sekunden]
Protokoll: /tmp/touchlong.txt
"""

import json
import sys
import time
import urllib.request

HOST = "192.168.1.168"
OUT = "/tmp/touchlong.txt"

CODE = """
import display_config
import lvgl as lv
import time

t = display_config.LAST_TOUCH
cls = type(t)
_orig = cls._read_data

beob = {"aufrufe": 0, "punkte": [], "abweichend": {}}


def _obs(self):
    pts = _orig(self)
    beob["aufrufe"] += 1
    raw = bytes(self._rx_buf).hex()
    if raw != "8585858585858585":
        beob["abweichend"][raw] = beob["abweichend"].get(raw, 0) + 1
        print("ABWEICHEND  %s" % raw)
    if pts:
        beob["punkte"].append((round(time.time() % 1000, 1), pts[0].x, pts[0].y, pts[0].event))
        print("PUNKT  x=%d y=%d event=%d" % (pts[0].x, pts[0].y, pts[0].event))
    return pts


cls._read_data = _obs


def _beschriftungen():
    treffer = []
    kette = [lv.screen_active()]
    while kette:
        obj = kette.pop()
        try:
            text = obj.get_text()
            if text and "Touch" in text:
                treffer.append(text)
        except Exception:
            pass
        try:
            for i in range(obj.get_child_count()):
                kette.append(obj.get_child(i))
        except Exception:
            pass
    return treffer


print("Beobachtung %.0f s -- bitte nach Belieben aufs Display tippen" % SECONDS)
t0 = time.time()
letzter_stand = None
while time.time() - t0 < SECONDS:
    try:
        stand = _beschriftungen()
    except Exception as exc:
        stand = ["(Abfrage: %s)" % type(exc).__name__]
    if stand != letzter_stand:
        letzter_stand = stand
        print("%5.1fs  UI: %s" % (time.time() - t0, stand))
    time.sleep_ms(400)

print()
print("Treiberlesevorgaenge: %d" % beob["aufrufe"])
print("erkannte Punkte: %d" % len(beob["punkte"]))
if beob["punkte"]:
    print("Punkte:", beob["punkte"][:20])
print("von der Ruheantwort abweichende Daten:")
if beob["abweichend"]:
    for raw, count in sorted(beob["abweichend"].items(), key=lambda kv: -kv[1])[:12]:
        print("   %s  x%d" % (raw, count))
else:
    print("   keine (immer 85 85 ...)")
"""


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 300.0
    code = CODE.replace("SECONDS", str(seconds))
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "exec_python", "arguments": {"code": code}}}
    request = urllib.request.Request(
        "http://%s/mcp" % HOST, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json"})
    started = time.time()
    with urllib.request.urlopen(request, timeout=seconds + 90) as response:
        reply = json.loads(response.read().decode())
    text = reply["result"]["content"][0]["text"]
    print(text)
    with open(OUT, "w") as handle:
        handle.write(text)
    print("(Protokoll: %s, Dauer %.1f s)" % (OUT, time.time() - started))
    return 0


if __name__ == "__main__":
    sys.exit(main())
