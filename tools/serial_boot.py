#!/usr/bin/env python3
"""Capture the board's serial console across a reset.

Reads the board's USB CDC console for `seconds`, triggers a power cycle of the
dock port after `delay` seconds and prints everything the board said. Reading the
CDC port does not reset the ESP32-S3 -- only the power cycle does.

Call: python3 tools/serial_boot.py [seconds] [delay]
"""

import subprocess
import sys
import threading
import time

import serial

PORT = "/dev/serial/by-path/pci-0000:00:15.0-usb-0:4.4.3:1.0"
HUB = "1-4.4"
POWER_PORT = "3"
BAUD = 115200


def power_cycle():
    subprocess.run(["uhubctl", "-l", HUB, "-p", POWER_PORT, "-a", "cycle", "-d", "2"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    delay = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
    line = []
    ende = time.time() + seconds
    gecycled = False
    port = None
    while time.time() < ende:
        if not gecycled and time.time() > ende - seconds + delay:
            gecycled = True
            line.append("\n--- power cycle ---\n")
            threading.Thread(target=power_cycle, daemon=True).start()
        if port is None:
            try:
                port = serial.Serial(PORT, BAUD, timeout=0.5)
                line.append("\n--- port opened ---\n")
            except serial.SerialException:
                time.sleep(0.3)
                continue
        try:
            daten = port.read(4096)
        except (serial.SerialException, OSError):
            # The board re-enumerates while power cycling; reconnect instead of giving up.
            try:
                port.close()
            except Exception:  # noqa: BLE001
                pass
            port = None
            time.sleep(0.5)
            continue
        if daten:
            text = daten.decode("utf-8", "replace")
            line.append(text)
            print(text, end="", flush=True)
    if port is not None:
        try:
            port.close()
        except Exception:  # noqa: BLE001
            pass
    geschrieben = "".join(line)
    with open("/root/.hermes/cache/scratch/serial_boot.log", "w") as fh:
        fh.write(geschrieben)
    print("\n--- captured %d bytes, full log: /root/.hermes/cache/scratch/serial_boot.log ---"
          % len(geschrieben))
    return 0


if __name__ == "__main__":
    sys.exit(main())
