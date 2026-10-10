# boot.py -- laeuft vor main.py: WLAN verbinden.
# Zugangsdaten: config.json (von der Weboberflaeche geschrieben) hat Vorrang,
# wifi.json bleibt als Altbestand nutzbar und fuellt nur leere Felder.
# Wenn keine Verbindung zustande kommt, startet main.py trotzdem -- dann ist das Board
# nur ueber die serielle Konsole erreichbar, und der Laufzeit-Fehler steht im Log.

import time

try:
    import network
except ImportError:      # Host-Test ohne Hardware: das Modul fehlt dort
    network = None

CONFIG_FILE = "config.json"   # Weboberflaeche: WLAN + Anzeige + Geraetename
WIFI_FILE = "wifi.json"       # aeltere Ablage, wird weiter gelesen
TIMEOUT_S = 20


def _load_config():
    """Zugangsdaten zusammenfuehren: config.json gewinnt, wifi.json fuellt Luecken.

    Gleiche Regel wie in der Weboberflaeche (mcp_webui.config_lesen), damit beide
    dieselbe wirksame Konfiguration sehen.
    """
    import json
    cfg = {}
    for name in (WIFI_FILE, CONFIG_FILE):
        try:
            with open(name) as fh:
                teil = json.load(fh)
        except (OSError, ValueError) as exc:
            print("boot: %s nicht lesbar (%s)" % (name, exc))
            continue
        for schluessel, wert in teil.items():
            if wert or schluessel not in cfg:
                cfg[schluessel] = wert
    if not cfg.get("ssid"):
        print("boot: keine Zugangsdaten gefunden -- kein WLAN")
        return None
    print("boot: Zugangsdaten geladen (%s)" % ", ".join(sorted(cfg)))
    return cfg


def connect(cfg):
    if not cfg or network is None:
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
