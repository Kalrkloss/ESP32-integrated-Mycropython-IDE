# _ui.py -- design tokens and shared widgets for the on-device applications.
#
# Files starting with "_" are not applications (app_loader skips them) and are not
# listed in the launcher. Import it with `import _ui as ui`.
#
# The point of this module is that nothing below the token block writes a raw colour,
# a raw radius or an ad-hoc font size: an application composes widgets and, if the look
# has to change, only this file changes. Contrast values are WCAG ratios measured
# against the surface they sit on.
#
# Panel: 320x480 portrait (JC3248W535), touch targets >= 44 px, 8 px spacing grid.

import lvgl as lv

# --------------------------------------------------------------------- palette
# Surfaces
BG = 0x0E141B              # screen background
SURFACE = 0x18222D         # cards, rows, panels
SURFACE_ALT = 0x22303E     # pressed/hover surface, grid gaps
LINE = 0x2A3947            # hairlines only -- never text (1.6:1 on BG, decorative)
GRID_LINE = 0x4F6377       # outline of touchable tiles: 3.0:1 on BG, the non-text minimum
# Text
TEXT = 0xF2F6FA            # 14.8:1 on SURFACE
DIM = 0x9FB0C0             # 7.2:1 on SURFACE, secondary lines only
# Accent
ACCENT = 0x1F6FEB          # white text on it: 4.6:1
ACCENT_PRESSED = 0x17509E
ACCENT_TEXT = 0xFFFFFF     # 4.6:1 on ACCENT, 6.7:1 on ACCENT_PRESSED
ACCENT_SOFT = 0x152438     # tinted surface for the selected row
# Semantic
OK = 0x3FB950
WARN = 0xD29922
DANGER = 0xF85149
# Game markers
MARK_X = 0x58B4F5
MARK_O = 0xE3B341

# --------------------------------------------------------------------- metrics
S1 = 4
S2 = 8
S3 = 12
S4 = 16
S5 = 24
S6 = 32

R_SM = 8
R_MD = 12
R_LG = 16
R_PILL = 999

TOUCH_MIN = 48             # every interactive widget is at least this tall
HEADER_H = 56
FOOTER_H = 24

FONT_SIZES = (12, 14, 16, 18, 20, 22, 24, 28, 32, 40, 48)


def font(size):
    """Largest compiled Montserrat at or below `size` -- never a silent jump to 16."""
    for candidate in sorted([s for s in FONT_SIZES if s <= size], reverse=True):
        face = getattr(lv, "font_montserrat_%d" % candidate, None)
        if face is not None:
            return face
    return getattr(lv, "font_montserrat_16", None)


def _state(*parts):
    """Selector from parts, tolerant about how the binding exposes them."""
    selector = 0
    for part in parts:
        if part is None:
            continue
        selector |= int(part)
    return selector


MAIN = getattr(getattr(lv, "PART", object), "MAIN", 0)
STATE_PRESSED = getattr(getattr(lv, "STATE", object), "PRESSED", 0)
STATE_CHECKED = getattr(getattr(lv, "STATE", object), "CHECKED", 0)
STATE_DISABLED = getattr(getattr(lv, "STATE", object), "DISABLED", 0)


# --------------------------------------------------------------------- building
def screen(parent=None, width=320, height=480):
    """The screen an app builds on, normalised to the token background."""
    obj = parent if parent is not None else lv.screen_active()
    obj.set_style_bg_color(lv.color_hex(BG), 0)
    obj.set_style_bg_opa(lv.OPA.COVER, 0)
    obj.set_style_border_width(0, 0)
    obj.set_style_radius(0, 0)
    obj.set_style_pad_all(0, 0)
    clear_scroll(obj)
    return obj


def clear_scroll(obj):
    remover = getattr(obj, "remove_flag", None)
    if remover is not None:
        try:
            remover(lv.obj.FLAG.SCROLLABLE)
        except Exception:  # noqa: BLE001 - flag missing on some builds
            pass


def box(parent, x, y, width, height, bg=None, radius=0):
    obj = lv.obj(parent)
    obj.set_pos(x, y)
    obj.set_size(width, height)
    obj.set_style_border_width(0, 0)
    obj.set_style_pad_all(0, 0)
    obj.set_style_radius(radius, 0)
    clear_scroll(obj)
    if bg is not None:
        obj.set_style_bg_color(lv.color_hex(bg), 0)
        obj.set_style_bg_opa(lv.OPA.COVER, 0)
    else:
        obj.set_style_bg_opa(lv.OPA.TRANSP, 0)
    return obj


def card(parent, x, y, width, height, bg=SURFACE, radius=R_MD, border=LINE):
    """A surface with a hairline border -- one level of elevation, never nested."""
    obj = box(parent, x, y, width, height, bg=bg, radius=radius)
    obj.set_style_border_width(1, 0)
    obj.set_style_border_color(lv.color_hex(border), 0)
    return obj


def label(parent, text, x=0, y=0, size=16, color=TEXT, align=None, width=None):
    lab = lv.label(parent)
    lab.set_text(text)
    lab.set_style_text_color(lv.color_hex(color), 0)
    face = font(size)
    if face is not None:
        lab.set_style_text_font(face, 0)
    if width is not None:
        lab.set_width(width)
        long_mode = getattr(getattr(lv, "LABEL_LONG", None), "WRAP", None)
        if long_mode is not None and hasattr(lab, "set_long_mode"):
            lab.set_long_mode(long_mode)
    if align is not None:
        lab.align(align, x, y)
    else:
        lab.set_pos(x, y)
    return lab


class _Header:
    """Band plus its labels. Native lv.obj cannot carry extra attributes, so the
    handles live in a plain Python object instead."""

    def __init__(self, band, title, subtitle):
        self.band = band
        self.title = title
        self.subtitle = subtitle

    def set_status(self, text, color=TEXT):
        if self.subtitle is not None:
            self.subtitle.set_text(text)
            self.subtitle.set_style_text_color(lv.color_hex(color), 0)


def header(parent, title, subtitle="", width=320, title_size=22, subtitle_size=14):
    """Title band with optional subtitle; returns a handle with .set_status(text)."""
    band = box(parent, 0, 0, width, HEADER_H, bg=SURFACE)
    if subtitle:
        title_label = label(band, title, S4, S2, size=title_size, color=TEXT)
        subtitle_label = label(band, subtitle, S4, HEADER_H - S5, size=subtitle_size,
                               color=DIM)
    else:
        title_label = label(band, title, S4, 0, size=title_size, color=TEXT,
                            align=lv.ALIGN.LEFT_MID)
        subtitle_label = None
    rule = box(band, 0, HEADER_H - 1, width, 1, bg=LINE)
    rule.set_style_bg_opa(lv.OPA.COVER, 0)
    return _Header(band, title_label, subtitle_label)


def footer(parent, text, width=320):
    """Thin status strip at the bottom: hairline plus one dim line of text."""
    band = box(parent, 0, 480 - FOOTER_H, width, FOOTER_H, bg=SURFACE)
    rule = box(band, 0, 0, width, 1, bg=LINE)
    rule.set_style_bg_opa(lv.OPA.COVER, 0)
    lab = label(band, text, S4, 0, size=12, color=DIM, align=lv.ALIGN.LEFT_MID)
    return lab


def show_scrollbar(obj, active=True):
    mode = getattr(getattr(lv, "SCROLLBAR_MODE", None), "ACTIVE" if active else "OFF", None)
    if mode is not None and hasattr(obj, "set_scrollbar_mode"):
        obj.set_scrollbar_mode(mode)


def tap(obj, callback, extra=8):
    """Make an object a real target: clickable, with a margin beyond its pixels."""
    obj.add_flag(lv.obj.FLAG.CLICKABLE)
    extender = getattr(obj, "set_ext_click_area", None)
    if extender is not None:
        try:
            extender(extra)
        except Exception:  # noqa: BLE001
            pass
    if callback is not None:
        obj.add_event_cb(lambda _e: callback(), lv.EVENT.CLICKED, None)
    return obj


def button(parent, text, x, y, width=140, height=TOUCH_MIN, callback=None,
           kind="primary", radius=R_MD):
    """The only button builder: same anatomy and the same three states everywhere."""
    if kind == "primary":
        fill, fill_pressed, ink = ACCENT, ACCENT_PRESSED, ACCENT_TEXT
    elif kind == "ghost":
        fill, fill_pressed, ink = SURFACE, SURFACE_ALT, TEXT
    else:                                   # "quiet": no fill, accent ink
        fill, fill_pressed, ink = None, SURFACE_ALT, ACCENT

    btn = card(parent, x, y, width, height, bg=fill, radius=radius) if fill is not None \
        else box(parent, x, y, width, height, bg=None, radius=radius)
    if fill is None:
        btn.set_style_border_width(1, 0)
        btn.set_style_border_color(lv.color_hex(LINE), 0)

    if height < TOUCH_MIN:
        raise ValueError("touch target below %d px" % TOUCH_MIN)

    # States on the object itself, so no per-call styling creeps back in.
    btn.set_style_bg_color(lv.color_hex(fill_pressed), _state(MAIN, STATE_PRESSED))
    btn.set_style_bg_opa(lv.OPA.COVER, _state(MAIN, STATE_PRESSED))
    btn.set_style_bg_opa(lv.OPA._50, _state(MAIN, STATE_DISABLED))
    btn.set_style_text_color(lv.color_hex(DIM), _state(MAIN, STATE_DISABLED))

    label(btn, text, 0, 0, size=18, color=ink, align=lv.ALIGN.CENTER)
    tap(btn, callback)
    return btn


def pill(parent, text, x, y, color=ACCENT_SOFT, ink=TEXT, size=12, width=None):
    pad = S3
    w = width if width is not None else (len(text) * 7 + pad * 2)
    height = size + S3
    obj = box(parent, x, y, w, height, bg=color, radius=R_PILL)
    label(obj, text, 0, 0, size=size, color=ink, align=lv.ALIGN.CENTER)
    return obj


def set_enabled(widget, enabled):
    """Real disabled state: the widget stops looking pressable and stops reacting."""
    if enabled:
        remover = getattr(widget, "remove_state", None)
        if remover is not None:
            remover(lv.STATE.DISABLED)
    else:
        widget.add_state(lv.STATE.DISABLED)
        widget.remove_flag(lv.obj.FLAG.CLICKABLE)


def set_checked(widget, checked):
    if checked:
        widget.add_state(lv.STATE.CHECKED)
    else:
        widget.remove_state(lv.STATE.CHECKED)


def spacer(parent, height):
    return box(parent, 0, 0, 1, height)
