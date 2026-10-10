# boot.py -- laeuft vor main.py: WLAN verbinden.
# Zugangsdaten stehen in wifi.json (nicht im Repo; wifi.json.example als Vorlage).
# Wenn keine Verbindung zustande kommt, startet main.py trotzdem -- dann ist das Board
# nur ueber die serielle Konsole erreichbar, und der Laufzeit-Fehler steht im Log.

import sys
import time

import network

WIFI_FILE = "wifi.json"
TIMEOUT_S = 20


def _load_config():
    try:
        import json
        with open(WIFI_FILE) as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        print("boot: %s nicht lesbar (%s) -- kein WLAN" % (WIFI_FILE, exc))
        return None


def connect(cfg):
    if not cfg:
        return False
    sta = network.WLAN(network.STA_IF)
    if sta.isconnected():
        print("boot: WLAN schon verbunden:", sta.ifconfig())
        return True
    sta.active(True)
    try:
        hostname = cfg.get("hostname")
        if hostname:
            sta.config(dhcp_hostname=hostname)
    except (ValueError, OSError):
        pass
    sta.connect(cfg.get("ssid"), cfg.get("password"))
    deadline = time.time() + TIMEOUT_S
    while time.time() < deadline:
        if sta.isconnected():
            print("boot: WLAN verbunden:", sta.ifconfig())
            return True
        time.sleep(0.25)
    print("boot: WLAN-Verbindung zu %r fehlgeschlagen" % cfg.get("ssid"))
    return False


try:
    connect(_load_config())
except Exception as exc:  # noqa: BLE001 - Boot darf nie abbrechen
    print("boot: Fehler beim Verbinden: %s: %s" % (type(exc).__name__, exc))
