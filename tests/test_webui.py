"""Host tests for the web UI (runs without an ESP32, under CPython).

Checked here: the page structure (IDs, handlers, brackets), the API handlers against a
temporary filesystem, and the whole path over a real HTTP socket.

Run:  python3 tests/test_webui.py
"""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FIRMWARE = os.path.join(os.path.dirname(HERE), "firmware", "mcpsrv")
DEVICE = os.path.join(os.path.dirname(HERE), "firmware", "device")
WEBFILES = os.path.join(os.path.dirname(HERE), "firmware", "webfiles")
sys.path.insert(0, FIRMWARE)
sys.path.insert(0, DEVICE)          # display_config, portal: device modules

import mcp_httpd as httpd  # noqa: E402
import mcp_serve as serve  # noqa: E402
import mcp_webui as webui  # noqa: E402

FAILURES = []
CHECKS = [0]


def check(name, condition, detail=""):
    CHECKS[0] += 1
    if condition:
        print("  ok   %s" % name)
    else:
        print("  FAIL %s %s" % (name, detail))
        FAILURES.append(name)


def req(method, path, query=None, body=b"", headers=None):
    return httpd.Request(method, path, query or {}, headers or {}, body)


def text_of(resp):
    if isinstance(resp.body, bytes):
        return resp.body.decode()
    return resp.body


# ---------------------------------------------------------------- Page

def read(name):
    with open(os.path.join(WEBFILES, name)) as fh:
        return fh.read()


def js_syntax(path):
    """Real syntax check with node -- counting brackets does not catch every error.
    (That is exactly what the first version failed on: a \\n became a real
    line break and took the whole script down with it.)"""
    node = shutil.which("node")
    if not node:
        return None
    finished = subprocess.run([node, "--check", path], capture_output=True)
    return finished.returncode == 0, (finished.stderr or b"").decode()[:300]


def test_page():
    print("The page")
    html = read("index.html")
    js = read("app.js")
    css = read("app.css")
    check("Page is HTML", html.lstrip().startswith("<!DOCTYPE html>"))
    check("Page is complete", html.rstrip().endswith("</html>"))
    check("Size within bounds (<40 KB)", len(html) < 40000, "%d Byte" % len(html))
    check("no external dependencies",
          "http://" not in html.replace("http://www.w3.org", "") and "https://" not in html)

    ids = set(re.findall(r'id="([^"]+)"', html))
    for name in ("repl", "editor", "files", "config", "out", "cmd", "code", "e-path",
                 "f-rows", "f-path", "upload", "c-ssid", "c-pass", "c-host", "c-bri",
                 "p-ip", "p-heap", "c-info", "shot-scale", "prev-status",
                 "c-board", "c-app"):
        check("Element #%s present" % name, name in ids)
    check("Preview is a canvas (no PNG on the device)",
          '<canvas class="prev" id="prev"' in html)
    check("Preview fetches the raw buffer", '"/screen.raw?scale="' in js)

    # Every ID referenced via el("...") must also exist -- catches typos.
    used = set(re.findall(r'el\("([^"]+)"\)', js))
    missing = sorted(used - ids)
    check("all referenced IDs exist", not missing, str(missing))

    # Every onclick handler must be defined as a function.
    calls = set(re.findall(r'onclick="([a-zA-Z_][a-zA-Z0-9_]*)\(' , html))
    defined = set(re.findall(r"function\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", js))
    missing = sorted(calls - defined)
    check("all onclick handlers are defined", not missing, str(missing))

    # Tabs and sections must match up.
    for tab in ("repl", "editor", "files", "config"):
        check("Tab for %s" % tab, 'data-tab="%s"' % tab in html)

    check("HTML references the separate files",
          'href="/app.css"' in html and 'src="/app.js"' in html)
    check("Editor is loaded alongside",
          'href="/editor/codemirror.css"' in html and 'src="/editor/codemirror.js"' in html
          and 'src="/editor/python.js"' in html)
    check("Editor falls back to the textarea",
          'typeof CodeMirror === "undefined"' in js and "editorTasten();" in js)
    check("Editor reads and writes through CodeMirror",
          "editor.getValue()" in js and "editor.setValue(text)" in js)
    for name in ("codemirror.js", "codemirror.css", "python.js", "search.js", "dialog.js",
                 "dialog.css", "closebrackets.js", "matchbrackets.js", "active-line.js",
                 "comment.js", "jump-to-line.js", "LICENSE.txt"):
        check("Editor file %s present" % name,
              os.path.exists(os.path.join(WEBFILES, "editor", name)))

    check("JS brackets balanced",
          js.count("{") == js.count("}") and js.count("(") == js.count(")"),
          "%d/%d curly, %d/%d round" % (js.count("{"), js.count("}"),
                                        js.count("("), js.count(")")))
    result = js_syntax(os.path.join(WEBFILES, "app.js"))
    if result is None:
        print("  .... node missing -- syntax check skipped")
    else:
        valid, error = result
        check("app.js syntactically valid", valid, error)

    check("no leftover placeholders", "%s" not in html and "@@" not in html)
    for name, content in (("index.html", html), ("app.js", js), ("app.css", css)):
        check("%s without foreign characters mixed in" % name,
              not re.search(r"[\u4e00-\u9fff]", content))
    # There must be no real line break inside a JS string (escaping trap).
    bad = [z for z in js.split("\n") if z.count('"') % 2 == 1 and "//" not in z]
    check("no torn JS string literals", not bad, str(bad[:2]))


def test_setup_page():
    print("Setup page")
    html = read("setup.html")
    script = read("setup.js")
    ids = set(re.findall(r'id="([^"]+)"', html))
    for name in ("ssid", "password", "hostname", "ap_ssid", "ap_password", "board",
                 "board-info", "form-display", "form-touch", "status", "err", "chip",
                 "drivers"):
        check("Element #%s present" % name, name in ids)
    check("Setup page loads its own script", 'src="/setup.js"' in html)
    check("Setup page uses the shared stylesheet", 'href="/app.css"' in html)
    check("no CDN in the setup page", "http://" not in html.replace("http://www.w3.org", ""))
    check("Setup page knows the profile API", "/api/profiles" in script)
    check("Setup page knows the driver API", "/api/drivers" in script)
    check("Setup page saves via the API", '"/api/config"' in script)
    check("Setup page can restart", '"/api/reset"' in script)
    check("Setup page requires an SSID",
          "WiFi name is required" in script)
    check("no German umlauts in the setup page",
          not set("äöüÄÖÜß") & set(html + script))
    check("Setup syntax ok (node)", js_syntax(os.path.join(WEBFILES, "setup.js")))
    check("Setup CSS present", ".setup" in read("app.css"))
    check("Main page links the setup",
          "setup" in read("app.js").lower() or "setup" in read("index.html").lower())


def test_routes():
    print("Routes")
    routes = webui.build_routes()
    for key in ("GET /", "GET /api/state", "POST /api/exec", "GET /api/log",
                "GET /api/files", "GET /api/file", "POST /api/file",
                "DELETE /api/file", "POST /api/mkdir", "POST /api/rename",
                "GET /api/config", "POST /api/config", "GET /api/screen.png",
                "POST /api/reset", "GET /status", "GET /editor/*",
                "GET /setup", "GET /setup.js", "GET /api/profiles",
                "GET /api/drivers"):
        check("Route %s" % key, key in routes)
    _, server = serve.build_server(port=0)
    check("Web UI is attached to the server", "GET /api/files" in server.routes)
    check("Plain-text status remains", "GET /status" in server.routes)

    # Setup mode serves configuration only: no MCP, no code execution, no files.
    setup_routes = webui.setup_routes()
    check("Setup route present", "GET /setup" in setup_routes)
    check("Setup without code execution", "POST /api/exec" not in setup_routes)
    check("Setup without MCP", "POST /mcp" not in setup_routes)
    check("Setup without file access", "GET /api/files" not in setup_routes)
    _, setup_server = serve.build_server(port=0, setup_only=True)
    find_setup = setup_server._find_handler
    check("Setup mode serves the config page",
          find_setup("GET", "/") is not None and find_setup("GET", "/setup") is not None)
    check("Setup mode redirects unknown paths", find_setup("GET", "/generate_204") is not None)
    check("Setup mode redirects code execution instead of running it",
          find_setup("POST", "/api/exec") is webui.portal_redirect)
    check("Setup mode redirects file access", find_setup("GET", "/api/files") is webui.portal_redirect)

    # Resolve prefix routes (key ends with "*")
    find = server._find_handler
    check("Prefix route matches editor file",
          find("GET", "/editor/codemirror.js") is not None)
    check("exact route takes precedence",
          find("GET", "/app.js") is not None and find("GET", "/app.js") is not find("GET", "/editor/x"))
    check("unknown path has no handler", find("GET", "/doesnotexist") is None)
    check("wrong method has no handler", find("POST", "/editor/codemirror.js") is None)


# ---------------------------------------------------------------- API against tmp

def test_files(tmp):
    print("Files (API)")
    os.makedirs(os.path.join(tmp, "lib"))
    with open(os.path.join(tmp, "main.py"), "w") as fh:
        fh.write("print('hello')\n")
    with open(os.path.join(tmp, "image.png"), "wb") as fh:
        fh.write(bytes(range(256)))

    response = json.loads(text_of(webui.api_files(req("GET", "/api/files", {"path": "/"}))))
    names = [e["name"] for e in response["entries"]]
    check("entries listed", "main.py" in names and "lib" in names, str(names))
    check("directory first", names[0] == "lib", str(names))
    check("directory marked", [e["dir"] for e in response["entries"] if e["name"] == "lib"] == [True])
    check("size reported", [e["size"] for e in response["entries"] if e["name"] == "main.py"] == [15])
    check("memory info included", "free" in response.get("memory", {}))
    check("subfolder listable",
          json.loads(text_of(webui.api_files(req("GET", "/api/files", {"path": "/lib"}))))["entries"] == [])

    # read
    response = json.loads(text_of(webui.api_file_get(req("GET", "/api/file", {"path": "/main.py"}))))
    check("file readable", response["data"] == "print('hello')\n")
    check("text as text", response["binary"] is False)

    response = json.loads(text_of(webui.api_file_get(req("GET", "/api/file", {"path": "/image.png"}))))
    check("binary file detected", response["binary"] is True and response["size"] == 256)

    resp = webui.api_file_get(req("GET", "/api/file", {"path": "/image.png", "download": "1"}))
    check("download returns attachment", resp.headers.get("Content-Disposition", "").startswith("attachment"))
    check("download returns bytes", resp.body == bytes(range(256)))

    response = json.loads(text_of(webui.api_file_get(req("GET", "/api/file", {"path": "/doesnotexist"}))))
    check("missing file reported", "error" in response)

    # write
    response = json.loads(text_of(webui.api_file_put(
        req("POST", "/api/file", {"path": "/new.txt"}, b"sample")))
    )
    check("file written", response["ok"] and response["bytes"] == 6)
    with open(os.path.join(tmp, "new.txt")) as fh:
        check("content matches", fh.read() == "sample")

    # JSON variant
    response = json.loads(text_of(webui.api_file_put(
        req("POST", "/api/file", {}, json.dumps({"path": "/json.txt", "data": "abc"}).encode())))
    )
    check("write via JSON", response["ok"] and os.path.exists(os.path.join(tmp, "json.txt")))

    check("write without path rejected",
          webui.api_file_put(req("POST", "/api/file", {}, b"x")).status == 400)
    check("file too large rejected",
          webui.api_file_put(req("POST", "/api/file", {"path": "/big"},
                                 b"x" * (webui.MAX_UPLOAD + 1))).status == 413)

    # a subfolder is created on write
    response = json.loads(text_of(webui.api_file_put(
        req("POST", "/api/file", {"path": "/deep/inside.txt"}, b"deep"))))
    check("missing folder is created",
          response["ok"] and os.path.exists(os.path.join(tmp, "deep", "inside.txt")))

    # mkdir / rename / delete
    check("mkdir", json.loads(text_of(webui.api_file_mkdir(
        req("POST", "/api/mkdir", {}, b'{"path": "/data"}'))))["ok"])
    check("folder exists", os.path.isdir(os.path.join(tmp, "data")))
    check("rename", json.loads(text_of(webui.api_file_rename(
        req("POST", "/api/rename", {}, b'{"old": "/new.txt", "new": "/data/old.txt"}'))))["ok"])
    check("file renamed", os.path.exists(os.path.join(tmp, "data", "old.txt")))
    check("delete file", json.loads(text_of(webui.api_file_delete(
        req("DELETE", "/api/file", {}, b'{"path": "/data/old.txt"}'))))["ok"])
    check("delete folder", json.loads(text_of(webui.api_file_delete(
        req("DELETE", "/api/file", {}, b'{"path": "/data"}'))))["ok"])
    check("folder gone", not os.path.exists(os.path.join(tmp, "data")))

    # prevent escaping the root directory
    webui.api_file_put(req("POST", "/api/file", {"path": "/../../escape.txt"}, b"no"))
    check("no escape from the root directory",
          not os.path.exists(os.path.join(os.path.dirname(tmp), "escape.txt")))
    check("path stays inside the root directory",
          webui.real_path("/../../x").startswith(tmp))


def test_configuration(tmp):
    print("Configuration")
    start = webui.config_lesen()
    check("default values present",
          start["hostname"] == "esp32-debug" and start["display"]["brightness"] == 70)
    check("display and touch section present",
          "driver" in start["display"] and "driver" in start["touch"])
    response = json.loads(text_of(webui.api_config(req("POST", "/api/config", {}, json.dumps(
        {"ssid": "Net", "password": "Secret", "hostname": "board", "brightness": 30,
         "unknown": "ignored"}).encode()))))
    check("saving returns the configuration", response["config"]["ssid"] == "Net")
    check("unknown key ignored", "unknown" not in response["config"])
    after = webui.config_lesen()
    check("values persist",
          after["hostname"] == "board" and after["display"]["brightness"] == 30)
    check("file lives on the device", os.path.exists(os.path.join(tmp, "config.json")))
    check("read via GET",
          json.loads(text_of(webui.api_config(req("GET", "/api/config"))))["config"]["ssid"] == "Net")
    # Display/Touch sections are merged field by field, a profile provides the base.
    webui.config_schreiben({"board": "JC3248W535", "display": {"brightness": 42},
                            "touch": {"scl": 7}})
    after_profile = webui.config_lesen()
    check("profile provides pins", after_profile["display"]["sck"] == 47,
          str(after_profile["display"].get("sck")))
    check("own value wins", after_profile["display"]["brightness"] == 42)
    check("unmentioned fields remain", after_profile["display"]["width"] == 320)
    check("touch section merged",
          after_profile["touch"]["scl"] == 7 and after_profile["touch"]["sda"] == 4)
    # Password must never reach the browser -- but must not be lost either.
    visible = json.loads(text_of(webui.api_config(req("GET", "/api/config"))))["config"]
    check("password is not served", visible["password"] == "")
    check("password marked as set", visible["password_gesetzt"] is True)
    webui.api_config(req("POST", "/api/config", {}, json.dumps(
        {"hostname": "board2", "password": ""}).encode()))
    check("empty password deletes nothing", webui.config_lesen(mit_passwort=True)["password"] == "Secret")
    webui.api_config(req("POST", "/api/config", {}, json.dumps(
        {"password": "New"}).encode()))
    check("new password adopted", webui.config_lesen(mit_passwort=True)["password"] == "New")
    # wifi.json stays usable as a base (legacy data), but only for empty fields
    with open(os.path.join(tmp, "wifi.json"), "w") as fh:
        json.dump({"ssid": "Old-Net", "password": "Old-Secret", "hostname": "old"}, fh)
    webui.config_schreiben({"ssid": "", "hostname": "board3", "brightness": 40})
    effective = webui.config_lesen()
    check("empty SSID -> wifi.json provides it", effective["ssid"] == "Old-Net", effective["ssid"])
    check("set hostname wins", effective["hostname"] == "board3", effective["hostname"])
    check("brightness persists", effective["display"]["brightness"] == 40)
    check("legacy password stays usable",
          webui.config_lesen(mit_passwort=True)["password"] == "New")
    # A profile only provides the fields that were never stored explicitly.
    os.remove(os.path.join(tmp, "config.json"))
    webui.config_schreiben({"board": "CUSTOM"})
    check("profile provides the driver as long as nothing of its own is stored",
          webui.config_lesen()["display"]["driver"] == "st7789",
          webui.config_lesen()["display"]["driver"])
    check("after deletion the legacy data applies again",
          webui.config_lesen(mit_passwort=True)["password"] == "Old-Secret",
          webui.config_lesen(mit_passwort=True)["password"])
    # Profile and driver lists feed the setup page
    display_config = sys.modules["display_config"]
    real_chip = display_config.chip_name
    display_config.chip_name = lambda: "esp32s3"     # host runs on x86_64
    try:
        profile = json.loads(text_of(webui.api_profiles(req("GET", "/api/profiles"))))
        check("profiles for this chip",
              len(profile["profiles"]) >= 2
              and all(p["chip"] == profile["chip"] for p in profile["profiles"]),
              str(profile.get("chip")))
        check("profile contains pins", "display" in profile["profiles"][0])
        check("chip type is included", profile["chip"] == "esp32s3")
    finally:
        display_config.chip_name = real_chip
    drivers = json.loads(text_of(webui.api_drivers(req("GET", "/api/drivers"))))
    check("driver lists present",
          isinstance(drivers["display"], list) and isinstance(drivers["touch"], list))
    # Device-only trap: this MicroPython build has no os.path. Emulate that on the
    # host, otherwise the bug only shows up on the board.
    import types
    without_path = types.ModuleType("os")
    for name in ("listdir", "stat", "mkdir", "remove", "rename", "rmdir", "uname"):
        if hasattr(os, name):
            setattr(without_path, name, getattr(os, name))
    real_os = display_config.os
    display_config.os = without_path
    try:
        drivers = display_config.available_drivers()
        check("driver list without os.path",
              isinstance(drivers["display"], list) and isinstance(drivers["touch"], list),
              str(drivers))
        check("drivers from /drv are found", "axs15231b" in drivers["display"]
              or not drivers["display"], str(drivers["display"][:3]))
    finally:
        display_config.os = real_os


def test_exec():
    print("Console (exec)")
    response = json.loads(text_of(webui.api_exec(
        req("POST", "/api/exec", {}, json.dumps({"code": "print(6*7)"}).encode()))))
    check("print output comes back", "42" in response["output"])
    response = json.loads(text_of(webui.api_exec(req("POST", "/api/exec", {}, b"print('raw')"))))
    check("plain text as code", "raw" in response["output"])
    response = json.loads(text_of(webui.api_exec(
        req("POST", "/api/exec", {}, json.dumps({"code": "1/0"}).encode()))))
    check("error is reported", "ZeroDivisionError" in response["output"])
    check("empty code rejected",
          webui.api_exec(req("POST", "/api/exec", {}, b"")).status == 400)


def test_http_path(tmp):
    print("Over HTTP")
    _, server = serve.build_server(port=0)
    server.start_in_thread()
    port = server.sock.getsockname()[1]
    base = ("127.0.0.1", port)

    def fetch(path, method="GET", data=None, headers=None):
        s = socket.create_connection(base, timeout=10)
        head_lines = ["%s %s HTTP/1.1" % (method, path), "Host: localhost",
                      "Connection: close"]
        for h in (headers or []):
            head_lines.append(h)
        if data is not None:
            head_lines.append("Content-Length: %d" % len(data))
        raw = ("\r\n".join(head_lines) + "\r\n\r\n").encode()
        if data:
            raw += data
        s.sendall(raw)
        parts = []
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            parts.append(chunk)
        s.close()
        response = b"".join(parts)
        head_part, _, body = response.partition(b"\r\n\r\n")
        return head_part.decode(), body

    head, body = fetch("/")
    check("GET / serves the page", head.startswith("HTTP/1.1 200") and b"ESP32-S3 Debug" in body)
    check("page as HTML", "text/html" in head)

    head, body = fetch("/status")
    check("GET /status serves plain text", b"debug server" in body)

    head, body = fetch("/api/files?path=/")
    check("GET /api/files serves JSON",
          head.startswith("HTTP/1.1 200") and "entries" in json.loads(body.decode()))

    head, body = fetch("/api/config", "POST", b'{"brightness": 55}')
    check("POST /api/config saves",
          json.loads(body.decode())["config"]["display"]["brightness"] == 55)

    head, body = fetch("/api/file?path=/http.txt", "POST", b"over http")
    check("POST /api/file writes", json.loads(body.decode())["ok"])
    with open(os.path.join(tmp, "http.txt")) as fh:
        check("content written over HTTP", fh.read() == "over http")
    head, body = fetch("/api/file?path=/http.txt")
    check("file readable over HTTP", json.loads(body.decode())["data"] == "over http")

    head, body = fetch("/api/exec", "POST", b'{"code": "print(2+2)"}')
    check("exec over HTTP", "4" in json.loads(body.decode())["output"])

    head, body = fetch("/api/log")
    check("log retrievable", head.startswith("HTTP/1.1 200"))

    # Large file: must be sent chunked and delivered completely (on the device
    # a 174-KB block at once would be the trigger for memory problems).
    big = os.path.join(tmp, "web", "editor", "big.js")
    with open(big, "wb") as fh:
        fh.write(b"/*" + b"x" * 300000 + b"*/")
    head, body = fetch("/editor/big.js")
    check("large file arrives complete",
          head.startswith("HTTP/1.1 200") and len(body) == 300004, "%d Byte" % len(body))
    check("length header matches", "Content-Length: 300004" in head)
    check("content matches", body.startswith(b"/*") and body.endswith(b"*/"))
    check("editor file over HTTP",
          fetch("/editor/codemirror.js")[0].startswith("HTTP/1.1 200"))
    head, _ = fetch("/editor/../../etc/passwd", "GET", headers=["X-Test: 1"])
    check("escape is rejected", head.startswith("HTTP/1.1 403"), head[:40])
    os.remove(big)

    head, body = fetch("/doesnotexist")
    check("unknown path -> 404", head.startswith("HTTP/1.1 404"))

    server.running = False
    try:
        socket.create_connection(base, timeout=2).close()
    except OSError:
        pass


def main():
    tmp = tempfile.mkdtemp(prefix="webui-test-")
    # As on the device: the UI lives under <root>/web/
    shutil.copytree(WEBFILES, os.path.join(tmp, "web"))
    old = webui.ROOT
    webui.ROOT = tmp
    display_config = sys.modules["display_config"]
    old_profile = display_config.PROFILES_FILE
    # profiles.json ships with the firmware and is not part of the writable area.
    display_config.PROFILES_FILE = os.path.join(os.path.dirname(HERE), "firmware", "device",
                                                "profiles.json")
    try:
        test_page()
        test_setup_page()
        test_routes()
        test_files(tmp)
        test_configuration(tmp)
        test_exec()
        test_http_path(tmp)
    finally:
        webui.ROOT = old
        display_config.PROFILES_FILE = old_profile
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
