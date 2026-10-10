# probe.py -- Bestandsaufnahme des Boards (per `tools/deploy.sh run firmware/device/probe.py`).
# Laeuft ohne Display-Init, damit es auch bei Problemen mit dem Panel funktioniert.

import gc
import sys

print("== MicroPython ==")
print("version :", sys.version)
print("platform:", sys.platform)
print("heap    : used=%d free=%d" % (gc.mem_alloc(), gc.mem_free()))

try:
    import machine
    print("freq_mhz:", machine.freq() // 1000000)
    print("uid     :", "".join("%02x" % b for b in machine.unique_id()))
    print("reset   :", machine.reset_cause())
except Exception as exc:  # noqa: BLE001
    print("machine:", exc)

print("== Speicherbereiche ==")
try:
    import esp32
    for heap in esp32.idf_heap_info(esp32.HEAP_DATA):
        print("  HEAP_DATA region: total=%d free=%d" % (heap[2], heap[3]))
except Exception as exc:  # noqa: BLE001
    print("  esp32.idf_heap_info:", exc)

print("== Dateisystem ==")
try:
    import os
    st = os.statvfs("/")
    print("  frei %d von %d Bytes" % (st[0] * st[3], st[0] * st[2]))
    print("  Dateien:", sorted(os.listdir("/")))
except Exception as exc:  # noqa: BLE001
    print("  os:", exc)

print("== Module ==")
for name in ("lvgl", "lcd_bus", "axs15231b", "axs15231", "task_handler", "i2c",
             "deflate", "binascii", "zlib", "socket", "_thread", "network", "bluetooth",
             "machine", "esp32", "time", "json"):
    try:
        __import__(name)
        print("  ok    :", name)
    except Exception as exc:  # noqa: BLE001
        print("  FEHLT :", name, "-", type(exc).__name__, exc)

print("== WLAN ==")
try:
    import network
    sta = network.WLAN(network.STA_IF)
    print("  aktiv=%s verbunden=%s" % (sta.active(), sta.isconnected()))
    if sta.isconnected():
        print("  ifconfig:", sta.ifconfig())
except Exception as exc:  # noqa: BLE001
    print("  network:", exc)

print("== LVGL-Version ==")
try:
    import lvgl as lv
    for attr in ("version_major", "version_minor", "version_patch"):
        print("  %s = %s" % (attr, getattr(lv, attr, "?")))
except Exception as exc:  # noqa: BLE001
    print("  lvgl:", exc)

print("probe: fertig")
