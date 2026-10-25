# clock.py -- Clock, stopwatch and alarm for the JC3248W535 (ESP32-S3, 320x480, LVGL 9).
#
# Self-contained LVGL app. Public API used by app_loader / launcher:
#   TITLE / DESCRIPTION      short texts for the launcher (TITEL/BESCHREIBUNG aliases)
#   start(parent=None)       builds the UI, returns a handle with .stop()
#
# The alarm has no buzzer on this board: it flashes the backlight and shows a
# message on the screen instead. The backlight is reached through display_config
# (an allowed import for apps); if it is missing the alarm only flashes the panel.
#
# Rules kept: only lvgl + stdlib, our own lv.timer_create per animated part, full
# cleanup in stop(), touch targets >= 40x40 px, LVGL only from the main thread.

import time

import lvgl as lv

TITLE = "Clock"
DESCRIPTION = "Live clock, stopwatch and an alarm that flashes the screen."
TITEL = TITLE
BESCHREIBUNG = DESCRIPTION

BG = 0x101820
CARD = 0x18242E
TEXT = 0xFFFFFF
ACCENT = 0x3A6EA5
GOOD = 0x30D060
ALERT = 0xE04040


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


class _Clock:
    def __init__(self, parent):
        self.parent = parent
        self.mode = "clock"           # clock | stopwatch | alarm
        self.tick_timer = None
        self.flash_timer = None
        self.flash_on = False
        # stopwatch state
        self.sw_running = False
        self.sw_base = 0
        self.sw_elapsed = 0
        # alarm state
        self.alarm_h = 7
        self.alarm_m = 30
        self.alarm_set = False
        self.alarm_ringing = False
        self.display = self._find_display()
        self._build()
        self.tick_timer = lv.timer_create(self._tick, 250, None)

    def _find_display(self):
        try:
            import display_config
            return getattr(display_config, "LAST_DISPLAY", None)
        except Exception:  # noqa: BLE001
            return None

    # ------------------------------------------------------------- UI
    def _build(self):
        self.root_ = lv.obj(self.parent)
        self.root_.set_pos(0, 0)
        self.root_.set_size(320, 480)
        self.root_.set_style_bg_color(lv.color_hex(BG), 0)
        self.root_.set_style_border_width(0, 0)
        _zero_pad(self.root_)

        self._tab(0, "Clock", "clock")
        self._tab(108, "Stopwatch", "stopwatch")
        self._tab(216, "Alarm", "alarm")

        self.page = _rect(self.root_, 0, 60, 320, 420, BG)
        self.big = _label(self.page, "--:--:--", 0, 40, TEXT, 40)

        self.pages = {}
        self._build_clock_page()
        self._build_stopwatch_page()
        self._build_alarm_page()
        self._show("clock")

    def _tab(self, x, text, mode):
        btn = _rect(self.root_, x, 6, 100, 48, ACCENT, radius=8)
        btn.add_flag(lv.obj.FLAG.CLICKABLE)
        lab = _label(btn, text, 0, 0, TEXT, 14)
        lab.center()
        btn.add_event_cb(lambda _e, m=mode: self._show(m), lv.EVENT.CLICKED, None)

    def _build_clock_page(self):
        page = lv.obj(self.page)
        page.set_pos(0, 0)
        page.set_size(320, 420)
        page.set_style_bg_color(lv.color_hex(BG), 0)
        page.set_style_border_width(0, 0)
        _zero_pad(page)
        _label(page, "Time", 120, 4, 0x8FD4FF, 16)
        page.add_flag(lv.obj.FLAG.HIDDEN)
        self.pages["clock"] = page

    def _build_stopwatch_page(self):
        page = lv.obj(self.page)
        page.set_pos(0, 0)
        page.set_size(320, 420)
        page.set_style_bg_color(lv.color_hex(BG), 0)
        page.set_style_border_width(0, 0)
        _zero_pad(page)
        self.sw_label = _label(page, "00:00.0", 40, 40, TEXT, 40)
        _button(page, 20, 180, 130, 60, "Start", self._sw_start, GOOD)
        _button(page, 170, 180, 130, 60, "Stop", self._sw_stop, ACCENT)
        _button(page, 95, 260, 130, 60, "Reset", self._sw_reset, ACCENT)
        page.add_flag(lv.obj.FLAG.HIDDEN)
        self.pages["stopwatch"] = page

    def _build_alarm_page(self):
        page = lv.obj(self.page)
        page.set_pos(0, 0)
        page.set_size(320, 420)
        page.set_style_bg_color(lv.color_hex(BG), 0)
        page.set_style_border_width(0, 0)
        _zero_pad(page)
        self.alarm_label = _label(page, "07:30", 70, 30, TEXT, 48)
        self.alarm_state = _label(page, "off", 120, 100, 0x8FD4FF, 18)
        _button(page, 20, 150, 80, 60, "-h", lambda: self._alarm_adjust(1, -1), ACCENT)
        _button(page, 110, 150, 80, 60, "+h", lambda: self._alarm_adjust(1, 1), ACCENT)
        _button(page, 200, 150, 100, 60, "toggle", self._alarm_toggle, ACCENT)
        _button(page, 20, 220, 80, 60, "-m", lambda: self._alarm_adjust(0, -5), ACCENT)
        _button(page, 110, 220, 80, 60, "+m", lambda: self._alarm_adjust(0, 5), ACCENT)
        self.ringing_label = _label(page, "", 30, 320, ALERT, 20)
        _button(page, 95, 360, 130, 56, "Silence", self._alarm_silence, ALERT)
        page.add_flag(lv.obj.FLAG.HIDDEN)
        self.pages["alarm"] = page

    def _show(self, mode):
        self.mode = mode
        for name, page in self.pages.items():
            if name == mode:
                page.remove_flag(lv.obj.FLAG.HIDDEN)
            else:
                page.add_flag(lv.obj.FLAG.HIDDEN)
        self.big.set_text("")

    # ------------------------------------------------------------- tick
    def _tick(self, _timer=None):
        if self.mode == "clock":
            t = time.localtime()
            text = "%02d:%02d:%02d" % (t[3], t[4], t[5])
            self.big.set_text(text)
        elif self.mode == "stopwatch":
            self._refresh_stopwatch()
        else:
            self._check_alarm()
        return None

    def _refresh_stopwatch(self):
        if self.sw_running:
            elapsed = self.sw_base + time.ticks_diff(time.ticks_ms(), self.sw_start)
        else:
            elapsed = self.sw_elapsed
        seconds = elapsed // 1000
        tenths = (elapsed % 1000) // 100
        self.sw_label.set_text("%02d:%02d.%d" % (seconds // 60, seconds % 60, tenths))

    def _sw_start(self):
        if not self.sw_running:
            self.sw_running = True
            self.sw_start = time.ticks_ms()

    def _sw_stop(self):
        if self.sw_running:
            self.sw_elapsed = self.sw_base + time.ticks_diff(time.ticks_ms(), self.sw_start)
            self.sw_base = self.sw_elapsed
            self.sw_running = False

    def _sw_reset(self):
        self.sw_running = False
        self.sw_base = 0
        self.sw_elapsed = 0
        self.sw_label.set_text("00:00.0")

    def _alarm_adjust(self, which, delta):
        if which == 1:
            self.alarm_h = (self.alarm_h + delta) % 24
        else:
            self.alarm_m = (self.alarm_m + delta) % 60
        self._refresh_alarm_label()

    def _refresh_alarm_label(self):
        self.alarm_label.set_text("%02d:%02d" % (self.alarm_h, self.alarm_m))
        self.alarm_state.set_text("on" if self.alarm_set else "off")

    def _alarm_toggle(self):
        self.alarm_set = not self.alarm_set
        self._refresh_alarm_label()

    def _check_alarm(self):
        if not self.alarm_set or self.alarm_ringing:
            return
        t = time.localtime()
        if t[3] == self.alarm_h and t[4] == self.alarm_m:
            self._alarm_ring()

    def _alarm_ring(self):
        self.alarm_ringing = True
        self.ringing_label.set_text("ALARM! %02d:%02d" % (self.alarm_h, self.alarm_m))
        self.flash_timer = lv.timer_create(self._flash, 300, None)

    def _flash(self, _timer=None):
        if not self.alarm_ringing:
            return None
        self.flash_on = not self.flash_on
        if self.display is not None:
            try:
                self.display.set_backlight(100 if self.flash_on else 0)
            except Exception:  # noqa: BLE001
                pass
        color = ALERT if self.flash_on else BG
        try:
            self.root_.set_style_bg_color(lv.color_hex(color), 0)
        except Exception:  # noqa: BLE001
            pass
        return None

    def _alarm_silence(self):
        self.alarm_ringing = False
        if self.flash_timer is not None:
            try:
                self.flash_timer.delete()
            except Exception:  # noqa: BLE001
                pass
            self.flash_timer = None
        if self.display is not None:
            try:
                self.display.set_backlight(70)
            except Exception:  # noqa: BLE001
                pass
        self.root_.set_style_bg_color(lv.color_hex(BG), 0)
        self.ringing_label.set_text("")

    # ------------------------------------------------------------- lifecycle
    def stop(self):
        for timer in ("tick_timer", "flash_timer"):
            t = getattr(self, timer, None)
            if t is not None:
                try:
                    t.delete()
                except Exception:  # noqa: BLE001
                    pass
                setattr(self, timer, None)
        if self.display is not None:
            try:
                self.display.set_backlight(70)
            except Exception:  # noqa: BLE001
                pass
        try:
            self.root_.delete()
        except Exception:  # noqa: BLE001
            pass


def _button(parent, x, y, w, h, text, cb, bg, size=18):
    btn = _rect(parent, x, y, w, h, bg, radius=8)
    btn.add_flag(lv.obj.FLAG.CLICKABLE)
    lab = _label(btn, text, 0, 0, TEXT, size)
    lab.center()
    btn.add_event_cb(lambda _e, cb=cb: cb(), lv.EVENT.CLICKED, None)
    return btn


def start(parent=None):
    """Build the app on `parent` (default: the active screen). Returns a handle."""
    return _Clock(parent if parent is not None else lv.screen_active())
