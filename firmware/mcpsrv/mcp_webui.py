# Web-Oberflaeche des Debug-Servers: Konsole (REPL), Codeeditor, Dateimanager, Konfiguration.
#
# Bewusste Entscheidungen:
#   * Reines HTML/CSS/JS ohne externe Abhaengigkeiten -- der Browser holt nichts aus
#     dem Netz, die Seite funktioniert also auch ohne Internet.
#   * Eine einzige Seite mit Reitern statt vier Seiten: weniger Uebertragung, und der
#     Editorinhalt bleibt beim Wechseln erhalten.
#   * Texte auf Deutsch, Code-Kommentare auf Englisch (Projektkonvention).
#   * KEINE Authentifizierung. Das UI ist ein Debug-Werkzeug fuer das eigene LAN.
#
# Alle Dateizugriffe laufen ueber ROOT -- die Host-Tests setzen dort ein temporaeres
# Verzeichnis und pruefen dieselben Handler wie das Geraet.

import json
import os

import mcp_httpd
import mcp_logbuf
import mcp_screen
import mcp_tools

ROOT = ""                                     # "" = Geraetewurzel; Host-Test: tmp-Verzeichnis
CONFIG_FILE = "config.json"                   # WLAN + Anzeige + Geraetename
MAX_UPLOAD = 1024 * 1024
TEXT_SUFFIXES = (".py", ".json", ".txt", ".md", ".csv", ".html", ".css", ".js", ".cfg", ".ini")
BINARY_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".bin", ".uf2", ".z", ".deflate")


# ---------------------------------------------------------------- Dateizugriff

def real_path(path):
    """Pfadangabe des Browsers in einen echten Pfad umsetzen (ohne Ausbruch aus ROOT)."""
    path = (path or "/").strip() or "/"
    if not path.startswith("/"):
        path = "/" + path
    # ".." neutralisieren, damit niemand aus ROOT ausbricht
    teile = [p for p in path.split("/") if p not in ("", ".")]
    sauber = []
    for teil in teile:
        if teil == "..":
            if sauber:
                sauber.pop()
            continue
        sauber.append(teil)
    return ROOT + "/" + "/".join(sauber)


def ist_verzeichnis(pfad):
    try:
        return (os.stat(pfad)[0] & 0x4000) != 0
    except OSError:
        return False


def datei_eintraege(path):
    """Verzeichnis auflisten: Name, Groesse, Verzeichnis-Kennzeichen."""
    ziel = real_path(path)
    namen = os.listdir(ziel)
    eintraege = []
    for name in sorted(namen):
        voll = ziel.rstrip("/") + "/" + name
        versuch = None
        try:
            versuch = os.stat(voll)
        except OSError:
            pass
        if versuch is None:
            eintraege.append({"name": name, "size": 0, "dir": False, "unbekannt": True})
            continue
        eintraege.append({
            "name": name,
            "size": versuch[6],
            "dir": (versuch[0] & 0x4000) != 0,
        })
    # Verzeichnisse zuerst
    eintraege.sort(key=lambda e: (not e["dir"], e["name"].lower()))
    return eintraege


def speicher_info():
    try:
        st = os.statvfs(ROOT + "/")
        return {"frei": st[0] * st[3], "gesamt": st[0] * st[2]}
    except OSError:
        return {}


# ---------------------------------------------------------------- Konfiguration

STANDARD_CONFIG = {
    "ssid": "",
    "password": "",
    "hostname": "esp32-debug",
    "brightness": 70,
    "backlight": True,
}


def _wifi_json_lesen():
    try:
        with open(ROOT + "/wifi.json") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def config_lesen(mit_passwort=False):
    """Wirksame Konfiguration: wifi.json als Basis, config.json hat Vorrang.

    Das WLAN-Passwort wird geraeteseitig gebraucht, aber nicht an den Browser
    zurueckgegeben (`mit_passwort=False`); stattdessen steht dort
    `password_gesetzt`, damit die Seite anzeigen kann, dass eines hinterlegt ist.
    """
    cfg = dict(STANDARD_CONFIG)
    try:
        with open(ROOT + "/" + CONFIG_FILE) as fh:
            cfg.update(json.load(fh))
    except (OSError, ValueError):
        pass
    # wifi.json (Altbestand) fuellt nur Luecken -- es ueberschreibt nichts Gesetztes.
    # Gleiche Regel wie in boot.py, damit beide dieselbe wirksame Konfiguration sehen.
    alt = _wifi_json_lesen()
    for schluessel in ("ssid", "hostname"):
        if not cfg.get(schluessel) and alt.get(schluessel):
            cfg[schluessel] = alt[schluessel]
    if not mit_passwort:
        cfg["password_gesetzt"] = bool(cfg.get("password"))
        cfg["password"] = ""
    return cfg


def config_schreiben(daten):
    """Speichern. Ein leeres Passwortfeld loescht kein hinterlegtes Passwort."""
    alt = config_lesen(mit_passwort=True)
    cfg = dict(alt)
    for schluessel in STANDARD_CONFIG:
        if schluessel not in daten:
            continue
        wert = daten[schluessel]
        if schluessel == "password" and wert == "" and alt.get("password"):
            continue                      # leer = unveraendert
        cfg[schluessel] = wert
    with open(ROOT + "/" + CONFIG_FILE, "w") as fh:
        json.dump(cfg, fh)
    return config_lesen()


# ---------------------------------------------------------------- API-Handler

def api_state(req):
    info = mcp_tools.tool_device_info()
    antwort = {
        "ip": None,
        "heap": info.get("gc_free"),
        "uptime_s": info.get("uptime_s"),
        "freq_mhz": info.get("freq_mhz"),
        "wifi": info.get("wifi"),
        "screen": mcp_screen.describe(),
        "speicher": speicher_info(),
    }
    try:
        wlan = info.get("wifi") or {}
        if isinstance(wlan, dict) and wlan.get("ifconfig"):
            antwort["ip"] = wlan["ifconfig"][0]
    except Exception:  # noqa: BLE001
        pass
    return mcp_httpd.json_response(antwort)


def api_exec(req):
    """Code ausfuehren. Body: JSON {"code": "..."} oder reiner Text."""
    if req.body:
        text = req.body.decode("utf-8", "replace") if hasattr(req.body, "decode") else str(req.body)
    else:
        text = req.arg("code", "") or ""
    if text.lstrip().startswith("{"):
        try:
            text = json.loads(text).get("code", "")
        except ValueError:
            pass
    if not text:
        return mcp_httpd.json_response({"ok": False, "output": "kein Code uebergeben"}, 400)
    try:
        ausgabe = mcp_tools.tool_exec(text)
    except Exception as exc:  # noqa: BLE001
        return mcp_httpd.json_response(
            {"ok": False, "output": "%s: %s" % (type(exc).__name__, exc)}, 500)
    return mcp_httpd.json_response({"ok": True, "output": ausgabe})


def api_log(req):
    return mcp_httpd.text(200, mcp_logbuf.logs(clear=req.arg("clear") == "1"))


def api_files(req):
    try:
        eintraege = datei_eintraege(req.arg("path", "/"))
    except OSError as exc:
        return mcp_httpd.json_response({"error": "listdir: %s" % exc, "path": req.arg("path", "/")}, 404)
    return mcp_httpd.json_response({
        "path": req.arg("path", "/"),
        "entries": eintraege,
        "speicher": speicher_info(),
    })


def api_file_get(req):
    pfad = req.arg("path")
    if not pfad:
        return mcp_httpd.json_response({"error": "path fehlt"}, 400)
    ziel = real_path(pfad)
    try:
        with open(ziel, "rb") as fh:
            daten = fh.read()
    except OSError as exc:
        return mcp_httpd.json_response({"error": "lesen: %s" % exc}, 404)
    if req.arg("download") == "1":
        name = ziel.rsplit("/", 1)[-1]
        return mcp_httpd.Response(200, daten, {
            "Content-Type": "application/octet-stream",
            "Content-Disposition": 'attachment; filename="%s"' % name,
        })
    try:
        return mcp_httpd.json_response({"path": pfad, "data": daten.decode("utf-8"), "binary": False})
    except UnicodeError:
        return mcp_httpd.json_response(
            {"path": pfad, "binary": True, "size": len(daten),
             "hinweis": "Binaerdatei -- nur Download"}, 200)


def api_file_put(req):
    """Datei schreiben. Body = Inhalt (roh), Pfad ueber ?path= oder JSON {"path","data"}."""
    pfad = req.arg("path")
    daten = req.body or b""
    if not pfad and daten[:1] == b"{":
        try:
            nutzlast = json.loads(daten.decode("utf-8"))
            pfad = nutzlast.get("path")
            daten = nutzlast.get("data", "").encode("utf-8")
        except ValueError:
            return mcp_httpd.json_response({"error": "JSON unlesbar"}, 400)
    if not pfad:
        return mcp_httpd.json_response({"error": "path fehlt"}, 400)
    if len(daten) > MAX_UPLOAD:
        return mcp_httpd.json_response({"error": "zu gross (max %d)" % MAX_UPLOAD}, 413)
    ziel = real_path(pfad)
    eltern = ziel.rsplit("/", 1)[0]
    if eltern and not ist_verzeichnis(eltern):
        try:
            os.mkdir(eltern)
        except OSError:
            pass
    try:
        with open(ziel, "wb") as fh:
            fh.write(daten)
    except OSError as exc:
        return mcp_httpd.json_response({"error": "schreiben: %s" % exc}, 500)
    return mcp_httpd.json_response({"ok": True, "path": pfad, "bytes": len(daten)})


def api_file_delete(req):
    daten = req.json()
    pfad = daten.get("path")
    if not pfad:
        return mcp_httpd.json_response({"error": "path fehlt"}, 400)
    ziel = real_path(pfad)
    try:
        if ist_verzeichnis(ziel):
            os.rmdir(ziel)
        else:
            os.remove(ziel)
    except OSError as exc:
        return mcp_httpd.json_response({"error": "loeschen: %s" % exc}, 500)
    return mcp_httpd.json_response({"ok": True, "path": pfad})


def api_file_mkdir(req):
    daten = req.json()
    pfad = daten.get("path")
    if not pfad:
        return mcp_httpd.json_response({"error": "path fehlt"}, 400)
    try:
        os.mkdir(real_path(pfad))
    except OSError as exc:
        return mcp_httpd.json_response({"error": "mkdir: %s" % exc}, 500)
    return mcp_httpd.json_response({"ok": True, "path": pfad})


def api_file_rename(req):
    daten = req.json()
    alt, neu = daten.get("old"), daten.get("new")
    if not alt or not neu:
        return mcp_httpd.json_response({"error": "old/new fehlt"}, 400)
    ziel = real_path(neu)
    try:
        os.rename(real_path(alt), ziel)
    except OSError as exc:
        return mcp_httpd.json_response({"error": "umbenennen: %s" % exc}, 500)
    return mcp_httpd.json_response({"ok": True, "path": neu})


def api_config(req):
    if req.method == "POST":
        daten = req.json()
        if not isinstance(daten, dict):
            return mcp_httpd.json_response({"error": "Objekt erwartet"}, 400)
        try:
            cfg = config_schreiben(daten)
        except OSError as exc:
            return mcp_httpd.json_response({"error": "speichern: %s" % exc}, 500)
        return mcp_httpd.json_response({"ok": True, "config": cfg})
    return mcp_httpd.json_response({"config": config_lesen()})


def api_screen(req):
    scale = int(req.arg("scale", "2"))
    daten, breite, hoehe, swap = mcp_screen.capture(scale=scale)
    from mcp_png import encode_rgb565_png
    blob = encode_rgb565_png(daten, breite, hoehe, byte_swap=swap)
    return mcp_httpd.Response(200, blob, {"Content-Type": "image/png",
                                          "Cache-Control": "no-store"})


def api_reset(req):
    return mcp_httpd.json_response({"result": mcp_tools.tool_reset(500)})


def build_routes():
    return {
        "GET /": statisch("index.html"),
        "GET /ui": statisch("index.html"),
        "GET /index.html": statisch("index.html"),
        "GET /app.css": statisch("app.css"),
        "GET /app.js": statisch("app.js"),
        "GET /editor/*": web_baum,          # mitgelieferter Codeeditor (CodeMirror)
        "GET /favicon.ico": favicon,
        "GET /api/state": api_state,
        "POST /api/exec": api_exec,
        "GET /api/log": api_log,
        "GET /api/files": api_files,
        "GET /api/file": api_file_get,
        "POST /api/file": api_file_put,
        "DELETE /api/file": api_file_delete,
        "POST /api/mkdir": api_file_mkdir,
        "POST /api/rename": api_file_rename,
        "GET /api/config": api_config,
        "POST /api/config": api_config,
        "GET /api/screen.png": api_screen,
        "POST /api/reset": api_reset,
        "GET /status": status_route,
    }


def status_route(req):
    """Klartext-Status -- bleibt fuer den schnellen Blick mit curl erhalten."""
    return mcp_httpd.text(200, "esp32 debug server\n%s\nUI: http://<ip>/\ntools:\n%s\n" % (
        mcp_screen.describe(),
        "\n".join("  %s" % t.name for t in mcp_tools.build_tools())))


def seite(req):
    """Kompatibilitaet: "/" liefert die Startseite der Oberflaeche."""
    return statisch("index.html")(req)


# ---------------------------------------------------------------- Dateien der Oberflaeche

# HTML, CSS und JS liegen als echte Dateien in firmware/webfiles/ (auf dem Geraet: /web).
# Grund: im Python-String entstehen sonst Escaping-Fehler -- in der ersten Fassung wurden
# aus "\n" in JS-Strings echte Zeilenumbrueche, wodurch das ganze Skript nicht mehr
# geparst wurde und die Oberflaeche ohne Funktion blieb. Ausserdem sind die Dateien so
# ueber den Dateimanager editierbar.

WEB_DIR = "web"
TYPEN = {".html": "text/html; charset=utf-8",
         ".css": "text/css; charset=utf-8",
         ".js": "application/javascript; charset=utf-8",
         ".txt": "text/plain; charset=utf-8",
         ".png": "image/png",
         ".svg": "image/svg+xml; charset=utf-8",
         ".json": "application/json"}


def web_datei_lesen(name):
    with open(ROOT + "/" + WEB_DIR + "/" + name, "rb") as fh:
        return fh.read()


def content_type(name):
    for endung, typ in TYPEN.items():
        if name.endswith(endung):
            return typ
    return "application/octet-stream"


def statisch(name):
    """Auslieferer fuer eine Datei der Oberflaeche (ohne Cache -- Aenderungen im
    Dateimanager sollen sofort wirken). Der Inhalt wird gestueckt gesendet."""

    def handler(req):
        ziel = ROOT + "/" + WEB_DIR + "/" + name
        try:
            with open(ziel, "rb"):
                pass
        except OSError as exc:
            return mcp_httpd.text(
                500, "%s fehlt auf dem Geraet (%s)\\n-- firmware/webfiles/ mit deploy.sh kopieren"
                % (name, exc))
        return mcp_httpd.Response(200, b"", {"Content-Type": content_type(name),
                                            "Cache-Control": "no-store"}, datei=ziel)
    return handler


def favicon(req):
    return mcp_httpd.Response(204, b"", {})


def web_baum(req):
    """Dateien des mitgelieferten Editors ausliefern (Praefix-Route /editor/*).

    Der Pfad kommt vom Browser und wird deshalb streng geprueft: nur der Baum
    <WEB_DIR>/editor, und kein ".." darin.
    """
    name = req.path.lstrip("/")
    erlaubt = name.startswith("editor/") and ".." not in name and "//" not in name
    if not erlaubt:
        return mcp_httpd.text(403, "Pfad nicht erlaubt")
    ziel = ROOT + "/" + WEB_DIR + "/" + name
    try:
        with open(ziel, "rb"):
            pass
    except OSError as exc:
        return mcp_httpd.text(404, "%s nicht gefunden (%s)" % (name, exc))
    return mcp_httpd.Response(200, b"", {"Content-Type": content_type(name),
                                         "Cache-Control": "no-store"}, datei=ziel)
