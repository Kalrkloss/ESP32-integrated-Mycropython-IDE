# launcher.py -- dashboard listing the applications on the device.
#
# Tapping a row asks app_loader to switch. The switch deliberately does NOT happen
# inside the click callback: deleting the objects of the screen we are currently
# dispatching an event for would be a use-after-free. app_loader stores the request
# and the main loop starts the application on its next iteration.

import lvgl as lv

import app_loader

TITLE = "Launcher"
DESCRIPTION = "Pick one of the example applications."
TITEL = TITLE
BESCHREIBUNG = DESCRIPTION

BG = 0xEFF3F8
CARD = 0xFFFFFF
CARD_ACTIVE = 0xDCE8F5
LINE = 0xD3DCE6
FG = 0x16202C
DIM = 0x5A6B7C
HEADER = 0x1B5E9C
HEADER_TEXT = 0xFFFFFF
HEADER_DIM = 0xC9DEF2
ACCENT = 0x1B5E9C


def _font(size, fallback):
    font = getattr(lv, "font_montserrat_%d" % size, None)
    if font is None:
        font = getattr(lv, "font_montserrat_%d" % fallback, None)
    return font


def _style(obj, bg=None, radius=None, border=None):
    if bg is not None:
        obj.set_style_bg_color(lv.color_hex(bg), 0)
        obj.set_style_bg_opa(lv.OPA.COVER, 0)
    if radius is not None:
        obj.set_style_radius(radius, 0)
    if border is not None:
        obj.set_style_border_width(0, 0)


def start(parent=None):
    screen = parent or lv.screen_active()
    try:
        screen.set_style_bg_color(lv.color_hex(BG), 0)
        screen.set_style_pad_all(0, 0)
    except Exception:  # noqa: BLE001
        pass

    created = []

    header = lv.obj(screen)
    header.set_size(320, 56)
    header.set_pos(0, 0)
    _style(header, bg=HEADER)
    created.append(header)

    title = lv.label(header)
    title.set_text("ESP32-S3 BOARD")
    title.set_style_text_color(lv.color_hex(HEADER_TEXT), 0)
    font_title = _font(20, 16)
    if font_title is not None:
        title.set_style_text_font(font_title, 0)
    title.align(lv.ALIGN.LEFT_MID, 12, -8)

    subtitle = lv.label(header)
    subtitle.set_text("choose an application")
    subtitle.set_style_text_color(lv.color_hex(HEADER_DIM), 0)
    subtitle.align(lv.ALIGN.LEFT_MID, 12, 12)

    apps = app_loader.list_apps()
    if not apps:
        note = lv.label(screen)
        note.set_text("No applications found in /apps.\nCopy files with\n"
                      "tools/deploy.sh apps")
        note.set_style_text_color(lv.color_hex(DIM), 0)
        note.align(lv.ALIGN.CENTER, 0, 0)
        created.append(note)
    else:
        listbox = lv.obj(screen)
        listbox.set_size(320, 480 - 56)
        listbox.set_pos(0, 56)
        _style(listbox, bg=BG)
        listbox.set_style_pad_all(6, 0)
        listbox.set_style_pad_row(6, 0)
        listbox.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        listbox.set_scroll_dir(lv.DIR.VER)
        created.append(listbox)

        for entry in apps:
            row = lv.obj(listbox)
            row.set_size(308, 72)
            _style(row, bg=CARD, radius=10)
            row.add_flag(lv.obj.FLAG.CLICKABLE)
            row.set_style_border_width(2, 0)
            row.set_style_border_color(lv.color_hex(LINE), 0)
            created.append(row)

            name = lv.label(row)
            name.set_text(entry["title"] or entry["name"])
            name.set_style_text_color(lv.color_hex(FG), 0)
            font_name = _font(18, 16)
            if font_name is not None:
                name.set_style_text_font(font_name, 0)
            name.align(lv.ALIGN.TOP_LEFT, 12, 10)

            description = lv.label(row)
            description.set_text(entry["description"] or entry["name"])
            description.set_style_text_color(lv.color_hex(DIM), 0)
            description.set_width(284)
            description.align(lv.ALIGN.TOP_LEFT, 12, 34)

            arrow = lv.label(row)
            arrow.set_text(">")
            arrow.set_style_text_color(lv.color_hex(ACCENT), 0)
            arrow.align(lv.ALIGN.RIGHT_MID, -12, 8)

            def on_click(_event, target=entry["name"], widget=row):
                widget.set_style_bg_color(lv.color_hex(CARD_ACTIVE), 0)
                app_loader.request_app(target)

            row.add_event_cb(on_click, lv.EVENT.CLICKED, None)

    state = lv.label(screen)
    state.set_text("running: %s" % (app_loader.running_app() or "-"))
    state.set_style_text_color(lv.color_hex(DIM), 0)
    state.align(lv.ALIGN.BOTTOM_LEFT, 12, -8)
    created.append(state)

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
