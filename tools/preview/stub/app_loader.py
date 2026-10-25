# stub/app_loader.py -- host stand-in for the device module.
#
# The launcher imports app_loader, which cannot run on a desktop (it scans /apps and
# drives the LVGL main loop). This stub answers the same API from the repository's
# firmware/apps directory so the launcher can be rendered off-device.

import os

# No os.path here: the unix port of this build exposes os.listdir but not os.path, and
# the stub runs on the same interpreter as the application. preview.py passes the
# directory in.
APPS_DIR = os.getenv("PREVIEW_APPS_DIR") or "firmware/apps"

_running = "launcher"
_requested = None


def _metadata(path, stem):
    title, description = stem, ""
    try:
        with open(path) as fh:
            for line in fh:
                if line.startswith("TITLE"):
                    title = line.split("=", 1)[1].strip().strip("\"'") or stem
                elif line.startswith("DESCRIPTION"):
                    description = line.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        pass
    return title, description


def list_apps(include_launcher=False):
    found = []
    for name in sorted(os.listdir(APPS_DIR)):
        if not name.endswith(".py") or name.startswith("_"):
            continue
        stem = name[:-3]
        if stem == "launcher" and not include_launcher:
            continue
        title, description = _metadata(APPS_DIR + "/" + name, stem)
        found.append({"name": stem, "title": title, "description": description})
    return found


def app_names():
    return [entry["name"] for entry in list_apps(include_launcher=True)]


def request_app(name):
    global _requested
    _requested = name


def pending_app():
    return _requested


def running_app():
    return _running


def start_app(name=None):
    global _running
    _running = name or _running
    return _running


def stop_app():
    return None


def service_requests():
    return None


def last_error():
    return None
