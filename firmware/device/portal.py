# Setup mode: open access point, DNS hijack and captive portal redirect.
#
# Used when the board is not configured yet (no WiFi credentials, flag
# "configured" not set). The board then opens an open access point at
# 192.168.4.1, answers every DNS query with its own address and redirects any
# HTTP request to the setup page -- the usual captive portal behaviour, so a
# phone or laptop pops up the configuration page by itself.
#
# The DNS answer construction and the probe detection are pure functions so they
# can be tested on a host.

SETUP_MODE = False           # boot.py sets this; main.py branches on it
AP_IP = "192.168.4.1"
AP_NETMASK = "255.255.255.0"
AP_SSID_DEFAULT = "ESP32-Setup"
SETUP_URL = "http://" + AP_IP + "/setup"

# Paths operating systems probe to detect a captive portal
PROBE_PATHS = (
    "/generate_204", "/gen_204", "/mobile/status.php",
    "/hotspot-detect.html", "/hotspotdetect.html", "/library/test/success.html",
    "/ncsi.txt", "/connecttest.txt", "/redirect", "/canonical.html", "/success.txt",
    "/kindle-wifi/wifistub.html", "/check_network_status.txt",
)


def is_configured(cfg):
    """Configured means: a WiFi name is stored and the flag is set."""
    if not cfg:
        return False
    return bool(cfg.get("configured")) and bool(cfg.get("ssid"))


# ------------------------------------------------------------------ access point

def start_ap(ssid=None, password=None):
    """Open the access point. Returns a status string."""
    import network
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    config = {"essid": ssid or AP_SSID_DEFAULT}
    if password:
        config["password"] = password
        config["authmode"] = network.AUTH_WPA_WPA2_PSK
    else:
        config["authmode"] = network.AUTH_OPEN
    try:
        ap.config(**config)
    except (ValueError, OSError) as exc:
        print("portal: AP config failed (%s)" % exc)
    try:
        ap.ifconfig((AP_IP, AP_NETMASK, AP_IP, AP_IP))
    except (ValueError, OSError) as exc:
        print("portal: AP ifconfig failed (%s)" % exc)
    print("portal: access point %r is up, page http://%s/" % (config["essid"], AP_IP))
    return "AP %s (%s)" % (config["essid"], AP_IP)


def stop_ap():
    try:
        import network
        network.WLAN(network.AP_IF).active(False)
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------ DNS hijack

def dns_answer(query, ip=AP_IP):
    """Answer an A query with `ip`. Returns None when the packet is not a query.

    Everything else (other record types, truncated packets) gets an answer with
    zero records, which makes clients fall back to their normal resolution.
    """
    if not query or len(query) < 12:
        return None
    if query[2] & 0x80:                       # QR bit: this is a response already
        return None
    qdcount = (query[4] << 8) | query[5]
    if qdcount < 1:
        return None
    index = 12
    while index < len(query) and query[index] != 0:
        index += 1 + query[index]
    if index + 5 > len(query):
        return None
    qtype = (query[index + 1] << 8) | query[index + 2]
    question = query[12:index + 5]

    if qtype != 1:                            # only A records are hijacked
        header = query[0:2] + b"\x81\x80" + query[4:6] + b"\x00\x00" + b"\x00\x00" + b"\x00\x00"
        return header + question
    try:
        parts = bytes(int(p) for p in ip.split("."))
    except ValueError:
        return None
    header = query[0:2] + b"\x81\x80" + query[4:6] + b"\x00\x01" + b"\x00\x00" + b"\x00\x00"
    answer = (b"\xc0\x0c" + b"\x00\x01" + b"\x00\x01" + b"\x00\x00\x00\x3c"
              + b"\x00\x04" + parts)
    return header + question + answer


def start_dns_hijack(ip=AP_IP, port=53):
    """Answer DNS queries on UDP/53 in a background thread. Returns True on success."""
    try:
        import socket
        import _thread
    except ImportError as exc:
        print("portal: DNS hijack not available (%s)" % exc)
        return False

    def worker():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except Exception:  # noqa: BLE001
            pass
        try:
            sock.bind(("0.0.0.0", port))
        except OSError as exc:
            print("portal: cannot bind UDP/%d (%s)" % (port, exc))
            return
        print("portal: DNS hijack active on UDP/%d" % port)
        while True:
            try:
                data, addr = sock.recvfrom(512)
            except OSError:
                continue
            antwort = dns_answer(data, ip)
            if antwort:
                try:
                    sock.sendto(antwort, addr)
                except OSError:
                    pass

    try:
        _thread.stack_size(8192)
    except Exception:  # noqa: BLE001
        pass
    try:
        _thread.start_new_thread(worker, ())
        return True
    except Exception as exc:  # noqa: BLE001
        print("portal: DNS hijack thread failed (%s)" % exc)
        return False


# ------------------------------------------------------------------ HTTP redirect

def is_captive_probe(req, ap_ip=AP_IP):
    """True when a request looks like a captive portal probe.

    Two cases: a well known probe path, or a request addressed to a foreign host
    name (the client asked for e.g. connectivitycheck.gstatic.com but the DNS
    hijack sent it here).
    """
    path = (req.path or "").lower().split("?")[0]
    if path in PROBE_PATHS:
        return True
    host = (req.headers.get("host") or "").split(":")[0].strip().lower()
    if host and host != ap_ip and not host.endswith(".local"):
        return True
    return False


def redirect_to_setup(req, url=SETUP_URL):
    """Answer with a redirect to the setup page."""
    import mcp_httpd
    body = ('<!DOCTYPE html><html><head><meta http-equiv="refresh" content="0; url=%s">'
            "<title>Setup</title></head><body>"
            '<p>Configuration: <a href="%s">%s</a></p></body></html>' % (url, url, url))
    return mcp_httpd.Response(302, body, {"Content-Type": "text/html; charset=utf-8",
                                          "Location": url,
                                          "Cache-Control": "no-store"})
