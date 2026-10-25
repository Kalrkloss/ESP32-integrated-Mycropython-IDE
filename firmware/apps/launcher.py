# launcher.py -- dashboard listing the applications on the device.
#
# Tapping a row asks app_loader to switch. The switch deliberately does NOT happen
# inside the click callback: deleting the objects of the screen we are currently
# dispatching an event for would be a use-after-free. app_loader stores the request
# and the main loop starts the application on its next iteration.
#
# Look and feel comes from _ui (tokens + widgets); this file only composes.

import lvgl as lv

import _ui as ui
import app_loader

TITLE = "Launcher"
DESCRIPTION = "Pick one of the example applications."
TITEL = TITLE
BESCHREIBUNG = DESCRIPTION

ROW_H = 80


def _app_row(parent, entry):
    row = ui.card(parent, 0, 0, 304, ROW_H)
    row.set_style_bg_color(lv.color_hex(ui.SURFACE_ALT), ui._state(ui.MAIN, ui.STATE_PRESSED))

    ui.label(row, entry["title"] or entry["name"], ui.S4, ui.S2, size=20)
    description = entry["description"] or entry["name"]
    text = ui.label(row, description, ui.S4, ui.S2 + 26, size=14, color=ui.DIM, width=248)
    text.set_height(34)
    ui.label(row, ">", -ui.S4, 0, size=20, color=ui.DIM, align=lv.ALIGN.RIGHT_MID)

    def on_click(name=entry["name"]):
        app_loader.request_app(name)

    return ui.tap(row, on_click)


def start(parent=None):
    screen = ui.screen(parent)
    apps = app_loader.list_apps()
    ui.header(screen, "Applications", "%d on this board" % len(apps))
    created = [screen]

    list_top = ui.HEADER_H + ui.S2
    list_height = 480 - list_top - ui.FOOTER_H - ui.S2

    if not apps:
        empty = ui.card(screen, ui.S4, list_top, 288, 120)
        ui.label(empty, "No applications in /apps", 0, ui.S4, size=16, color=ui.TEXT,
                 align=lv.ALIGN.TOP_MID)
        ui.label(empty, "Copy files with tools/deploy.sh apps", 0, ui.S4 + 28, size=12,
                 color=ui.DIM, align=lv.ALIGN.TOP_MID)
        created.append(empty)
    else:
        listed = ui.box(screen, ui.S2, list_top, 304, list_height)
        listed.set_style_pad_row(ui.S2, 0)
        listed.set_style_pad_all(0, 0)
        listed.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        listed.set_scroll_dir(lv.DIR.VER)
        ui.show_scrollbar(listed, True)
        created.append(listed)
        for entry in apps:
            created.append(_app_row(listed, entry))

    ui.footer(screen, "running: %s" % (app_loader.running_app() or "-"))

    return _Handle(created)


class _Handle:
    """Returns the objects so the next application starts on a clean screen."""

    def __init__(self, objects):
        self.objects = objects

    def stop(self):
        while self.objects:
            obj = self.objects.pop()
            try:
                obj.delete()
            except Exception:  # noqa: BLE001
                pass
