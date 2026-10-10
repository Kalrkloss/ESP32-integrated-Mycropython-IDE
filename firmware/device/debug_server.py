# debug_server.py -- I2C-Anbindung des Touch und Server-Start isoliert pruefen.

import sys
import time

print("== i2c-Modul ==")
try:
    import i2c
    print("  i2c.I2C:", [a for a in dir(i2c.I2C) if not a.startswith("_")])
    bus = i2c.I2C.Bus(host=1, sda=4, scl=8)
    print("  Bus ok:", bus)
    dev = i2c.I2C.Device(bus, 0x3B, 8)
    print("  Device ok:", dev)
    import axs15231
    print("  AXS15231.I2C_ADDR=0x%02x BITS=%d" % (axs15231.I2C_ADDR, axs15231.BITS))
    touch = axs15231.AXS15231(dev)
    print("  Touch-Objekt ok:", type(touch).__name__)
except Exception as exc:  # noqa: BLE001
    print("  FEHLER:")
    sys.print_exception(exc)

print("== MCP-Server ==")
try:
    import mcp_serve
    mcp_serve.start(port=80)
    print("  Server gestartet")
    time.sleep(0.5)
    import mcp_screen
    print("  screen:", mcp_screen.describe())
    import mcp_tools
    print("  Tools:", [t.name for t in mcp_tools.build_tools()])
except Exception as exc:  # noqa: BLE001
    print("  FEHLER:")
    sys.print_exception(exc)

print("== WLAN ==")
try:
    import network
    sta = network.WLAN(network.STA_IF)
    print("  aktiv=%s verbunden=%s" % (sta.active(), sta.isconnected()))
    if sta.isconnected():
        print("  ifconfig:", sta.ifconfig())
except Exception as exc:  # noqa: BLE001
    print("  FEHLER:")
    sys.print_exception(exc)

print("debug_server: fertig")
