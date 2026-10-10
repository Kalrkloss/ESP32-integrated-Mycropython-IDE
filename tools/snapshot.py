#!/usr/bin/env python3
"""Screenshot vom Board holen und als PNG ablegen.

Ablauf: Board neu starten, Geraeteskript ausfuehren, das PNG als Base64 ausgibt,
Base64 aus der Ausgabe schneiden, PNG schreiben.

Aufruf:  python3 tools/snapshot.py [ausgabe.png] [geraeteskript.py]
"""

import base64
import glob
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MPY = os.environ.get("MPY", "/opt/esp-tools/bin/python3")
BOARD_USB_PATH = "/dev/serial/by-path/pci-0000:00:15.0-usb-0:4.4.3:1.0"
ZIGBEE_SERIAL = "F0:F5:BD:03:09:5C"
DEFAULT_SCRIPT = os.path.join(REPO, "firmware", "device", "snapshot_test.py")
DEFAULT_OUT = "/root/.hermes/cache/scratch/board_snapshot.png"


def resolve_port():
    """Dock-Port primaer, sonst by-id -- der Zigbee-Stick wird nie gewaehlt."""
    if os.path.exists(BOARD_USB_PATH):
        return BOARD_USB_PATH
    for path in sorted(glob.glob("/dev/serial/by-id/*Espressif*")):
        if ZIGBEE_SERIAL in path:
            continue
        return path
    raise SystemExit("Board nicht gefunden (Dock-Port 1-4.4.3 oder by-id)")


def wait_ready(port, tries=40):
    """Nach einem Reset kurz warten, bis der Interpreter wieder antwortet."""
    for _ in range(tries):
        if os.path.exists(port):
            probe = subprocess.run([MPY, "-m", "mpremote", "connect", port, "eval", "1"],
                                   capture_output=True, text=True)
            if probe.returncode == 0:
                return True
        time.sleep(0.5)
    raise SystemExit("Board antwortet nach dem Reset nicht")


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    script = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_SCRIPT
    port = resolve_port()
    print("Port:", port)
    print("Skript:", script)

    subprocess.run([MPY, "-m", "mpremote", "connect", port, "reset"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    wait_ready(port)

    proc = subprocess.run([MPY, "-m", "mpremote", "connect", port, "run", script],
                          capture_output=True, text=True, timeout=180)
    out = proc.stdout
    if proc.returncode != 0:
        print("mpremote exit:", proc.returncode, proc.stderr[-500:])

    for line in out.splitlines():
        if line.startswith(("snapshot_test:", "snapshot:")):
            print("  board>", line)

    if "SNAP_BEGIN" not in out or "SNAP_END" not in out:
        print("!!! Kein PNG in der Ausgabe gefunden. Letzte Zeilen:")
        print("\n".join(out.splitlines()[-25:]))
        return 1

    body = out.split("SNAP_BEGIN", 1)[1]
    dims = body.split("\n", 1)[0].split()
    payload = body.split("\n", 1)[1].split("SNAP_END", 1)[0]
    payload = "".join(payload.split())
    blob = base64.b64decode(payload)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as fh:
        fh.write(blob)
    w, h = (int(dims[0]), int(dims[1])) if len(dims) >= 2 else ("?", "?")
    print("PNG gespeichert:", out_path, "(%d Bytes, %sx%s)" % (len(blob), w, h))
    return 0


if __name__ == "__main__":
    sys.exit(main())
