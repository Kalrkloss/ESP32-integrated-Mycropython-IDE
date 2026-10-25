# calculator.py -- Calculator for the JC3248W535 (ESP32-S3, 320x480, LVGL 9).
#
# Self-contained LVGL app. Public API used by app_loader / launcher:
#   TITLE / DESCRIPTION      short texts for the launcher (TITEL/BESCHREIBUNG aliases)
#   start(parent=None)       builds the UI, returns a handle with .stop()
#
# The keypad builds an expression string; it is evaluated with a strict whitelist
# so no arbitrary code can be entered from the touch panel.
#
# Look and feel comes from _ui (tokens + widgets); this file only composes.

import lvgl as lv

import _ui as ui

TITLE = "Calculator"
DESCRIPTION = "A four function calculator with a large touch keypad."
TITEL = TITLE
BESCHREIBUNG = DESCRIPTION

ALLOWED = set("0123456789.+-*/() ")

# Keypad geometry: 4 columns of 66 px and 8 px gaps fill the 288 px content width,
# five 52 px rows fill the band between the display and the footer.
KEY_W = 66
KEY_H = 52
KEY_GAP = ui.S2
KEYS_X = ui.S4
KEYS_Y = 160

FUNCTIONS = "/*-+()C<"

DISPLAY_Y = ui.HEADER_H + ui.S3
DISPLAY_H = 80
CONTENT_W = 320 - 2 * ui.S4          # 288


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
        self.root_ = ui.screen(self.parent)
        self.header = ui.header(self.root_, TITLE, "Tap = to evaluate")

        # Two-line readout: the expression on top, the result underneath it.
        display = ui.card(self.root_, ui.S4, DISPLAY_Y, CONTENT_W, DISPLAY_H)
        self.screen_label = ui.label(display, "0", -ui.S3, ui.S2, size=32, color=ui.TEXT,
                                     align=lv.ALIGN.TOP_RIGHT)
        self.result_label = ui.label(display, "", -ui.S3, -ui.S2, size=20, color=ui.DIM,
                                     align=lv.ALIGN.BOTTOM_RIGHT)

        for r, row in enumerate(self.KEYS):
            for c, text in enumerate(row):
                x = KEYS_X + c * (KEY_W + KEY_GAP)
                y = KEYS_Y + r * (KEY_H + KEY_GAP)
                self._key(x, y, text)

        ui.footer(self.root_, "four function  -  ( ) group  -  < deletes")

    def _kind(self, text):
        """Digit keys are neutral, function keys outline, the commit key is filled."""
        if text == "=":
            return "primary"
        if text in FUNCTIONS:
            return "quiet"
        return "ghost"

    def _key(self, x, y, text):
        btn = ui.button(self.root_, text, x, y, width=KEY_W, height=KEY_H,
                        callback=lambda t=text: self._press(t),
                        kind=self._kind(text), radius=ui.R_MD)
        # ui.button is sized for a 140 px wide button; a keypad tile carries a single
        # glyph and reads better at the 24 px step, so the caption is lifted here.
        face = ui.font(24)
        if face is not None and hasattr(btn, "get_child"):
            try:
                btn.get_child(0).set_style_text_font(face, 0)
            except Exception:  # noqa: BLE001 - binding without child access
                pass
        return btn

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
            value = int(value) if float(value) == int(float(value)) else round(value, 6)
        except (ValueError, TypeError, OverflowError):
            self.result_label.set_text("error")
            return
        self.result_label.set_text("= %s" % value)

    # ------------------------------------------------------------- lifecycle
    def stop(self):
        try:
            # root_ is the display's active screen -- clean it, never delete it.
            self.root_.clean()
        except Exception:  # noqa: BLE001
            pass


def start(parent=None):
    """Build the calculator on `parent` (default: the active screen). Returns a handle."""
    return _Calculator(parent if parent is not None else lv.screen_active())
