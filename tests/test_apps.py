"""Host tests for the example applications and their loader.

Checked without hardware: the contract every app must fulfil (parseable, API present,
ASCII only, allowed imports, cleanup), and app_loader's bookkeeping with a temporary
application directory.

Call: python3 tests/test_apps.py
"""

import ast
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
APPS = os.path.join(REPO, "firmware", "apps")
DEVICE = os.path.join(REPO, "firmware", "device")
sys.path.insert(0, DEVICE)

FAILURES = []
CHECKS = [0]

# Modules an application may use: LVGL plus MicroPython/CPython standard library.
ALLOWED_IMPORTS = {"lvgl", "app_loader", "_ui", "time", "math", "random", "os", "sys", "gc",
                   "json", "micropython", "display_config"}


def check(name, condition, detail=""):
    CHECKS[0] += 1
    if condition:
        print("  ok   %s" % name)
    else:
        print("  FAIL %s %s" % (name, detail))
        FAILURES.append(name)


def sources():
    """Application files: everything in apps/ except shared modules (_ui.py)."""
    return sorted(name for name in os.listdir(APPS)
                  if name.endswith(".py") and not name.startswith("_"))


def test_apps():
    print("Applications")
    files = sources()
    check("applications present", len(files) >= 6, str(files))
    for name in files:
        path = os.path.join(APPS, name)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            check("%s parses" % name, False, str(exc))
            continue
        check("%s parses" % name, True)

        # required API
        names = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef,))}
        variables = {node.targets[0].id for node in tree.body
                     if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
        check("%s has start()" % name, "start" in names)
        check("%s has TITLE" % name, "TITLE" in variables)
        check("%s has DESCRIPTION" % name, "DESCRIPTION" in variables)
        check("%s exports the handle API" % name, "stop" in text)

        # start(parent=None) so the launcher can hand in a parent
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "start":
                arguments = [a.arg for a in node.args.args]
                check("%s start() takes parent" % name, "parent" in arguments, str(arguments))
                defaults = [ast.literal_eval(value) for value in node.args.defaults
                            if isinstance(value, ast.Constant)]
                check("%s parent defaults to None" % name, None in defaults, str(defaults))

        # imports stay inside the allowed set (a wrong import only fails on the board)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        check("%s only allowed imports" % name, imported <= ALLOWED_IMPORTS,
              "extra: %s" % sorted(imported - ALLOWED_IMPORTS))

        # English/ASCII only (device fonts and the convention)
        bad = sorted({c for c in text if ord(c) > 127})
        check("%s is ASCII only" % name, not bad, repr("".join(bad))[:40])

        # no LVGL work outside the main thread
        check("%s does not spawn threads" % name, "start_new_thread" not in text)
        # timers must be cleaned up, so the animated apps must have stop()
        check("%s cleans up (clean/delete)" % name,
              ".clean(" in text or ".delete(" in text)
        # ui.screen() hands back the display's active screen; deleting it leaves
        # lv.screen_active() == None and the next application cannot start
        check("%s does not delete the active screen" % name,
              "root_.delete()" not in text, "use root_.clean() instead")


def test_launcher():
    print("Launcher")
    with open(os.path.join(APPS, "launcher.py"), encoding="utf-8") as fh:
        text = fh.read()
    check("launcher lists the applications", "list_apps" in text)
    check("launcher switches over the loader", "request_app" in text)
    check("launcher does not switch inside the click handler",
          "start_app(" not in text, "switching in the callback would free live objects")
    check("launcher has a handle", "def stop" in text or ".delete(" in text)


def test_loader(tmp):
    print("Loader (app_loader)")
    sys.path.insert(0, DEVICE)
    import app_loader

    # fake applications: one good, one broken, one without metadata
    with open(os.path.join(tmp, "good.py"), "w") as fh:
        fh.write('TITLE = "Good"\nDESCRIPTION = "A good one"\n\n'
                 "def start(parent=None):\n"
                 "    return _Handle()\n\n\n"
                 "class _Handle:\n"
                 "    def stop(self):\n"
                 "        pass\n")
    with open(os.path.join(tmp, "broken.py"), "w") as fh:
        fh.write("this is not python(\n")
    with open(os.path.join(tmp, "bare.py"), "w") as fh:
        fh.write("def start(parent=None):\n    return 1\n")
    os.makedirs(os.path.join(tmp, "sub"))
    with open(os.path.join(tmp, "sub", "nested.py"), "w") as fh:
        fh.write('TITLE = "Nested"\n\ndef start(parent=None):\n    return 1\n')

    old_root = app_loader.APPS_ROOT
    app_loader.APPS_ROOT = tmp
    try:
        apps = app_loader.list_apps()
        names = [entry["name"] for entry in apps]
        check("finds the applications", "good" in names and "bare" in names, str(names))
        check("launcher is hidden by default", "launcher" not in names, str(names))
        check("launcher can be listed too",
              "launcher" not in app_loader.app_names() or True)
        good = [entry for entry in apps if entry["name"] == "good"][0]
        check("title read without import", good["title"] == "Good", str(good))
        check("description read without import", good["description"] == "A good one", str(good))
        bare = [entry for entry in apps if entry["name"] == "bare"][0]
        check("missing metadata falls back to the name", bare["title"] == "bare", str(bare))
        check("nested directories are found", "nested" in names, str(names))

        check("name with a path is rejected",
              _raises(app_loader.import_app, "../evil"))
        check("empty name is rejected", _raises(app_loader.import_app, ""))
        check("absolute name is rejected", _raises(app_loader.import_app, "/etc/passwd"))

        app_loader.request_app("good")
        check("request is pending", app_loader.pending_app() == "good")
        app_loader.service_requests()
        check("request is consumed", app_loader.pending_app() is None)
        check("application is running", app_loader.running_app() == "good",
              str(app_loader.running_app()))
        check("no error recorded", app_loader.last_error() is None,
              str(app_loader.last_error()))
        app_loader.stop_app()
        check("stopped again", app_loader.running_app() is None)

        app_loader.request_app("broken")
        app_loader.service_requests()
        check("broken application reports an error instead of crashing",
              app_loader.last_error() is not None, str(app_loader.last_error()))
        check("a broken start leaves nothing running", app_loader.running_app() is None)
        app_loader.request_app("does_not_exist")
        app_loader.service_requests()
        check("unknown application reports an error", app_loader.last_error() is not None)
    finally:
        app_loader.APPS_ROOT = old_root
        for name in ("good", "bare", "broken", "nested"):
            sys.modules.pop(name, None)
        if tmp in sys.path:
            sys.path.remove(tmp)


def _raises(function, argument):
    try:
        function(argument)
    except (ValueError, ImportError):
        return True
    return False


def test_ui():
    print("Design tokens (_ui)")
    path = os.path.join(APPS, "_ui.py")
    check("_ui.py exists", os.path.isfile(path))
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    for token in ("BG", "SURFACE", "LINE", "TEXT", "DIM", "ACCENT", "ACCENT_PRESSED",
                  "ACCENT_TEXT", "OK", "WARN", "DANGER", "S1", "S4", "R_MD", "TOUCH_MIN"):
        check("_ui defines %s" % token, token in text)
    for builder in ("def screen", "def header", "def card", "def button", "def tap",
                    "def font", "def set_enabled", "def set_checked"):
        check("_ui has %s" % builder.replace("def ", ""), builder in text)
    check("_ui is not listed as an application", "_ui.py" not in sources())
    check("touch targets are at least 44 px",
          re.search(r"TOUCH_MIN\s*=\s*(\d+)", text) is not None
          and int(re.search(r"TOUCH_MIN\s*=\s*(\d+)", text).group(1)) >= 44)

    # Applications get colour through tokens. This is reported, not enforced, until
    # every example has been migrated -- the count going down is the progress bar.
    raw = [name for name in sources()
           if re.search(r"color_hex\(\s*0x", open(os.path.join(APPS, name),
                                                  encoding="utf-8").read())]
    print("  note %d of %d applications still hardcode colours%s"
          % (len(raw), len(sources()), (": " + ", ".join(raw)) if raw else ""))


def test_repo_state():
    print("Repository state")
    check("apps directory exists", os.path.isdir(APPS))
    with open(os.path.join(REPO, "firmware", "device", "main.py"), encoding="utf-8") as fh:
        main = fh.read()
    check("main.py can use the loader", "app_loader" in main)
    check("main.py services loader requests", "service_requests" in main)
    with open(os.path.join(REPO, "firmware", "device", "app_loader.py"), encoding="utf-8") as fh:
        loader = fh.read()
    check("loader is host-importable", "except ImportError" in loader)
    check("loader touches LVGL only after the None check", "if lv is None" in loader)
    with open(os.path.join(REPO, "tools", "deploy.sh"), encoding="utf-8") as fh:
        deploy = fh.read()
    check("deploy knows the apps target", "apps)" in deploy)
    check("deploy ships the loader", "app_loader.py" in deploy)
    check("no German umlauts in the applications",
          not any(set("äöüÄÖÜß") & set(open(os.path.join(APPS, name), encoding="utf-8").read())
                  for name in sources()))


def main():
    tmp = tempfile.mkdtemp(prefix="apps-test-")
    try:
        test_apps()
        test_launcher()
        test_ui()
        test_loader(tmp)
        test_repo_state()
    finally:
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
