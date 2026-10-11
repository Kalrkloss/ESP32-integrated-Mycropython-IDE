# Web UI of the debug server: console (REPL), code editor, file manager, configuration.
#
# Deliberate decisions:
#   * Pure HTML/CSS/JS without external dependencies -- the browser fetches nothing
#     from the network, so the page works without internet too.
#   * A single page with tabs instead of four pages: less transfer, and the editor
#     content is preserved when switching.
#   * All texts in English (project convention).
#   * NO authentication. The UI is a debug tool for your own LAN.
#
# All file accesses go through ROOT -- the host tests set a temporary directory
# there and exercise the same handlers as the device.

import json
import os

import display_config
import mcp_httpd
import mcp_logbuf
import mcp_screen
import mcp_tools
import portal

ROOT = ""                                     # "" = device root; host test: tmp directory
CONFIG_FILE = "config.json"                   # WLAN + display + device name
MAX_UPLOAD = 1024 * 1024
TEXT_SUFFIXES = (".py", ".json", ".txt", ".md", ".csv", ".html", ".css", ".js", ".cfg", ".ini")
BINARY_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".bin", ".uf2", ".z", ".deflate")


# ---------------------------------------------------------------- File access

def real_path(path):
    """Turn a path given by the browser into a real path (without escaping ROOT)."""
    path = (path or "/").strip() or "/"
    if not path.startswith("/"):
        path = "/" + path
    # neutralize ".." so nobody escapes ROOT
    parts = [p for p in path.split("/") if p not in ("", ".")]
    clean = []
    for part in parts:
        if part == "..":
            if clean:
                clean.pop()
            continue
        clean.append(part)
    return ROOT + "/" + "/".join(clean)


def is_dir(path):
    try:
        return (os.stat(path)[0] & 0x4000) != 0
    except OSError:
        return False


def dir_entries(path):
    """List a directory: name, size, directory flag."""
    target = real_path(path)
    names = os.listdir(target)
    entries = []
    for name in sorted(names):
        full = target.rstrip("/") + "/" + name
        stat = None
        try:
            stat = os.stat(full)
        except OSError:
            pass
        if stat is None:
            entries.append({"name": name, "size": 0, "dir": False, "unbekannt": True})
            continue
        entries.append({
            "name": name,
            "size": stat[6],
            "dir": (stat[0] & 0x4000) != 0,
        })
    # directories first
    entries.sort(key=lambda e: (not e["dir"], e["name"].lower()))
    return entries


def memory_info():
    try:
        st = os.statvfs(ROOT + "/")
        return {"free": st[0] * st[3], "total": st[0] * st[2]}
    except OSError:
        return {}


# ---------------------------------------------------------------- Configuration

DEFAULT_CONFIG = {
    "ssid": "",
    "password": "",
    "hostname": "esp32-debug",
    "brightness": 70,
    "backlight": True,
}


def _read_wifi_json():
    try:
        with open(real_path("/wifi.json")) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def config_lesen(mit_passwort=False):
    """Effective configuration as the web UI sees it.

    Base is display_config.load_config() (profile + config.json). The legacy
    wifi.json only fills empty fields, with the same rule boot.py uses. The WiFi
    password is needed on the device but is never handed back to the browser --
    instead the UI gets `password_gesetzt` so it can show that one is stored.
    """
    display_config.ROOT = ROOT
    cfg = display_config.load_config()
    legacy = _read_wifi_json()
    for key in ("ssid", "hostname"):
        if not cfg.get(key) and legacy.get(key):
            cfg[key] = legacy[key]
    if not mit_passwort:
        cfg["password_gesetzt"] = bool(cfg.get("password") or legacy.get("password"))
        cfg["password"] = ""
    elif not cfg.get("password") and legacy.get("password"):
        cfg["password"] = legacy["password"]
    return cfg


def config_schreiben(data):
    """Store the configuration. An empty password field deletes nothing."""
    display_config.ROOT = ROOT
    return config_lesen() if not data else display_config.save_config(data)


# ---------------------------------------------------------------- API handlers

def api_state(req):
    info = mcp_tools.tool_device_info()
    response = {
        "ip": None,
        "heap": info.get("gc_free"),
        "uptime_s": info.get("uptime_s"),
        "freq_mhz": info.get("freq_mhz"),
        "wifi": info.get("wifi"),
        "screen": mcp_screen.describe(),
        "memory": memory_info(),
    }
    try:
        wlan = info.get("wifi") or {}
        if isinstance(wlan, dict) and wlan.get("ifconfig"):
            response["ip"] = wlan["ifconfig"][0]
    except Exception:  # noqa: BLE001
        pass
    return mcp_httpd.json_response(response)


def api_exec(req):
    """Run code. Body: JSON {"code": "..."} or plain text."""
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
        return mcp_httpd.json_response({"ok": False, "output": "no code given"}, 400)
    try:
        output = mcp_tools.tool_exec(text)
    except Exception as exc:  # noqa: BLE001
        return mcp_httpd.json_response(
            {"ok": False, "output": "%s: %s" % (type(exc).__name__, exc)}, 500)
    return mcp_httpd.json_response({"ok": True, "output": output})


def api_log(req):
    return mcp_httpd.text(200, mcp_logbuf.logs(clear=req.arg("clear") == "1"))


def api_files(req):
    try:
        entries = dir_entries(req.arg("path", "/"))
    except OSError as exc:
        return mcp_httpd.json_response({"error": "listdir: %s" % exc, "path": req.arg("path", "/")}, 404)
    return mcp_httpd.json_response({
        "path": req.arg("path", "/"),
        "entries": entries,
        "memory": memory_info(),
    })


def api_file_get(req):
    path = req.arg("path")
    if not path:
        return mcp_httpd.json_response({"error": "path missing"}, 400)
    target = real_path(path)
    try:
        with open(target, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        return mcp_httpd.json_response({"error": "read: %s" % exc}, 404)
    if req.arg("download") == "1":
        name = target.rsplit("/", 1)[-1]
        return mcp_httpd.Response(200, data, {
            "Content-Type": "application/octet-stream",
            "Content-Disposition": 'attachment; filename="%s"' % name,
        })
    try:
        return mcp_httpd.json_response({"path": path, "data": data.decode("utf-8"), "binary": False})
    except UnicodeError:
        return mcp_httpd.json_response(
            {"path": path, "binary": True, "size": len(data),
             "hinweis": "binary file -- download only"}, 200)


def api_file_put(req):
    """Write a file. Body = content (raw), path via ?path= or JSON {"path","data"}."""
    path = req.arg("path")
    data = req.body or b""
    if not path and data[:1] == b"{":
        try:
            payload = json.loads(data.decode("utf-8"))
            path = payload.get("path")
            data = payload.get("data", "").encode("utf-8")
        except ValueError:
            return mcp_httpd.json_response({"error": "JSON unreadable"}, 400)
    if not path:
        return mcp_httpd.json_response({"error": "path missing"}, 400)
    if len(data) > MAX_UPLOAD:
        return mcp_httpd.json_response({"error": "too large (max %d)" % MAX_UPLOAD}, 413)
    target = real_path(path)
    parent = target.rsplit("/", 1)[0]
    if parent and not is_dir(parent):
        try:
            os.mkdir(parent)
        except OSError:
            pass
    try:
        with open(target, "wb") as fh:
            fh.write(data)
    except OSError as exc:
        return mcp_httpd.json_response({"error": "write: %s" % exc}, 500)
    return mcp_httpd.json_response({"ok": True, "path": path, "bytes": len(data)})


def api_file_delete(req):
    data = req.json()
    path = data.get("path")
    if not path:
        return mcp_httpd.json_response({"error": "path missing"}, 400)
    target = real_path(path)
    try:
        if is_dir(target):
            os.rmdir(target)
        else:
            os.remove(target)
    except OSError as exc:
        return mcp_httpd.json_response({"error": "delete: %s" % exc}, 500)
    return mcp_httpd.json_response({"ok": True, "path": path})


def api_file_mkdir(req):
    data = req.json()
    path = data.get("path")
    if not path:
        return mcp_httpd.json_response({"error": "path missing"}, 400)
    try:
        os.mkdir(real_path(path))
    except OSError as exc:
        return mcp_httpd.json_response({"error": "mkdir: %s" % exc}, 500)
    return mcp_httpd.json_response({"ok": True, "path": path})


def api_file_rename(req):
    data = req.json()
    old, new = data.get("old"), data.get("new")
    if not old or not new:
        return mcp_httpd.json_response({"error": "old/new missing"}, 400)
    target = real_path(new)
    try:
        os.rename(real_path(old), target)
    except OSError as exc:
        return mcp_httpd.json_response({"error": "rename: %s" % exc}, 500)
    return mcp_httpd.json_response({"ok": True, "path": new})


def api_config(req):
    if req.method == "POST":
        data = req.json()
        if not isinstance(data, dict):
            return mcp_httpd.json_response({"error": "object expected"}, 400)
        try:
            cfg = config_schreiben(data)
        except OSError as exc:
            return mcp_httpd.json_response({"error": "save: %s" % exc}, 500)
        return mcp_httpd.json_response({"ok": True, "config": cfg})
    return mcp_httpd.json_response({"config": config_lesen()})


def api_screen(req):
    scale = int(req.arg("scale", "2"))
    data, width, height, swap = mcp_screen.capture(scale=scale)
    from mcp_png import encode_rgb565_png
    blob = encode_rgb565_png(data, width, height, byte_swap=swap)
    return mcp_httpd.Response(200, blob, {"Content-Type": "image/png",
                                          "Cache-Control": "no-store"})


def api_drivers(req):
    """Driver files present on the device -- the basis of the selection lists."""
    drivers = display_config.available_drivers()
    drivers["chip"] = display_config.chip_name()
    return mcp_httpd.json_response(drivers)


def api_profiles(req):
    """Board profiles for this firmware's chip, plus the current configuration."""
    display_config.ROOT = ROOT
    return mcp_httpd.json_response({
        "chip": display_config.chip_name(),
        "profiles": display_config.load_profiles(),
        "config": config_lesen(),
    })


def portal_redirect(req):
    """Captive portal: send every unknown request to the setup page."""
    return portal.redirect_to_setup(req)


def _app_loader():
    """app_loader imports LVGL, which does not exist on a host -- import lazily."""
    import app_loader
    return app_loader


def api_apps(req):
    """Applications present on the device (from /apps)."""
    try:
        loader = _app_loader()
    except ImportError as exc:
        return mcp_httpd.json_response({"apps": [], "error": str(exc)})
    return mcp_httpd.json_response({"apps": loader.list_apps(include_launcher=True),
                                    "running": loader.running_app()})


def api_app(req):
    """Switch the running application at runtime (serviced in the LVGL thread)."""
    if req.method != "POST":
        return mcp_httpd.json_response({"error": "POST expected"}, 405)
    data = req.json()
    name = (data or {}).get("name") if isinstance(data, dict) else None
    if not name:
        return mcp_httpd.json_response({"error": "name missing"}, 400)
    try:
        loader = _app_loader()
    except ImportError as exc:
        return mcp_httpd.json_response({"error": str(exc)}, 503)
    if name not in loader.app_names():
        return mcp_httpd.json_response({"error": "unknown application: %s" % name}, 404)
    loader.request_app(name)
    return mcp_httpd.json_response({"ok": True, "requested": name,
                                    "running": loader.running_app()})


def setup_routes():
    """Restricted route table for setup mode.

    The access point is open, so it serves configuration only: no MCP tools, no
    code execution, no file access. Every unknown path is redirected to /setup,
    which is what makes the captive portal work. "GET *" is a prefix route (empty
    prefix) and is only used after all exact matches failed.
    """
    return {
        "GET /": statisch("setup.html"),
        "GET /setup": statisch("setup.html"),
        "GET /setup.js": statisch("setup.js"),
        "GET /app.css": statisch("app.css"),
        "GET /favicon.ico": favicon,
        "GET /api/config": api_config,
        "POST /api/config": api_config,
        "GET /api/profiles": api_profiles,
        "GET /api/drivers": api_drivers,
        "GET /api/state": api_state,
        "POST /api/reset": api_reset,
        "GET /api/log": api_log,          # diagnosis: did the boot fall back to setup?
        "GET *": portal_redirect,
        "POST *": portal_redirect,
        "PUT *": portal_redirect,
        "DELETE *": portal_redirect,
    }


def api_reset(req):
    return mcp_httpd.json_response({"result": mcp_tools.tool_reset(500)})


def build_routes():
    return {
        "GET /": statisch("index.html"),
        "GET /ui": statisch("index.html"),
        "GET /index.html": statisch("index.html"),
        "GET /setup": statisch("setup.html"),
        "GET /setup.js": statisch("setup.js"),
        "GET /app.css": statisch("app.css"),
        "GET /app.js": statisch("app.js"),
        "GET /api/drivers": api_drivers,
        "GET /api/profiles": api_profiles,
        "GET /api/apps": api_apps,
        "POST /api/app": api_app,
        "GET /editor/*": web_tree,          # bundled code editor (CodeMirror)
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
    """Plain-text status -- kept for a quick look with curl."""
    return mcp_httpd.text(200, "esp32 debug server\n%s\nUI: http://<ip>/\ntools:\n%s\n" % (
        mcp_screen.describe(),
        "\n".join("  %s" % t.name for t in mcp_tools.build_tools())))


def page(req):
    """Compatibility: "/" serves the start page of the UI."""
    return statisch("index.html")(req)


# ---------------------------------------------------------------- UI files

# HTML, CSS and JS live as real files in firmware/webfiles/ (on the device: /web).
# Reason: inside a Python string escaping errors otherwise arise -- in the first
# version, "\n" in JS strings became real line breaks, so the whole script could no
# longer be parsed and the UI stayed without function. Besides, the files are thus
# editable via the file manager.

WEB_DIR = "web"
CONTENT_TYPES = {".html": "text/html; charset=utf-8",
                 ".css": "text/css; charset=utf-8",
                 ".js": "application/javascript; charset=utf-8",
                 ".txt": "text/plain; charset=utf-8",
                 ".png": "image/png",
                 ".svg": "image/svg+xml; charset=utf-8",
                 ".json": "application/json"}


def read_web_file(name):
    with open(ROOT + "/" + WEB_DIR + "/" + name, "rb") as fh:
        return fh.read()


def content_type(name):
    for suffix, ctype in CONTENT_TYPES.items():
        if name.endswith(suffix):
            return ctype
    return "application/octet-stream"


def statisch(name):
    """Server for a UI file (without cache -- changes in the file manager should
    take effect immediately). The content is sent in chunks."""

    def handler(req):
        target = ROOT + "/" + WEB_DIR + "/" + name
        try:
            with open(target, "rb"):
                pass
        except OSError as exc:
            return mcp_httpd.text(
                500, "%s missing on the device (%s)\n-- copy firmware/webfiles/ with deploy.sh"
                % (name, exc))
        return mcp_httpd.Response(200, b"", {"Content-Type": content_type(name),
                                            "Cache-Control": "no-store"}, datei=target)
    return handler


def favicon(req):
    return mcp_httpd.Response(204, b"", {})


def web_tree(req):
    """Serve files of the bundled editor (prefix route /editor/*).

    The path comes from the browser and is therefore checked strictly: only the tree
    <WEB_DIR>/editor, and no ".." inside it.
    """
    name = req.path.lstrip("/")
    allowed = name.startswith("editor/") and ".." not in name and "//" not in name
    if not allowed:
        return mcp_httpd.text(403, "path not allowed")
    target = ROOT + "/" + WEB_DIR + "/" + name
    try:
        with open(target, "rb"):
            pass
    except OSError as exc:
        return mcp_httpd.text(404, "%s not found (%s)" % (name, exc))
    return mcp_httpd.Response(200, b"", {"Content-Type": content_type(name),
                                         "Cache-Control": "no-store"}, datei=target)
