#!/usr/bin/env python3
"""Throughput-Messung fuer die Bildvorschau des Debug-Servers (nur lesend).

Misst, wie lange /screen.raw?scale=N am echten Board braucht und welcher
Durchsatz dabei herauskommt. Aendert nichts am Board -- reine GET-Abfragen
plus ein Heap-Vergleich vor/nach jeder Runde.

Aufruf:  python3 tools/bench_vorschau.py [runden]
Umgebung: BOARD_HOST (Standard 192.168.1.168)
"""

import json
import os
import sys
import time
import urllib.request

HOST = os.environ.get("BOARD_HOST", "192.168.1.168")
BASE = "http://%s" % HOST


def _get(path, timeout=60):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return r.read(), dict(r.headers)


def heap_kb():
    try:
        body, _ = _get("/api/state", timeout=20)
        return json.loads(body.decode()).get("heap")
    except Exception as exc:  # noqa: BLE001
        return "? (%s)" % exc


def measure_scale(scale, runden):
    """Liefert Liste (sekunden, bytes, w, h) je Runde."""
    ergebnisse = []
    for i in range(runden):
        t0 = time.perf_counter()
        body, headers = _get("/screen.raw?scale=%d" % scale)
        dt = time.perf_counter() - t0
        mass = (headers.get("X-Screen") or "0x0").split("x")
        ergebnisse.append((dt, len(body), int(mass[0]), int(mass[1])))
    return ergebnisse


def main():
    runden = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    print("Board: %s" % BASE)
    print("Heap vorher: %s Bytes" % heap_kb())
    print()
    print("%-8s %-6s %-10s %-10s %-9s %-8s" % (
        "scale", "Nr", "Sekunden", "Bytes", "KB/s", "Aufloesung"))
    for scale in (1, 2, 4, 8):
        for nr, (dt, n, w, h) in enumerate(measure_scale(scale, runden), 1):
            kb_s = (n / 1024.0) / dt if dt else 0
            print("%-8d %-6d %-10.3f %-10d %-9.1f %dx%d"
                  % (scale, nr, dt, n, kb_s, w, h))
        print()
    print("Heap nachher: %s Bytes" % heap_kb())


if __name__ == "__main__":
    sys.exit(main())
