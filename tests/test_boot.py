"""Host-Test fuer boot.py: Zusammenfuehrung der Zugangsdaten.

Wichtig, weil ein Fehler hier das Board vom Netz trennt -- und dann ist auch der
Debug-Server nicht mehr erreichbar. Aufruf: python3 tests/test_boot.py
"""

import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEVICE = os.path.join(os.path.dirname(HERE), "firmware", "device")
sys.path.insert(0, DEVICE)

FAILURES = []
CHECKS = [0]


def check(name, condition, detail=""):
    CHECKS[0] += 1
    if condition:
        print("  ok   %s" % name)
    else:
        print("  FAIL %s %s" % (name, detail))
        FAILURES.append(name)


def schreibe(name, daten):
    with open(name, "w") as fh:
        json.dump(daten, fh)


def main():
    tmp = tempfile.mkdtemp(prefix="boot-test-")
    alt = os.getcwd()
    os.chdir(tmp)
    sys.path.insert(0, DEVICE)
    try:
        import boot

        # nur wifi.json vorhanden
        schreibe("wifi.json", {"ssid": "Alt", "password": "Alt-PW", "hostname": "alt-name"})
        cfg = boot._load_config()
        check("wifi.json allein wird gelesen", cfg and cfg["ssid"] == "Alt", str(cfg))
        check("Passwort kommt mit", cfg["password"] == "Alt-PW")

        # config.json ohne SSID -> wifi.json fuellt
        schreibe("config.json", {"ssid": "", "password": "", "brightness": 55})
        cfg = boot._load_config()
        check("leere SSID -> Altbestand greift", cfg and cfg["ssid"] == "Alt", str(cfg))
        check("leeres Passwort -> Altbestand greift", cfg["password"] == "Alt-PW")

        # config.json mit SSID -> gewinnt
        schreibe("config.json", {"ssid": "Neu", "password": "Neu-PW", "hostname": "neu-name"})
        cfg = boot._load_config()
        check("config.json gewinnt bei SSID", cfg["ssid"] == "Neu")
        check("config.json gewinnt bei Hostname", cfg["hostname"] == "neu-name")
        check("config.json gewinnt bei Passwort", cfg["password"] == "Neu-PW")

        # kaputte Datei darf den Start nicht verhindern
        with open("config.json", "w") as fh:
            fh.write("{kaputt")
        cfg = boot._load_config()
        check("kaputte config.json wird uebersprungen", cfg and cfg["ssid"] == "Alt", str(cfg))

        os.remove("config.json")
        os.remove("wifi.json")
        check("ohne Dateien kein WLAN", boot._load_config() is None)

        # connect darf ohne WLAN-Modul nicht abstuerzen (Host-Test)
        check("connect ohne Modul liefert False", boot.connect({"ssid": "x"}) is False)
        check("connect ohne Konfiguration liefert False", boot.connect(None) is False)
    finally:
        os.chdir(alt)
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILURES:
        print("%d von %d Pruefungen fehlgeschlagen:" % (len(FAILURES), CHECKS[0]))
        for name in FAILURES:
            print("   - %s" % name)
        return 1
    print("alle %d Pruefungen bestanden" % CHECKS[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
