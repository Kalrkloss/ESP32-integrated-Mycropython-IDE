#!/usr/bin/env python3
"""Touch-Beobachtung am laufenden Board.

Prueft in einem Durchgang:
  1. ob der 33-ms-Timer des Treibers laeuft (enable_input_priority + Aufrufzaehler)
  2. was der Controller roh liefert (korrekte Aufrufform `read(buf=...)`)
  3. ob daraus Beruehrungspunkte werden (ueber den Treiberpfad `_read_data`)

Aufruf:  python3 tools/touch_watch.py [sekunden]
Protokoll zusaetzlich in /tmp/touchlog.txt
"""

import json
import sys
import time
import urllib.request

HOST = "192.168.1.168"
OUT = "/tmp/touchlog.txt"

CODE = """
import display_config
import time

t = display_config.LAST_TOUCH
cls = type(t)

stats = {"calls": 0, "punkte": []}
_orig_coords = cls._get_coords

def _coords(self):
    stats["calls"] += 1
    return _orig_coords(self)

cls._get_coords = _coords

try:
    t.enable_input_priority()
    print("33-ms-Timer des Treibers: aktiviert")
except Exception as exc:
    print("enable_input_priority FEHLER:", type(exc).__name__, exc)

print("Messung startet -- bitte jetzt aufs Display tippen (%.0f s)" % SECONDS)
t0 = time.time()
roh_werte = {}
while time.time() - t0 < SECONDS:
    try:
        pts = t._read_data()
        raw = bytes(t._rx_buf).hex()
        roh_werte[raw] = roh_werte.get(raw, 0) + 1
        if pts:
            stats["punkte"].append((pts[0].x, pts[0].y, pts[0].event))
            print("%5.1fs  PUNKT x=%d y=%d event=%d  roh=%s"
                  % (time.time() - t0, pts[0].x, pts[0].y, pts[0].event, raw))
    except Exception as exc:
        raw = "FEHLER " + type(exc).__name__ + ": " + str(exc)
        roh_werte[raw] = roh_werte.get(raw, 0) + 1
    time.sleep_ms(300)

print()
print("Treiberaufrufe (_get_coords, durch Timer/LVGL): %d" % stats["calls"])
print("erkannte Punkte: %d" % len(stats["punkte"]))
if stats["punkte"]:
    print("Punkte:", stats["punkte"][:15])
print("verschiedene Rohdaten:")
for raw, count in sorted(roh_werte.items(), key=lambda kv: -kv[1])[:8]:
    print("   %s  x%d" % (raw, count))
"""


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 45.0
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
