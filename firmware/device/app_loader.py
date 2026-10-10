# app_loader.py -- start MicroPython/LVGL applications and switch between them at
# runtime.
#
# Applications live as single files under /apps (firmware/apps in the repo) and
# follow one small contract:
#
#   TITLE / DESCRIPTION   short texts for the launcher
#   start(parent=None)    builds the UI on the active screen, returns a handle
#                         whose stop() removes the timers and objects again
#
# LVGL is not thread safe, so applications are started and stopped only from the
# main loop: another thread (the web UI) only stores a request, which
# service_requests() picks up on the next iteration.
#
# The module is importable on a host: lvgl is missing there, and everything that
# touches it checks that first.

import os
import sys

try:
    import lvgl as lv
except ImportError:              # host test: no LVGL, only the bookkeeping is used
    lv = None

try:
    import mcp_logbuf
except ImportError:              # host test without the debug server
    mcp_logbuf = None

APPS_ROOT = "/apps"              # overridden by ROOT in host tests
DEFAULT_APP = "launcher"
MAX_SEARCH_DEPTH = 2             # /apps holds flat files; be tolerant anyway

_state = {"name": None, "handle": None, "module": None, "error": None}
_pending = {"name": None}
_lock = None                     # created lazily: _thread does not exist everywhere


def _log(text):
    if mcp_logbuf is not None:
        mcp_logbuf.log(text)
    else:
        print(text)


def _thread_lock():
    global _lock
    if _lock is None:
        try:
            import _thread
            _lock = _thread.allocate_lock()
        except ImportError:
            _lock = False        # host without threads: no lock needed
    return _lock


# ------------------------------------------------------------------ listing

def _literal(line):
    """Value of a `KEY = "text"` line, or an empty string."""
    if "=" not in line:
        return ""
    value = line.split("=", 1)[1].strip()
    if len(value) >= 2 and value[0] in ("'", '"') and value[-1] == value[0]:
        return value[1:-1]
    return ""


def _metadata(stem, path):
    """Title and description without importing the module.

    Reading two lines of text is cheap; importing every application at boot would
    pull in LVGL code and memory for apps that may never be started.
    """
    title, description = stem, ""
    try:
        with open(path) as fh:
            for line in fh:
                if line.startswith("TITLE"):
                    title = _literal(line) or stem
                elif line.startswith("DESCRIPTION"):
                    description = _literal(line)
                if description and title != stem:
                    break
    except (OSError, UnicodeError):
        pass
    return title, description


def _scan(directory, depth=0):
    found = {}
    try:
        entries = os.listdir(directory or "/")
    except OSError:
        return found
    for name in entries:
        path = (directory + "/" + name) if directory not in ("", "/") else "/" + name
        if name.endswith(".py") and not name.startswith("_"):
            found[name[:-3]] = path
        elif depth < MAX_SEARCH_DEPTH and not name.startswith("."):
            try:
                os.listdir(path)              # a directory is one that can be listed
                found.update(_scan(path, depth + 1))
            except OSError:
                pass
    return found


def list_apps(include_launcher=False):
    """Applications on the device: [{"name", "title", "description"}]."""
    apps = []
    for stem, path in sorted(_scan(APPS_ROOT).items()):
        if stem == DEFAULT_APP and not include_launcher:
            continue
        title, description = _metadata(stem, path)
        apps.append({"name": stem, "title": title, "description": description})
    return apps


def app_names():
    return [entry["name"] for entry in list_apps(include_launcher=True)]


# ------------------------------------------------------------------ start/stop

def _clean_screen():
    """Remove the objects of the previous screen."""
    if lv is None:
        return
    try:
        lv.screen_active().clean()
    except Exception as exc:  # noqa: BLE001
        _log("app_loader: screen could not be cleared (%s)" % exc)


def import_app(name):
    """Import an application module by name. Rejects anything with a path."""
    name = (name or "").strip()
    if name.endswith(".py"):
        name = name[:-3]
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise ValueError("invalid application name: %r" % name)
    if APPS_ROOT not in sys.path:
        sys.path.insert(0, APPS_ROOT)
    if name in sys.modules:
        return sys.modules[name]
    return __import__(name)


def stop_app():
    """Stop the running application. Never raises: a switch must always work."""
    handle = _state["handle"]
    _state.update(name=None, handle=None, module=None)
    if handle is None:
        return
    stop = getattr(handle, "stop", None)
    if stop is None:
        _log("app_loader: handle has no stop()")
        return
    try:
        stop()
    except Exception as exc:  # noqa: BLE001
        _log("app_loader: stop failed -- %s: %s" % (type(exc).__name__, exc))


def start_app(name=None):
    """Start an application on the active screen. Returns its handle."""
    name = (name or DEFAULT_APP).strip()
    if _state["name"] == name and _state["handle"] is not None:
        return _state["handle"]
    stop_app()
    module = import_app(name)
    start = getattr(module, "start", None)
    if start is None:
        raise ValueError("application %r has no start()" % name)
    _clean_screen()
    handle = start()
    _state.update(name=name, handle=handle, module=module, error=None)
    _log("app_loader: started %s" % name)
    return handle


def running_app():
    return _state["name"]


# ------------------------------------------------------------------ runtime switch

def request_app(name):
    """Ask the main loop to switch to `name`. Safe from any thread."""
    lock = _thread_lock()
    if lock:
        lock.acquire()
    try:
        _pending["name"] = name
    finally:
        if lock:
            lock.release()
    return name


def service_requests():
    """Run from the main loop: starts a requested application (once, in this thread)."""
    lock = _thread_lock()
    if lock:
        lock.acquire()
    try:
        name = _pending["name"]
        _pending["name"] = None
    finally:
        if lock:
            lock.release()
    if name is None:
        return
    try:
        start_app(name)
    except Exception as exc:  # noqa: BLE001
        _state["error"] = "%s: %s" % (type(exc).__name__, exc)
        _log("app_loader: could not start %s -- %s" % (name, _state["error"]))


def pending_app():
    return _pending["name"]


def last_error():
    return _state["error"]
