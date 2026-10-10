#!/usr/bin/env python3
"""Touch-Beobachter: stoert die laufende Abfrage nicht, sondern liest mit.

Wichtig: Der Treiber wird hier NICHT selbst gelesen. LVGL fragt ihn im
Hauptthread ohnehin alle 33 ms ab; zwei Leser am selben I2C-Geraet wuerden sich
gegenseitig die Antworten zerschiessen. Stattdessen werden die Aufrufe
mitprotokolliert (Rohdaten + erkannte Punkte) und die UI-Beschriftung
"Touch: n" beobachtet -- damit ist die ganze Kette abgedeckt.

Aufruf:  python3 tools/touch_observe.py [sekunden]
Protokoll: /tmp/touchobs.txt
"""

import json
import sys
import time
import urllib.request

HOST = "192.168.1.168"
OUT = "/tmp/touchobs.txt"

CODE = """
import display_config
import lvgl as lv
import time

t = display_config.LAST_TOUCH
cls = type(t)

beob = {"aufrufe": 0, "punkte": [], "roh": {}}

_orig_read = cls._read_data

def _read_obs(self):
    pts = _orig_read(self)
    beob["aufrufe"] += 1
    raw = bytes(self._rx_buf).hex()
    beob["roh"][raw] = beob["roh"].get(raw, 0) + 1
    if pts:
        beob["punkte"].append((pts[0].x, pts[0].y, pts[0].event))
    return pts

cls._read_data = _read_obs


def _label_texte():
    # Alle Beschriftungen der aktiven Seite einsammeln
    treffer = []
    kette = [lv.screen_active()]
    while kette:
        obj = kette.pop()
        try:
            text = obj.get_text()
            if text:
                treffer.append(text)
        except Exception:
            pass
        try:
            for i in range(obj.get_child_count()):
                kette.append(obj.get_child(i))
        except Exception:
            pass
    return treffer


print("Beobachtung laeuft -- bitte jetzt aufs Display tippen (%.0f s)" % SECONDS)
t0 = time.time()
letzter_stand = None
while time.time() - t0 < SECONDS:
    texte = None
    try:
        texte = [x for x in _label_texte() if "Touch" in x]
    except Exception as exc:
        texte = ["(UI-Abfrage: %s)" % type(exc).__name__]
    if texte != letzter_stand:
        letzter_stand = texte
        print("%5.1fs  UI: %s" % (time.time() - t0, texte))
    time.sleep_ms(250)

print()
print("Treiberlesevorgaenge (durch LVGL): %d" % beob["aufrufe"])
print("erkannte Beruehrungspunkte: %d" % len(beob["punkte"]))
if beob["punkte"]:
    print("erste Punkte:", beob["punkte"][:12])
print("verschiedene Rohdaten (Haeufigkeit):")
for raw, count in sorted(beob["roh"].items(), key=lambda kv: -kv[1])[:10]:
    print("   %s  x%d" % (raw, count))
"""


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
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
