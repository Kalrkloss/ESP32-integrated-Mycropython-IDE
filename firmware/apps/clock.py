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
#
# Look and feel comes from _ui (tokens + widgets); this file only composes.

import time

import lvgl as lv

import _ui as ui

TITLE = "Clock"
DESCRIPTION = "Live clock, stopwatch and an alarm that flashes the screen."
TITEL = TITLE
BESCHREIBUNG = DESCRIPTION

# Frame: a tab row under the header, one page per mode below it, footer strip.
TABS = (("clock", "Clock"), ("stopwatch", "Stopwatch"), ("alarm", "Alarm"))
TAB_W = 96
TAB_GAP = ui.S1
TAB_Y = ui.HEADER_H + ui.S2                     # 64
PAGE_TOP = TAB_Y + ui.TOUCH_MIN + ui.S3         # 124
PAGE_H = 480 - ui.FOOTER_H - PAGE_TOP           # 332
READOUT_H = 116                                 # stopwatch/alarm hero card
RINGING_H = 28                                  # height of the alarm message line
CONTENT_W = 320 - 2 * ui.S4                     # 288


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
        self._tick()            # first paint now, not 250 ms of "--:--:--"

    def _find_display(self):
        try:
            import display_config
            return getattr(display_config, "LAST_DISPLAY", None)
        except Exception:  # noqa: BLE001
            return None

    # ------------------------------------------------------------- UI
    def _build(self):
        self.root_ = ui.screen(self.parent)
        self.header = ui.header(self.root_, TITLE, "Time, stopwatch, alarm")

        # Mode switch. The active segment is filled in _show(); pages do the hiding.
        self.tabs = {}
        for index, (mode, text) in enumerate(TABS):
            x = ui.S3 + index * (TAB_W + TAB_GAP)
            self.tabs[mode] = ui.button(self.root_, text, x, TAB_Y, width=TAB_W, size=16,
                                        height=ui.TOUCH_MIN, kind="ghost",
                                        callback=lambda m=mode: self._show(m))

        self.page = ui.box(self.root_, 0, PAGE_TOP, 320, PAGE_H, bg=ui.BG)

        self.pages = {}
        self._build_clock_page()
        self._build_stopwatch_page()
        self._build_alarm_page()
        ui.footer(self.root_, "tap a tab to switch")
        self._show("clock")

    def _new_page(self):
        page = ui.box(self.page, 0, 0, 320, PAGE_H, bg=ui.BG)
        page.add_flag(lv.obj.FLAG.HIDDEN)
        return page

    def _build_clock_page(self):
        page = self._new_page()
        card = ui.card(page, ui.S4, 0, CONTENT_W, 232)
        self.big = ui.label(card, "--:--:--", 0, -ui.S3, size=40, color=ui.TEXT,
                            align=lv.ALIGN.CENTER)
        ui.label(card, "24-hour local time", 0, -ui.S5, size=14, color=ui.DIM,
                 align=lv.ALIGN.BOTTOM_MID)
        self.pages["clock"] = page

    def _build_stopwatch_page(self):
        page = self._new_page()
        card = ui.card(page, ui.S4, 0, CONTENT_W, READOUT_H)
        self.sw_label = ui.label(card, "00:00.0", 0, 0, size=40, color=ui.TEXT,
                                 align=lv.ALIGN.CENTER)
        ui.button(page, "Start", ui.S4, READOUT_H + ui.S4, width=140,
                  callback=self._sw_start, kind="primary")
        ui.button(page, "Stop", ui.S4 + 140 + ui.S2, READOUT_H + ui.S4, width=140,
                  callback=self._sw_stop, kind="ghost")
        ui.button(page, "Reset", ui.S4, READOUT_H + ui.S4 + ui.TOUCH_MIN + ui.S2,
                  width=CONTENT_W, callback=self._sw_reset, kind="quiet")
        self.pages["stopwatch"] = page

    def _build_alarm_page(self):
        page = self._new_page()
        card = ui.card(page, ui.S4, 0, CONTENT_W, READOUT_H)
        self.alarm_label = ui.label(card, "07:30", 0, -ui.S3, size=40, color=ui.TEXT,
                                    align=lv.ALIGN.CENTER)
        self.alarm_state = ui.label(card, "off", 0, -ui.S2, size=16, color=ui.DIM,
                                    align=lv.ALIGN.BOTTOM_MID)

        row_one = READOUT_H + ui.S4
        row_two = row_one + ui.TOUCH_MIN + ui.S2
        ui.button(page, "-h", ui.S4, row_one, width=88,
                  callback=lambda: self._alarm_adjust(1, -1), kind="ghost")
        ui.button(page, "+h", ui.S4 + 88 + ui.S2, row_one, width=88,
                  callback=lambda: self._alarm_adjust(1, 1), kind="ghost")
        ui.button(page, "toggle", CONTENT_W + ui.S4 - 96, row_one, width=96,
                  callback=self._alarm_toggle, kind="primary")
        ui.button(page, "-m", ui.S4, row_two, width=140,
                  callback=lambda: self._alarm_adjust(0, -5), kind="ghost")
        ui.button(page, "+m", ui.S4 + 140 + ui.S2, row_two, width=140,
                  callback=lambda: self._alarm_adjust(0, 5), kind="ghost")

        ring_y = row_two + ui.TOUCH_MIN + ui.S2
        self.ringing_label = ui.label(page, "", ui.S4, ring_y, size=20, color=ui.DANGER)
        ui.button(page, "Silence", ui.S4, ring_y + RINGING_H + ui.S2,
                  width=CONTENT_W, callback=self._alarm_silence, kind="primary")
        self.pages["alarm"] = page

    def _show(self, mode):
        self.mode = mode
        for name, page in self.pages.items():
            if name == mode:
                page.remove_flag(lv.obj.FLAG.HIDDEN)
            else:
                page.add_flag(lv.obj.FLAG.HIDDEN)
        for name, tab in self.tabs.items():
            tab.set_style_bg_color(
                lv.color_hex(ui.ACCENT if name == mode else ui.SURFACE), 0)

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
        self.alarm_state.set_style_text_color(
            lv.color_hex(ui.OK if self.alarm_set else ui.DIM), 0)

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
        color = ui.DANGER if self.flash_on else ui.BG
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
        self.root_.set_style_bg_color(lv.color_hex(ui.BG), 0)
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
            # root_ is the display's active screen -- clean it, never delete it.
            self.root_.clean()
        except Exception:  # noqa: BLE001
            pass


def start(parent=None):
    """Build the app on `parent` (default: the active screen). Returns a handle."""
    return _Clock(parent if parent is not None else lv.screen_active())
