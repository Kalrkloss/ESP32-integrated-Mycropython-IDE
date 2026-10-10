#!/usr/bin/env python3
"""Start every example application on the board and check that it renders.

For each application: point config.json at it, power cycle the board, wait for the
loader's log line, then fetch the framebuffer and make sure something was drawn. A
blank screen or an error in the log is reported.

Call: python3 tools/apps_smoke.py            (all applications)
      python3 tools/apps_smoke.py snake 2048 (selected ones)
"""

import json
import subprocess
import sys
import time
import urllib.request

BOARD = "http://192.168.1.168"
HUB = "1-4.4"
POWER_PORT = "3"
CONFIG = {"configured": True, "board": "JC3248W535", "hostname": "esp32-debug",
          "display": {"brightness": 65}}


def http(path, method="GET", body=None, timeout=25):
    request = urllib.request.Request(BOARD + path, method=method)
    if body is not None:
        request.data = body if isinstance(body, bytes) else json.dumps(body).encode()
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def power_cycle():
    subprocess.run(["uhubctl", "-l", HUB, "-p", POWER_PORT, "-a", "cycle", "-d", "2"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def wait_for_board(seconds=60):
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            http("/api/state", timeout=4)
            return True
        except Exception:  # noqa: BLE001
            time.sleep(2)
    return False


def logs():
    """The device answers with plain text lines, one entry per line."""
    return http("/api/log", timeout=8).decode("utf-8", "replace").splitlines()


def set_app(name):
    payload = dict(CONFIG, app=name)
    http("/api/file?path=/config.json", "POST", json.dumps(payload).encode())


def check(name):
    """Returns (ok, detail, signature)."""
    set_app(name)
    power_cycle()
    if not wait_for_board():
        return False, "board did not come up", 0
    deadline = time.time() + 45
    started = False
    while time.time() < deadline:
        text = "\n".join(logs())
        if "app_loader: started %s" % name in text:
            started = True
            break
        if "could not start %s" % name in text:
            return False, "loader reported an error", 0
        time.sleep(2)
    if not started:
        return False, "no 'started' line within 45 s", 0
    time.sleep(2)                       # let the first frame be drawn
    raw = http("/screen.raw?scale=4", timeout=25)
    non_black = sum(1 for i in range(0, len(raw) - 1, 2) if raw[i] or raw[i + 1])
    text = "\n".join(logs())
    problem = [part for part in ("Traceback", "could not start", "failed") if part in text]
    if problem:
        return False, "log contains %s" % problem, 0
    if non_black < len(raw) // 20:
        return False, "screen looks blank (%d of %d bytes non black)" % (non_black, len(raw)), 0
    signature = sum(raw[i] * (i % 251) for i in range(0, len(raw), 2)) % (1 << 32)
    return True, "%d non-black samples, signature %08x" % (non_black, signature), signature


def main():
    names = sys.argv[1:]
    if not names:
        names = ["launcher", "snake", "minesweeper", "sokoban", "calculator",
                 "clock", "game2048", "tic_tac_toe"]
    failures = []
    signatures = {}
    for name in names:
        ok, detail, signature = check(name)
        print("%-14s %s  %s" % (name, "ok  " if ok else "FAIL", detail), flush=True)
        if not ok:
            failures.append(name)
        else:
            signatures.setdefault(signature, []).append(name)
    # Two applications drawing exactly the same pixels would mean one of them never
    # built its own screen.
    same = {sig: group for sig, group in signatures.items() if len(group) > 1}
    if same:
        print("FAIL identical screens: %s" % list(same.values()))
        failures.extend([name for group in same.values() for name in group[1:]])
    # leave the board on the launcher
    set_app("launcher")
    power_cycle()
    wait_for_board()
    print()
    if failures:
        print("%d of %d applications failed: %s" % (len(failures), len(names), failures))
        return 1
    print("all %d applications started and rendered" % len(names))
    return 0


if __name__ == "__main__":
    sys.exit(main())
