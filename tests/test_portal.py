"""Host tests for portal.py: setup mode, DNS hijack answers and captive portal
detection. These are pure functions -- no hardware needed.

Call: python3 tests/test_portal.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEVICE = os.path.join(os.path.dirname(HERE), "firmware", "device")
FIRMWARE = os.path.join(os.path.dirname(HERE), "firmware", "mcpsrv")
sys.path.insert(0, DEVICE)
sys.path.insert(0, FIRMWARE)

import mcp_httpd as httpd      # noqa: E402
import portal                  # noqa: E402

FAILURES = []
CHECKS = [0]


def check(name, condition, detail=""):
    CHECKS[0] += 1
    if condition:
        print("  ok   %s" % name)
    else:
        print("  FAIL %s %s" % (name, detail))
        FAILURES.append(name)


def query(name, qtype=1, ident=b"\x12\x34"):
    """Build a DNS query for `name` (simple, uncompressed QNAME)."""
    parts = b"".join(bytes([len(part)]) + part.encode() for part in name.split("."))
    return (ident + b"\x01\x00" + b"\x00\x01" + b"\x00\x00" + b"\x00\x00" + b"\x00\x00"
            + parts + b"\x00" + bytes([qtype >> 8, qtype & 0xFF]) + b"\x00\x01")


def test_dns():
    print("DNS hijack answer")
    antwort = portal.dns_answer(query("example.com"))
    check("Antwort vorhanden", antwort is not None)
    check("Antwort-Flag gesetzt", antwort[2] == 0x81 and antwort[3] == 0x80)
    check("eine Frage", antwort[4:6] == b"\x00\x01")
    check("eine Antwort", antwort[6:8] == b"\x00\x01")
    check("Absender-Id uebernommen", antwort[0:2] == b"\x12\x34")
    check("A-Record-Typ", antwort[-16:-10] == b"\xc0\x0c\x00\x01\x00\x01",
          repr(antwort[-16:-10]))
    check("Adresse ist die AP-Adresse", antwort[-4:] == bytes([192, 168, 4, 1]),
          repr(antwort[-4:]))
    check("Laengenfeld der Adresse", antwort[-6:-4] == b"\x00\x04")
    frage = query("example.com")
    check("Frage unveraendert uebernommen", frage[12:-4] in antwort)

    # IPv6 (AAAA) is not hijacked, but answered with zero records
    aaaa = portal.dns_answer(query("example.com", qtype=28))
    check("AAAA ohne Antworten", aaaa is not None and aaaa[6:8] == b"\x00\x00")
    check("Antwort wird nicht beantwortet", portal.dns_answer(b"\x12\x34" + b"\x81\x80" + b"\x00" * 8) is None)
    check("zu kurzes Paket", portal.dns_answer(b"\x00\x01") is None)
    check("keine Frage", portal.dns_answer(b"\x12\x34\x01\x00" + b"\x00\x00" + b"\x00" * 8) is None)
    check("kaputtes Namensfeld", portal.dns_answer(b"\x12\x34\x01\x00\x00\x01" + b"\x00" * 6 + b"\x09") is None)
    check("unsinnige Adresse", portal.dns_answer(query("a.b"), "") is None)


def test_probe():
    print("Captive portal detection")


    def request(path, host):
        return httpd.Request("GET", path, {}, {"host": host} if host else {}, b"")

    for path in portal.PROBE_PATHS:
        check("Probe %s" % path, portal.is_captive_probe(request(path, "192.168.4.1")))
    check("normale Anfrage auf der AP-Adresse",
          not portal.is_captive_probe(request("/setup", "192.168.4.1")))
    check("fremder Hostname ist ein Probe",
          portal.is_captive_probe(request("/", "connectivitycheck.gstatic.com")))
    check("fremder Hostname mit Port", portal.is_captive_probe(request("/x", "example.com:80")))
    check("mDNS-Name ist kein Probe", not portal.is_captive_probe(request("/", "board.local")))
    check("kein Host-Header", not portal.is_captive_probe(request("/setup", "")))
    check("Gross-/Kleinschreibung", portal.is_captive_probe(request("/GENERATE_204", "192.168.4.1")))
    check("Query ignoriert", portal.is_captive_probe(request("/generate_204?x=1", "192.168.4.1")))


def test_setup_mode():
    print("Setup mode")
    check("AP-Adresse", portal.AP_IP == "192.168.4.1")
    check("Standard-SSID", portal.AP_SSID_DEFAULT == "ESP32-Setup")
    check("Setup-URL", portal.SETUP_URL == "http://192.168.4.1/setup")

    check("leere Konfiguration", not portal.is_configured({}))
    check("ohne SSID", not portal.is_configured({"configured": True}))
    check("ohne Flag", not portal.is_configured({"ssid": "Netz"}))
    check("konfiguriert", portal.is_configured({"configured": True, "ssid": "Netz"}))

    response = portal.redirect_to_setup(httpd.Request("GET", "/generate_204", {},
                                                     {"host": "example.com"}, b""))
    check("Umleitung mit Status 302", response.status == 302, str(response.status))
    check("Ziel im Location-Kopf", response.headers.get("Location") == portal.SETUP_URL,
          str(response.headers))
    check("Umleitung nicht zwischenspeichern",
          response.headers.get("Cache-Control") == "no-store")
    body = response.body.decode() if isinstance(response.body, bytes) else response.body
    check("HTML verweist auf die Konfigseite", portal.SETUP_URL in body)
    check("Host-Test ohne Hardware: kein network-Import auf Modulebene",
          "network" not in vars(portal))
    check("Lesehilfe fuer die Weboberflaeche vorhanden",
          callable(portal.redirect_to_setup))


def main():
    test_dns()
    test_probe()
    test_setup_mode()
    print()
    if FAILURES:
        print("%d of %d checks failed:" % (len(FAILURES), CHECKS[0]))
        for name in FAILURES:
            print("   - %s" % name)
        return 1
    print("all %d checks passed" % CHECKS[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
