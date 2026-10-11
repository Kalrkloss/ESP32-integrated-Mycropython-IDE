"""Host test for boot.py: merging of the credentials.

Important, because a mistake here cuts the board off the network -- and then the
debug server is no longer reachable either. Run: python3 tests/test_boot.py
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


def write(name, data):
    with open(name, "w") as fh:
        json.dump(data, fh)


def main():
    tmp = tempfile.mkdtemp(prefix="boot-test-")
    old = os.getcwd()
    os.chdir(tmp)
    sys.path.insert(0, DEVICE)
    try:
        import boot
        import portal

        # only wifi.json present
        write("wifi.json", {"ssid": "Old", "password": "Old-PW", "hostname": "old-name"})
        cfg = boot.load_credentials()
        check("wifi.json alone is read", cfg and cfg["ssid"] == "Old", str(cfg))
        check("password is included", cfg["password"] == "Old-PW")

        # config.json without SSID -> wifi.json fills in
        write("config.json", {"ssid": "", "password": "", "brightness": 55})
        cfg = boot.load_credentials()
        check("empty SSID -> legacy data applies", cfg and cfg["ssid"] == "Old", str(cfg))
        check("empty password -> legacy data applies", cfg["password"] == "Old-PW")

        # config.json with SSID -> wins
        write("config.json", {"ssid": "New", "password": "New-PW", "hostname": "new-name"})
        cfg = boot.load_credentials()
        check("config.json wins for SSID", cfg["ssid"] == "New")
        check("config.json wins for hostname", cfg["hostname"] == "new-name")
        check("config.json wins for password", cfg["password"] == "New-PW")

        # broken file must not prevent startup
        with open("config.json", "w") as fh:
            fh.write("{broken")
        cfg = boot.load_credentials()
        check("broken config.json is skipped", cfg and cfg["ssid"] == "Old", str(cfg))

        os.remove("config.json")
        os.remove("wifi.json")
        check("no credentials without files", boot.load_credentials() == {})

        # connect must not crash without a WiFi module (host test); a failed
        # connection opens the setup access point so the board stays reachable.
        check("connect without module returns False", boot.connect({"ssid": "x"}) is False)
        check("connect without configuration returns False", boot.connect(None) is False)
        check("unconfigured board is in setup mode", portal.SETUP_MODE is True)
        check("unconfigured board has no credentials",
              not portal.is_configured(boot.load_credentials()))
    finally:
        os.chdir(old)
        shutil.rmtree(tmp, ignore_errors=True)

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
