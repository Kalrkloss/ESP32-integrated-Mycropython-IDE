# calculator.py -- Calculator for the JC3248W535 (ESP32-S3, 320x480, LVGL 9).
#
# Self-contained LVGL app. Public API used by app_loader / launcher:
#   TITLE / DESCRIPTION      short texts for the launcher (TITEL/BESCHREIBUNG aliases)
#   start(parent=None)       builds the UI, returns a handle with .stop()
#
# Rules kept: only lvgl + stdlib, full cleanup in stop(), touch targets >= 40x40 px.
# The keypad builds an expression string; it is evaluated with a strict whitelist
# so no arbitrary code can be entered from the touch panel.

import lvgl as lv

TITLE = "Calculator"
DESCRIPTION = "A four function calculator with a large touch keypad."
TITEL = TITLE
BESCHREIBUNG = DESCRIPTION

BG = 0x101820
DISPLAY = 0x18242E
KEY = 0x2C3646
KEY_OP = 0x3A6EA5
KEY_ACC = 0xC08030
TEXT = 0xFFFFFF

ALLOWED = set("0123456789.+-*/() ")


def _font(size):
    f = getattr(lv, "font_montserrat_%d" % size, None)
    if f is None:
        f = lv.font_montserrat_16
    return f


def _zero_pad(obj):
    for name in ("set_style_pad_all", "set_style_pad_row", "set_style_pad_column"):
        fn = getattr(obj, name, None)
        if fn is not None:
            try:
                fn(0, 0)
            except Exception:  # noqa: BLE001
                pass


def _rect(parent, x, y, w, h, color, radius=0):
    obj = lv.obj(parent)
    obj.set_pos(x, y)
    obj.set_size(w, h)
    obj.set_style_bg_color(lv.color_hex(color), 0)
    obj.set_style_radius(radius, 0)
    obj.set_style_border_width(0, 0)
    _zero_pad(obj)
    return obj


def _label(parent, text, x, y, color, size=16):
    lab = lv.label(parent)
    lab.set_text(text)
    lab.set_style_text_color(lv.color_hex(color), 0)
    lab.set_style_text_font(_font(size), 0)
    lab.set_pos(x, y)
    return lab


class _Calculator:
    KEYS = [
        ["C", "(", ")", "/"],
        ["7", "8", "9", "*"],
        ["4", "5", "6", "-"],
        ["1", "2", "3", "+"],
        ["0", ".", "<", "="],
    ]

    def __init__(self, parent):
        self.parent = parent
        self.expr = ""
        self._build()

    def _build(self):
        self.root_ = lv.obj(self.parent)
        self.root_.set_pos(0, 0)
        self.root_.set_size(320, 480)
        self.root_.set_style_bg_color(lv.color_hex(BG), 0)
        self.root_.set_style_border_width(0, 0)
        _zero_pad(self.root_)

        box = _rect(self.root_, 8, 8, 304, 96, DISPLAY, radius=10)
        self.screen_label = _label(box, "0", 10, 20, TEXT, 32)
        self.result_label = _label(box, "", 10, 62, 0x8FD4FF, 18)

        # Keypad: 4 columns x 5 rows, each key 72x66 -> touch targets well over 40.
        key_w, key_h = 72, 66
        gap = 4
        left = 8
        top = 116
        for r, row in enumerate(self.KEYS):
            for c, text in enumerate(row):
                x = left + c * (key_w + gap)
                y = top + r * (key_h + gap)
                if text == "=":
                    bg = KEY_ACC
                elif text in "/*-+()":
                    bg = KEY_OP
                else:
                    bg = KEY
                self._key(x, y, key_w, key_h, text, bg)

    def _key(self, x, y, w, h, text, bg):
        btn = _rect(self.root_, x, y, w, h, bg, radius=8)
        btn.add_flag(lv.obj.FLAG.CLICKABLE)
        lab = _label(btn, text, 0, 0, TEXT, 24)
        lab.center()
        btn.add_event_cb(lambda _e, t=text: self._press(t), lv.EVENT.CLICKED, None)

    def _press(self, key):
        if key == "C":
            self.expr = ""
        elif key == "<":
            self.expr = self.expr[:-1]
        elif key == "=":
            self._evaluate()
            return
        else:
            self.expr += key
        self.screen_label.set_text(self.expr or "0")

    def _evaluate(self):
        text = self.expr
        if not text or set(text) - ALLOWED:
            self.result_label.set_text("invalid")
            return
        try:
            value = eval(text, {"__builtins__": {}}, {})   # noqa: S307 - whitelisted input
        except Exception:  # noqa: BLE001
            self.result_label.set_text("error")
            return
        try:
            value = int(value) if float(value).is_integer() else round(value, 6)
        except (ValueError, TypeError, OverflowError):
            self.result_label.set_text("error")
            return
        self.result_label.set_text("= %s" % value)

    # ------------------------------------------------------------- lifecycle
    def stop(self):
        try:
            self.root_.delete()
        except Exception:  # noqa: BLE001
            pass


def start(parent=None):
    """Build the calculator on `parent` (default: the active screen). Returns a handle."""
    return _Calculator(parent if parent is not None else lv.screen_active())
