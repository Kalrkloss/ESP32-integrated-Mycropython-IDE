# minesweeper.py -- Minesweeper for the JC3248W535 (ESP32-S3, 320x480, LVGL 9).
#
# Self-contained LVGL app. Public API used by app_loader / launcher:
#   TITLE / DESCRIPTION      short texts for the launcher (TITEL/BESCHREIBUNG aliases)
#   start(parent=None)       builds the UI, returns a handle with .stop()
#
# Rules kept: only lvgl + stdlib, our own lv.timer_create where needed, full
# cleanup in stop(), touch targets >= 40x40 px, LVGL only from the main thread.

import random

import lvgl as lv

TITLE = "Minesweeper"
DESCRIPTION = "Find every safe tile. Tap to dig, toggle a mode to flag mines."
TITEL = TITLE
BESCHREIBUNG = DESCRIPTION

N = 8              # 8 x 8 board -> 320 x 320 pixels, 40 px touch targets
CELL = 40
MINES = 10

BG = 0x101820
HIDDEN = 0x3A4250
OPEN = 0x202830
FLAG = 0xE0A030
MINE = 0xE04040
TEXT = 0xFFFFFF
ACCENT = 0x3A6EA5

NUM_COLORS = {1: 0x60A0FF, 2: 0x40C060, 3: 0xE06060, 4: 0xA060E0,
              5: 0xE0A030, 6: 0x40D0D0, 7: 0xD0D0D0, 8: 0x808080}


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


def _button(parent, x, y, w, h, text, cb, bg, size=16):
    btn = _rect(parent, x, y, w, h, bg, radius=8)
    btn.add_flag(lv.obj.FLAG.CLICKABLE)
    lab = _label(btn, text, 0, 0, TEXT, size)
    lab.center()
    btn.add_event_cb(lambda _e, cb=cb: cb(), lv.EVENT.CLICKED, None)
    return btn


class _Minesweeper:
    def __init__(self, parent):
        self.parent = parent
        self.timer = None
        self.flag_mode = False
        self.state = "run"           # run | lost | won
        self.mines = set()
        self.open_cells = set()
        self.flags = set()
        self._first = True
        self._build()

    # ------------------------------------------------------------- UI
    def _build(self):
        self.root_ = lv.obj(self.parent)
        self.root_.set_pos(0, 0)
        self.root_.set_size(320, 480)
        self.root_.set_style_bg_color(lv.color_hex(BG), 0)
        self.root_.set_style_border_width(0, 0)
        _zero_pad(self.root_)

        self.info = _label(self.root_, "Mines: %d" % MINES, 10, 8, TEXT, 18)
        self.status = _label(self.root_, "", 200, 8, FLAG, 16)

        field = _rect(self.root_, 0, 40, N * CELL, N * CELL, OPEN)
        field.remove_flag(lv.obj.FLAG.SCROLLABLE)
        self.cells = []
        self.labels = []
        for r in range(N):
            row, rowlab = [], []
            for c in range(N):
                cell = _rect(field, c * CELL, r * CELL, CELL - 2, CELL - 2, HIDDEN)
                cell.add_flag(lv.obj.FLAG.CLICKABLE)
                lab = _label(cell, "", 0, 0, TEXT, 18)
                lab.center()
                cell.add_event_cb(lambda _e, r=r, c=c: self._tap(r, c), lv.EVENT.CLICKED, None)
                row.append(cell)
                rowlab.append(lab)
            self.cells.append(row)
            self.labels.append(rowlab)

        self.mode_btn = _button(self.root_, 8, 368, 150, 50, "Mode: Dig",
                                self._toggle_mode, ACCENT)
        _button(self.root_, 166, 368, 146, 50, "New game", self._reset, ACCENT)
        self.hint = _label(self.root_, "Tap a tile to reveal it", 10, 428, TEXT, 14)

    def _toggle_mode(self):
        self.flag_mode = not self.flag_mode
        # Rebuild the label text; the button keeps its size (touch target stays).
        self.mode_btn.get_child(0).set_text("Mode: Flag" if self.flag_mode else "Mode: Dig")

    # ------------------------------------------------------------- game
    def _place_mines(self, safe_r, safe_c):
        forbidden = {(safe_r, safe_c)}
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                forbidden.add((safe_r + dr, safe_c + dc))
        pool = [(r, c) for r in range(N) for c in range(N) if (r, c) not in forbidden]
        self.mines = set(random.sample(pool, min(MINES, len(pool))))

    def _neighbors(self, r, c):
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if 0 <= nr < N and 0 <= nc < N:
                    yield nr, nc

    def _count(self, r, c):
        return sum(1 for nr, nc in self._neighbors(r, c) if (nr, nc) in self.mines)

    def _tap(self, r, c):
        if self.state != "run" or (r, c) in self.open_cells:
            return
        if self.flag_mode:
            if (r, c) in self.flags:
                self.flags.discard(r, c)
            else:
                self.flags.add((r, c))
            self._paint(r, c)
            return
        if self._first:
            self._place_mines(r, c)
            self._first = False
        if (r, c) in self.mines:
            self._lose(r, c)
            return
        self._flood(r, c)
        self._repaint()
        self._check_win()

    def _flood(self, r, c):
        stack = [(r, c)]
        while stack:
            cr, cc = stack.pop()
            if (cr, cc) in self.open_cells or (cr, cc) in self.mines:
                continue
            self.open_cells.add((cr, cc))
            self.flags.discard((cr, cc))
            if self._count(cr, cc) == 0:
                for nr, nc in self._neighbors(cr, cc):
                    if (nr, nc) not in self.open_cells:
                        stack.append((nr, nc))

    def _paint(self, r, c):
        lab = self.labels[r][c]
        cell = self.cells[r][c]
        if (r, c) in self.flags:
            cell.set_style_bg_color(lv.color_hex(HIDDEN), 0)
            lab.set_text("F")
            lab.set_style_text_color(lv.color_hex(FLAG), 0)
        elif (r, c) in self.open_cells:
            cell.set_style_bg_color(lv.color_hex(OPEN), 0)
            n = self._count(r, c)
            lab.set_text("" if n == 0 else str(n))
            lab.set_style_text_color(lv.color_hex(NUM_COLORS.get(n, TEXT)), 0)
        else:
            cell.set_style_bg_color(lv.color_hex(HIDDEN), 0)
            lab.set_text("")
        lab.center()

    def _repaint(self):
        for r in range(N):
            for c in range(N):
                self._paint(r, c)

    def _lose(self, r, c):
        self.state = "lost"
        for mr, mc in self.mines:
            self.labels[mr][mc].set_text("*")
            self.labels[mr][mc].set_style_text_color(lv.color_hex(TEXT), 0)
            self.labels[mr][mc].center()
        self.cells[r][c].set_style_bg_color(lv.color_hex(MINE), 0)
        self.status.set_text("BOOM!")

    def _check_win(self):
        if len(self.open_cells) == N * N - len(self.mines):
            self.state = "won"
            self.status.set_text("CLEAR!")

    def _reset(self):
        self.state = "run"
        self.flag_mode = False
        self._first = True
        self.mines = set()
        self.open_cells = set()
        self.flags = set()
        self.status.set_text("")
        self.mode_btn.get_child(0).set_text("Mode: Dig")
        for r in range(N):
            for c in range(N):
                self.cells[r][c].set_style_bg_color(lv.color_hex(HIDDEN), 0)
                self.labels[r][c].set_text("")
                self.labels[r][c].center()

    # ------------------------------------------------------------- lifecycle
    def stop(self):
        if self.timer is not None:
            try:
                self.timer.delete()
            except Exception:  # noqa: BLE001
                pass
            self.timer = None
        try:
            self.root_.delete()
        except Exception:  # noqa: BLE001
            pass


def start(parent=None):
    """Build the game on `parent` (default: the active screen). Returns a handle."""
    return _Minesweeper(parent if parent is not None else lv.screen_active())
