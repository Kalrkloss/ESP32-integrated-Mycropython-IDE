# game2048.py -- 2048 for the JC3248W535 (ESP32-S3, 320x480, LVGL 9).
#
# Self-contained LVGL app. Public API used by app_loader / launcher:
#   TITLE / DESCRIPTION      short texts for the launcher (TITEL/BESCHREIBUNG aliases)
#   start(parent=None)       builds the UI, returns a handle with .stop()
#
# Movement is via four arrow buttons (a swipe would need gesture handling the
# binding does not expose comfortably). Each tile shows its value; the colour
# steps up with the value.
#
# Rules kept: only lvgl + stdlib, full cleanup in stop(), touch targets >= 40x40 px.

import random

import lvgl as lv

TITLE = "2048"
DESCRIPTION = "Slide and merge tiles with the arrow buttons. Reach 2048."
TITEL = TITLE
BESCHREIBUNG = DESCRIPTION

N = 4
CELL = 64          # 4 x 4 -> 256 + gaps, touch targets far over 40
GAP = 8
BG = 0x101820
BOARD = 0x1E2833
TEXT = 0xFFFFFF
ACCENT = 0x3A6EA5

TILE_COLORS = {
    2: 0x3A6EA5, 4: 0x2F9E8F, 8: 0x30A0E0, 16: 0xE0A030, 32: 0xE06060,
    64: 0xE04040, 128: 0xC08030, 256: 0xB060C0, 512: 0x9060E0, 1024: 0x40C060,
    2048: 0xE0C030,
}


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


class _Game2048:
    def __init__(self, parent):
        self.parent = parent
        self.grid = [[0] * N for _ in range(N)]
        self.score = 0
        self.done = False
        self.timer = None
        self._build()
        self._spawn()
        self._spawn()
        self._draw()

    def _build(self):
        self.root_ = lv.obj(self.parent)
        self.root_.set_pos(0, 0)
        self.root_.set_size(320, 480)
        self.root_.set_style_bg_color(lv.color_hex(BG), 0)
        self.root_.set_style_border_width(0, 0)
        _zero_pad(self.root_)

        self.score_label = _label(self.root_, "Score: 0", 10, 8, TEXT, 20)
        self.status = _label(self.root_, "", 200, 8, 0x8FD4FF, 16)

        board = _rect(self.root_, 4, 44, 312, 312, BOARD, radius=10)
        board.remove_flag(lv.obj.FLAG.SCROLLABLE)
        self.cells = []
        self.labels = []
        for r in range(N):
            row, rowlab = [], []
            for c in range(N):
                x = GAP + c * (CELL + GAP)
                y = GAP + r * (CELL + GAP)
                cell = _rect(board, x, y, CELL, CELL, BOARD, radius=8)
                lab = _label(cell, "", 0, 0, TEXT, 24)
                lab.center()
                row.append(cell)
                rowlab.append(lab)
            self.cells.append(row)
            self.labels.append(rowlab)

        _button(self.root_, 104, 372, 56, 48, "^", lambda: self._move("up"), ACCENT)
        _button(self.root_, 44, 372, 56, 48, "<", lambda: self._move("left"), ACCENT)
        _button(self.root_, 164, 372, 56, 48, ">", lambda: self._move("right"), ACCENT)
        _button(self.root_, 104, 424, 56, 48, "v", lambda: self._move("down"), ACCENT)
        _button(self.root_, 226, 396, 84, 48, "Reset", self._reset, ACCENT)

    # ------------------------------------------------------------- game
    def _spawn(self):
        free = [(r, c) for r in range(N) for c in range(N) if self.grid[r][c] == 0]
        if not free:
            return
        r, c = random.choice(free)
        self.grid[r][c] = 4 if random.random() < 0.1 else 2

    def _line(self, cells):
        values = [self.grid[r][c] for r, c in cells if self.grid[r][c]]
        merged = []
        i = 0
        while i < len(values):
            if i + 1 < len(values) and values[i] == values[i + 1]:
                merged.append(values[i] * 2)
                self.score += values[i] * 2
                i += 2
            else:
                merged.append(values[i])
                i += 1
        merged += [0] * (N - len(merged))
        return merged

    def _move(self, direction):
        if self.done:
            return
        before = [row[:] for row in self.grid]
        moved = False
        for i in range(N):
            if direction == "left":
                cells = [(i, c) for c in range(N)]
            elif direction == "right":
                cells = [(i, c) for c in range(N - 1, -1, -1)]
            elif direction == "up":
                cells = [(r, i) for r in range(N)]
            else:
                cells = [(r, i) for r in range(N - 1, -1, -1)]
            merged = self._line(cells)
            for (r, c), value in zip(cells, merged):
                self.grid[r][c] = value
        if self.grid != before:
            moved = True
        if moved:
            self._spawn()
            self._draw()
            self._check_state()

    def _draw(self):
        for r in range(N):
            for c in range(N):
                value = self.grid[r][c]
                color = TILE_COLORS.get(value, 0x00C0C0) if value else BOARD
                self.cells[r][c].set_style_bg_color(lv.color_hex(color), 0)
                self.labels[r][c].set_text(str(value) if value else "")
                self.labels[r][c].center()
        self.score_label.set_text("Score: %d" % self.score)

    def _check_state(self):
        for r in range(N):
            for c in range(N):
                if self.grid[r][c] >= 2048:
                    self.status.set_text("YOU WIN")
                    return
        if not self._any_move():
            self.done = True
            self.status.set_text("Game over")

    def _any_move(self):
        for r in range(N):
            for c in range(N):
                if self.grid[r][c] == 0:
                    return True
                if c + 1 < N and self.grid[r][c] == self.grid[r][c + 1]:
                    return True
                if r + 1 < N and self.grid[r][c] == self.grid[r + 1][c]:
                    return True
        return False

    def _reset(self):
        self.grid = [[0] * N for _ in range(N)]
        self.score = 0
        self.done = False
        self.status.set_text("")
        self._spawn()
        self._spawn()
        self._draw()

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


def _button(parent, x, y, w, h, text, cb, bg):
    btn = _rect(parent, x, y, w, h, bg, radius=8)
    btn.add_flag(lv.obj.FLAG.CLICKABLE)
    lab = _label(btn, text, 0, 0, TEXT, 18)
    lab.center()
    btn.add_event_cb(lambda _e, cb=cb: cb(), lv.EVENT.CLICKED, None)
    return btn


def start(parent=None):
    """Build the game on `parent` (default: the active screen). Returns a handle."""
    return _Game2048(parent if parent is not None else lv.screen_active())
