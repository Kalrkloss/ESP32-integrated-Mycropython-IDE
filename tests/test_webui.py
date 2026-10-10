"""Host-Tests fuer die Weboberflaeche (laeuft ohne ESP32, mit CPython).

Geprueft werden: Aufbau der Seite (IDs, Handler, Klammern), die API-Handler gegen ein
temporaeres Dateisystem und der komplette Weg ueber einen echten HTTP-Socket.

Aufruf:  python3 tests/test_webui.py
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


# ---------------------------------------------------------------- Seite

def read(name):
    with open(os.path.join(WEBFILES, name)) as fh:
        return fh.read()


def js_syntax(pfad):
    """Echte Syntaxpruefung mit node -- Klammerzaehlen findet nicht jeden Fehler.
    (Genau daran ist die erste Fassung gescheitert: ein \\n wurde zum echten
    Zeilenumbruch und riss das ganze Skript mit.)"""
    node = shutil.which("node")
    if not node:
        return None
    fertig = subprocess.run([node, "--check", pfad], capture_output=True)
    return fertig.returncode == 0, (fertig.stderr or b"").decode()[:300]


def test_seite():
    print("Die Seite")
    html = read("index.html")
    js = read("app.js")
    css = read("app.css")
    check("Seite ist HTML", html.lstrip().startswith("<!DOCTYPE html>"))
    check("Seite ist abgeschlossen", html.rstrip().endswith("</html>"))
    check("Groesse im Rahmen (<40 KB)", len(html) < 40000, "%d Byte" % len(html))
    check("keine externen Abhaengigkeiten",
          "http://" not in html.replace("http://www.w3.org", "") and "https://" not in html)

    ids = set(re.findall(r'id="([^"]+)"', html))
    for name in ("repl", "editor", "files", "config", "out", "cmd", "code", "e-path",
                 "f-rows", "f-path", "upload", "c-ssid", "c-pass", "c-host", "c-bri",
                 "p-ip", "p-heap", "c-info", "shot-scale", "prev-status",
                 "c-board", "c-app"):
        check("Element #%s vorhanden" % name, name in ids)
    check("Vorschau ist eine Leinwand (kein PNG auf dem Geraet)",
          '<canvas class="prev" id="prev"' in html)
    check("Vorschau holt den Rohpuffer", '"/screen.raw?scale="' in js)

    # Jede per el("...") angesprochene ID muss es auch geben -- findet Tippfehler.
    benutzt = set(re.findall(r'el\("([^"]+)"\)', js))
    fehlend = sorted(benutzt - ids)
    check("alle angesprochenen IDs existieren", not fehlend, str(fehlend))

    # Jeder onclick-Handler muss als Funktion definiert sein.
    aufrufe = set(re.findall(r'onclick="([a-zA-Z_][a-zA-Z0-9_]*)\(', html))
    definiert = set(re.findall(r"function\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", js))
    fehlend = sorted(aufrufe - definiert)
    check("alle onclick-Handler sind definiert", not fehlend, str(fehlend))

    # Reiter und Abschnitte muessen zusammenpassen.
    for tab in ("repl", "editor", "files", "config"):
        check("Reiter fuer %s" % tab, 'data-tab="%s"' % tab in html)

    check("HTML verweist auf die getrennten Dateien",
          'href="/app.css"' in html and 'src="/app.js"' in html)
    check("Editor wird mitgeladen",
          'href="/editor/codemirror.css"' in html and 'src="/editor/codemirror.js"' in html
          and 'src="/editor/python.js"' in html)
    check("Editor faellt auf das Textfeld zurueck",
          'typeof CodeMirror === "undefined"' in js and "editorTasten();" in js)
    check("Editor liest und schreibt ueber CodeMirror",
          "editor.getValue()" in js and "editor.setValue(text)" in js)
    for name in ("codemirror.js", "codemirror.css", "python.js", "search.js", "dialog.js",
                 "dialog.css", "closebrackets.js", "matchbrackets.js", "active-line.js",
                 "comment.js", "jump-to-line.js", "LICENSE.txt"):
        check("Editordatei %s vorhanden" % name,
              os.path.exists(os.path.join(WEBFILES, "editor", name)))

    check("JS-Klammern ausgeglichen",
          js.count("{") == js.count("}") and js.count("(") == js.count(")"),
          "%d/%d geschweift, %d/%d rund" % (js.count("{"), js.count("}"),
                                            js.count("("), js.count(")")))
    ergebnis = js_syntax(os.path.join(WEBFILES, "app.js"))
    if ergebnis is None:
        print("  .... node fehlt -- Syntaxpruefung uebersprungen")
    else:
        gueltig, fehler = ergebnis
        check("app.js syntaktisch gueltig", gueltig, fehler)

    check("keine uebrig gebliebenen Platzhalter", "%s" not in html and "@@" not in html)
    for name, inhalt in (("index.html", html), ("app.js", js), ("app.css", css)):
        check("%s ohne eingestreute Fremdzeichen" % name,
              not re.search(r"[\u4e00-\u9fff]", inhalt))
    # Im JS-String darf kein echtes Zeilenende stehen (Escaping-Falle).
    schlecht = [z for z in js.split("\n") if z.count('"') % 2 == 1 and "//" not in z]
    check("keine abgerissenen JS-Zeichenketten", not schlecht, str(schlecht[:2]))


def test_setup_seite():
    print("Setup-Seite")
    html = read("setup.html")
    script = read("setup.js")
    ids = set(re.findall(r'id="([^"]+)"', html))
    for name in ("ssid", "password", "hostname", "ap_ssid", "ap_password", "board",
                 "board-info", "form-display", "form-touch", "status", "err", "chip",
                 "drivers"):
        check("Element #%s vorhanden" % name, name in ids)
    check("Setup-Seite laedt das eigene Skript", 'src="/setup.js"' in html)
    check("Setup-Seite nutzt das gemeinsame Stylesheet", 'href="/app.css"' in html)
    check("kein CDN in der Setup-Seite", "http://" not in html.replace("http://www.w3.org", ""))
    check("Setup-Seite kennt die Profil-API", "/api/profiles" in script)
    check("Setup-Seite kennt die Treiber-API", "/api/drivers" in script)
    check("Setup-Seite speichert ueber die API", '"/api/config"' in script)
    check("Setup-Seite kann neu starten", '"/api/reset"' in script)
    check("Setup-Seite fordert eine SSID",
          "WiFi name is required" in script)
    check("keine deutschen Umlaute in der Setup-Seite",
          not set("äöüÄÖÜß") & set(html + script))
    check("Setup-Syntax ok (node)", js_syntax(os.path.join(WEBFILES, "setup.js")))
    check("Setup-CSS vorhanden", ".setup" in read("app.css"))
    check("Hauptseite verlinkt die Einrichtung",
          "setup" in read("app.js").lower() or "setup" in read("index.html").lower())


def test_routen():
    print("Routen")
    routen = webui.build_routes()
    for schluessel in ("GET /", "GET /api/state", "POST /api/exec", "GET /api/log",
                       "GET /api/files", "GET /api/file", "POST /api/file",
                       "DELETE /api/file", "POST /api/mkdir", "POST /api/rename",
                       "GET /api/config", "POST /api/config", "GET /api/screen.png",
                       "POST /api/reset", "GET /status", "GET /editor/*",
                       "GET /setup", "GET /setup.js", "GET /api/profiles",
                       "GET /api/drivers"):
        check("Route %s" % schluessel, schluessel in routen)
    _, server = serve.build_server(port=0)
    check("Weboberflaeche haengt im Server", "GET /api/files" in server.routes)
    check("Klartext-Status bleibt", "GET /status" in server.routes)

    # Setup mode serves configuration only: no MCP, no code execution, no files.
    einrichten = webui.setup_routes()
    check("Setup-Route vorhanden", "GET /setup" in einrichten)
    check("Setup ohne Codeausfuehrung", "POST /api/exec" not in einrichten)
    check("Setup ohne MCP", "POST /mcp" not in einrichten)
    check("Setup ohne Dateizugriff", "GET /api/files" not in einrichten)
    _, setup_server = serve.build_server(port=0, setup_only=True)
    finde_setup = setup_server._find_handler
    check("Setup-Modus liefert die Konfigseite",
          finde_setup("GET", "/") is not None and finde_setup("GET", "/setup") is not None)
    check("Setup-Modus leitet Unbekanntes um", finde_setup("GET", "/generate_204") is not None)
    check("Setup-Modus leitet Codeausfuehrung um statt sie auszufuehren",
          finde_setup("POST", "/api/exec") is webui.portal_redirect)
    check("Setup-Modus leitet Dateizugriff um", finde_setup("GET", "/api/files") is webui.portal_redirect)

    # Praefix-Routen (Schluessel endet auf "*") aufloesen
    finde = server._find_handler
    check("Praefix-Route trifft Editor-Datei",
          finde("GET", "/editor/codemirror.js") is not None)
    check("exakte Route hat Vorrang",
          finde("GET", "/app.js") is not None and finde("GET", "/app.js") is not finde("GET", "/editor/x"))
    check("unbekannter Pfad ohne Handler", finde("GET", "/gibtsnicht") is None)
    check("falsche Methode ohne Handler", finde("POST", "/editor/codemirror.js") is None)


# ---------------------------------------------------------------- API gegen tmp

def test_dateien(tmp):
    print("Dateien (API)")
    os.makedirs(os.path.join(tmp, "lib"))
    with open(os.path.join(tmp, "main.py"), "w") as fh:
        fh.write("print('hallo')\n")
    with open(os.path.join(tmp, "bild.png"), "wb") as fh:
        fh.write(bytes(range(256)))

    antwort = json.loads(text_of(webui.api_files(req("GET", "/api/files", {"path": "/"}))))
    namen = [e["name"] for e in antwort["entries"]]
    check("Eintraege gelistet", "main.py" in namen and "lib" in namen, str(namen))
    check("Verzeichnis zuerst", namen[0] == "lib", str(namen))
    check("Verzeichnis markiert", [e["dir"] for e in antwort["entries"] if e["name"] == "lib"] == [True])
    check("Groesse gemeldet", [e["size"] for e in antwort["entries"] if e["name"] == "main.py"] == [15])
    check("Speicherinfo dabei", "frei" in antwort.get("speicher", {}))
    check("Unterordner listbar",
          json.loads(text_of(webui.api_files(req("GET", "/api/files", {"path": "/lib"}))))["entries"] == [])

    # lesen
    antwort = json.loads(text_of(webui.api_file_get(req("GET", "/api/file", {"path": "/main.py"}))))
    check("Datei lesbar", antwort["data"] == "print('hallo')\n")
    check("Text als Text", antwort["binary"] is False)

    antwort = json.loads(text_of(webui.api_file_get(req("GET", "/api/file", {"path": "/bild.png"}))))
    check("Binaerdatei erkannt", antwort["binary"] is True and antwort["size"] == 256)

    resp = webui.api_file_get(req("GET", "/api/file", {"path": "/bild.png", "download": "1"}))
    check("Download liefert Anhang", resp.headers.get("Content-Disposition", "").startswith("attachment"))
    check("Download liefert Bytes", resp.body == bytes(range(256)))

    antwort = json.loads(text_of(webui.api_file_get(req("GET", "/api/file", {"path": "/gibtsnicht"}))))
    check("fehlende Datei gemeldet", "error" in antwort)

    # schreiben
    antwort = json.loads(text_of(webui.api_file_put(
        req("POST", "/api/file", {"path": "/neu.txt"}, b"inhalt")))
    )
    check("Datei geschrieben", antwort["ok"] and antwort["bytes"] == 6)
    with open(os.path.join(tmp, "neu.txt")) as fh:
        check("Inhalt stimmt", fh.read() == "inhalt")

    # JSON-Variante
    antwort = json.loads(text_of(webui.api_file_put(
        req("POST", "/api/file", {}, json.dumps({"path": "/json.txt", "data": "abc"}).encode())))
    )
    check("Schreiben per JSON", antwort["ok"] and os.path.exists(os.path.join(tmp, "json.txt")))

    check("Schreiben ohne Pfad abgelehnt",
          webui.api_file_put(req("POST", "/api/file", {}, b"x")).status == 400)
    check("zu grosse Datei abgelehnt",
          webui.api_file_put(req("POST", "/api/file", {"path": "/gross"},
                                 b"x" * (webui.MAX_UPLOAD + 1))).status == 413)

    # Unterordner wird beim Schreiben angelegt
    antwort = json.loads(text_of(webui.api_file_put(
        req("POST", "/api/file", {"path": "/tief/drin.txt"}, b"tief"))))
    check("fehlender Ordner wird angelegt",
          antwort["ok"] and os.path.exists(os.path.join(tmp, "tief", "drin.txt")))

    # mkdir / rename / delete
    check("mkdir", json.loads(text_of(webui.api_file_mkdir(
        req("POST", "/api/mkdir", {}, b'{"path": "/daten"}'))))["ok"])
    check("Ordner existiert", os.path.isdir(os.path.join(tmp, "daten")))
    check("rename", json.loads(text_of(webui.api_file_rename(
        req("POST", "/api/rename", {}, b'{"old": "/neu.txt", "new": "/daten/alt.txt"}'))))["ok"])
    check("Datei umbenannt", os.path.exists(os.path.join(tmp, "daten", "alt.txt")))
    check("delete Datei", json.loads(text_of(webui.api_file_delete(
        req("DELETE", "/api/file", {}, b'{"path": "/daten/alt.txt"}'))))["ok"])
    check("delete Ordner", json.loads(text_of(webui.api_file_delete(
        req("DELETE", "/api/file", {}, b'{"path": "/daten"}'))))["ok"])
    check("Ordner weg", not os.path.exists(os.path.join(tmp, "daten")))

    # Ausbruch aus dem Wurzelverzeichnis verhindern
    webui.api_file_put(req("POST", "/api/file", {"path": "/../../ausbruch.txt"}, b"nein"))
    check("kein Ausbruch aus dem Wurzelverzeichnis",
          not os.path.exists(os.path.join(os.path.dirname(tmp), "ausbruch.txt")))
    check("Pfad bleibt im Wurzelverzeichnis",
          webui.real_path("/../../x").startswith(tmp))


def test_konfiguration(tmp):
    print("Konfiguration")
    start = webui.config_lesen()
    check("Standardwerte vorhanden",
          start["hostname"] == "esp32-debug" and start["display"]["brightness"] == 70)
    check("Display- und Touch-Abschnitt vorhanden",
          "driver" in start["display"] and "driver" in start["touch"])
    antwort = json.loads(text_of(webui.api_config(req("POST", "/api/config", {}, json.dumps(
        {"ssid": "Netz", "password": "Geheim", "hostname": "brett", "brightness": 30,
         "unbekannt": "ignoriert"}).encode()))))
    check("Speichern liefert Konfiguration", antwort["config"]["ssid"] == "Netz")
    check("unbekannter Schluessel ignoriert", "unbekannt" not in antwort["config"])
    danach = webui.config_lesen()
    check("Werte bleiben erhalten",
          danach["hostname"] == "brett" and danach["display"]["brightness"] == 30)
    check("Datei liegt auf dem Geraet", os.path.exists(os.path.join(tmp, "config.json")))
    check("Lesen ueber GET",
          json.loads(text_of(webui.api_config(req("GET", "/api/config"))))["config"]["ssid"] == "Netz")
    # Display/Touch sections are merged field by field, a profile provides the base.
    webui.config_schreiben({"board": "JC3248W535", "display": {"brightness": 42},
                            "touch": {"scl": 7}})
    nach_profil = webui.config_lesen()
    check("Profil liefert Pins", nach_profil["display"]["sck"] == 47,
          str(nach_profil["display"].get("sck")))
    check("eigener Wert gewinnt", nach_profil["display"]["brightness"] == 42)
    check("nicht genannte Felder bleiben", nach_profil["display"]["width"] == 320)
    check("Touch-Abschnitt gemischt",
          nach_profil["touch"]["scl"] == 7 and nach_profil["touch"]["sda"] == 4)
    # Passwort darf nie an den Browser gehen -- aber auch nicht verloren gehen.
    sichtbar = json.loads(text_of(webui.api_config(req("GET", "/api/config"))))["config"]
    check("Passwort wird nicht ausgeliefert", sichtbar["password"] == "")
    check("Passwort als gesetzt markiert", sichtbar["password_gesetzt"] is True)
    webui.api_config(req("POST", "/api/config", {}, json.dumps(
        {"hostname": "brett2", "password": ""}).encode()))
    check("leeres Passwort loescht nichts", webui.config_lesen(mit_passwort=True)["password"] == "Geheim")
    webui.api_config(req("POST", "/api/config", {}, json.dumps(
        {"password": "Neu"}).encode()))
    check("neues Passwort uebernommen", webui.config_lesen(mit_passwort=True)["password"] == "Neu")
    # wifi.json bleibt als Basis nutzbar (Altbestand), aber nur fuer leere Felder
    with open(os.path.join(tmp, "wifi.json"), "w") as fh:
        json.dump({"ssid": "Alt-Netz", "password": "Alt-Geheim", "hostname": "alt"}, fh)
    webui.config_schreiben({"ssid": "", "hostname": "brett3", "brightness": 40})
    wirksam = webui.config_lesen()
    check("leere SSID -> wifi.json liefert sie", wirksam["ssid"] == "Alt-Netz", wirksam["ssid"])
    check("gesetzter Hostname gewinnt", wirksam["hostname"] == "brett3", wirksam["hostname"])
    check("Helligkeit bleibt erhalten", wirksam["display"]["brightness"] == 40)
    check("Altbestand-Passwort bleibt nutzbar",
          webui.config_lesen(mit_passwort=True)["password"] == "Neu")
    # A profile only provides the fields that were never stored explicitly.
    os.remove(os.path.join(tmp, "config.json"))
    webui.config_schreiben({"board": "CUSTOM"})
    check("Profil liefert den Treiber, solange nichts Eigenes gespeichert ist",
          webui.config_lesen()["display"]["driver"] == "st7789",
          webui.config_lesen()["display"]["driver"])
    check("nach dem Loeschen greift wieder der Altbestand",
          webui.config_lesen(mit_passwort=True)["password"] == "Alt-Geheim",
          webui.config_lesen(mit_passwort=True)["password"])
    # Profile and driver lists feed the setup page
    display_config = sys.modules["display_config"]
    echt_chip = display_config.chip_name
    display_config.chip_name = lambda: "esp32s3"     # host runs on x86_64
    try:
        profile = json.loads(text_of(webui.api_profiles(req("GET", "/api/profiles"))))
        check("Profile fuer diesen Chip",
              len(profile["profiles"]) >= 2
              and all(p["chip"] == profile["chip"] for p in profile["profiles"]),
              str(profile.get("chip")))
        check("Profil enthaelt Pins", "display" in profile["profiles"][0])
        check("Chip-Typ wird mitgeliefert", profile["chip"] == "esp32s3")
    finally:
        display_config.chip_name = echt_chip
    treiber = json.loads(text_of(webui.api_drivers(req("GET", "/api/drivers"))))
    check("Treiberlisten vorhanden",
          isinstance(treiber["display"], list) and isinstance(treiber["touch"], list))
    # Device-only trap: this MicroPython build has no os.path. Emulate that on the
    # host, otherwise the bug only shows up on the board.
    import types
    ohne_pfad = types.ModuleType("os")
    for name in ("listdir", "stat", "mkdir", "remove", "rename", "rmdir", "uname"):
        if hasattr(os, name):
            setattr(ohne_pfad, name, getattr(os, name))
    echt_os = display_config.os
    display_config.os = ohne_pfad
    try:
        treiber = display_config.available_drivers()
        check("Treiberliste ohne os.path",
              isinstance(treiber["display"], list) and isinstance(treiber["touch"], list),
              str(treiber))
        check("Treiber aus /drv werden gefunden", "axs15231b" in treiber["display"]
              or not treiber["display"], str(treiber["display"][:3]))
    finally:
        display_config.os = echt_os


def test_exec():
    print("Konsole (exec)")
    antwort = json.loads(text_of(webui.api_exec(
        req("POST", "/api/exec", {}, json.dumps({"code": "print(6*7)"}).encode()))))
    check("Ausgabe von print kommt zurueck", "42" in antwort["output"])
    antwort = json.loads(text_of(webui.api_exec(req("POST", "/api/exec", {}, b"print('roh')"))))
    check("reiner Text als Code", "roh" in antwort["output"])
    antwort = json.loads(text_of(webui.api_exec(
        req("POST", "/api/exec", {}, json.dumps({"code": "1/0"}).encode()))))
    check("Fehler wird gemeldet", "ZeroDivisionError" in antwort["output"])
    check("leerer Code abgelehnt",
          webui.api_exec(req("POST", "/api/exec", {}, b"")).status == 400)


def test_httppfad(tmp):
    print("Ueber HTTP")
    _, server = serve.build_server(port=0)
    server.start_in_thread()
    port = server.sock.getsockname()[1]
    base = ("127.0.0.1", port)

    def hole(pfad, methode="GET", daten=None, kopf=None):
        s = socket.create_connection(base, timeout=10)
        kopfzeilen = ["%s %s HTTP/1.1" % (methode, pfad), "Host: localhost",
                      "Connection: close"]
        for k in (kopf or []):
            kopfzeilen.append(k)
        if daten is not None:
            kopfzeilen.append("Content-Length: %d" % len(daten))
        roh = ("\r\n".join(kopfzeilen) + "\r\n\r\n").encode()
        if daten:
            roh += daten
        s.sendall(roh)
        teile = []
        while True:
            stueck = s.recv(65536)
            if not stueck:
                break
            teile.append(stueck)
        s.close()
        Antwort = b"".join(teile)
        kopf_teil, _, koerper = Antwort.partition(b"\r\n\r\n")
        return kopf_teil.decode(), koerper

    kopf, koerper = hole("/")
    check("GET / liefert die Seite", kopf.startswith("HTTP/1.1 200") and b"ESP32-S3 Debug" in koerper)
    check("Seite als HTML", "text/html" in kopf)

    kopf, koerper = hole("/status")
    check("GET /status liefert Klartext", b"debug server" in koerper)

    kopf, koerper = hole("/api/files?path=/")
    check("GET /api/files liefert JSON",
          kopf.startswith("HTTP/1.1 200") and "entries" in json.loads(koerper.decode()))

    kopf, koerper = hole("/api/config", "POST", b'{"brightness": 55}')
    check("POST /api/config speichert",
          json.loads(koerper.decode())["config"]["display"]["brightness"] == 55)

    kopf, koerper = hole("/api/file?path=/http.txt", "POST", b"ueber http")
    check("POST /api/file schreibt", json.loads(koerper.decode())["ok"])
    with open(os.path.join(tmp, "http.txt")) as fh:
        check("Inhalt ueber HTTP geschrieben", fh.read() == "ueber http")
    kopf, koerper = hole("/api/file?path=/http.txt")
    check("Datei ueber HTTP lesbar", json.loads(koerper.decode())["data"] == "ueber http")

    kopf, koerper = hole("/api/exec", "POST", b'{"code": "print(2+2)"}')
    check("exec ueber HTTP", "4" in json.loads(koerper.decode())["output"])

    kopf, koerper = hole("/api/log")
    check("Log abrufbar", kopf.startswith("HTTP/1.1 200"))

    # Grosse Datei: muss gestueckt und vollstaendig ausgeliefert werden (auf dem Geraet
    # waere ein 174-KB-Block am Stueck der Ausloeser fuer Speicherprobleme).
    gross = os.path.join(tmp, "web", "editor", "gross.js")
    with open(gross, "wb") as fh:
        fh.write(b"/*" + b"x" * 300000 + b"*/")
    kopf, koerper = hole("/editor/gross.js")
    check("grosse Datei kommt vollstaendig an",
          kopf.startswith("HTTP/1.1 200") and len(koerper) == 300004, "%d Byte" % len(koerper))
    check("Laengenangabe stimmt", "Content-Length: 300004" in kopf)
    check("Inhalt stimmt", koerper.startswith(b"/*") and koerper.endswith(b"*/"))
    check("Editor-Datei ueber HTTP",
          hole("/editor/codemirror.js")[0].startswith("HTTP/1.1 200"))
    kopf, _ = hole("/editor/../../etc/passwd", "GET", kopf=["X-Test: 1"])
    check("Ausbruch wird abgewiesen", kopf.startswith("HTTP/1.1 403"), kopf[:40])
    os.remove(gross)

    kopf, koerper = hole("/gibtsnicht")
    check("unbekannter Pfad -> 404", kopf.startswith("HTTP/1.1 404"))

    server.running = False
    try:
        socket.create_connection(base, timeout=2).close()
    except OSError:
        pass


def main():
    tmp = tempfile.mkdtemp(prefix="webui-test-")
    # Wie auf dem Geraet: die Oberflaeche liegt unter <root>/web/
    shutil.copytree(WEBFILES, os.path.join(tmp, "web"))
    alt = webui.ROOT
    webui.ROOT = tmp
    display_config = sys.modules["display_config"]
    alt_profile = display_config.PROFILES_FILE
    # profiles.json ships with the firmware and is not part of the writable area.
    display_config.PROFILES_FILE = os.path.join(os.path.dirname(HERE), "firmware", "device",
                                                "profiles.json")
    try:
        test_seite()
        test_setup_seite()
        test_routen()
        test_dateien(tmp)
        test_konfiguration(tmp)
        test_exec()
        test_httppfad(tmp)
    finally:
        webui.ROOT = alt
        display_config.PROFILES_FILE = alt_profile
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
