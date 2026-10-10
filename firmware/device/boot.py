# boot.py -- runs before main.py: connect to WiFi or open the setup access point.
#
# Credentials come from config.json (written by the web UI); the older wifi.json
# is still read and only fills in empty fields.
#
# If the board is not configured yet, or the connection fails, it opens an open
# access point at 192.168.4.1 with a captive portal so the configuration page can
# be reached without knowing any address. main.py checks portal.SETUP_MODE.

import time

try:
    import network
except ImportError:          # host tests run without hardware
    network = None

import portal

CONFIG_FILE = "config.json"  # web UI: WiFi + display + device name
WIFI_FILE = "wifi.json"      # legacy location, still read
TIMEOUT_S = 20


def load_credentials():
    """Merge credentials: config.json wins, wifi.json fills gaps.

    Same rule as the web UI (mcp_webui.config_lesen) so both see the same
    effective configuration.
    """
    import json
    cfg = {}
    for name in (WIFI_FILE, CONFIG_FILE):
        try:
            with open(name) as fh:
                part = json.load(fh)
        except (OSError, ValueError) as exc:
            print("boot: %s not readable (%s)" % (name, exc))
            continue
        for key, value in part.items():
            if value or key not in cfg:
                cfg[key] = value
    return cfg


def connect(cfg):
    """Connect to the stored network. Returns True when connected."""
    if not cfg or network is None:
        return False
    sta = network.WLAN(network.STA_IF)
    if sta.isconnected():
        print("boot: WiFi already connected:", sta.ifconfig())
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
            print("boot: WiFi connected:", sta.ifconfig())
            return True
        time.sleep(0.25)
    print("boot: cannot connect to %r" % cfg.get("ssid"))
    return False


def open_setup_ap(cfg):
    """Switch to setup mode and open the access point with a captive portal."""
    portal.SETUP_MODE = True
    if network is None:
        return
    portal.start_ap(cfg.get("ap_ssid"), cfg.get("ap_password"))
    print("boot: setup mode -- connect to the access point and open http://%s/"
          % portal.AP_IP)


def main():
    cfg = load_credentials()
    if not portal.is_configured(cfg):
        print("boot: no WiFi configured yet (%s missing or flag not set) -- opening the "
              "setup access point" % CONFIG_FILE)
        open_setup_ap(cfg)
        return
    print("boot: credentials loaded (%s)" % ", ".join(sorted(cfg)))
    if not connect(cfg):
        # Reachable fallback: the user can fix the configuration over the portal
        # instead of having to reach the board by cable.
        open_setup_ap(cfg)


try:
    main()
except Exception as exc:  # noqa: BLE001 -- boot must never abort
    print("boot: error: %s: %s" % (type(exc).__name__, exc))
