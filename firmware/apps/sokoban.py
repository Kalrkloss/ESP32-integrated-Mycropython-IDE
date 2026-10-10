# sokoban.py -- Sokoban for the JC3248W535 (ESP32-S3, 320x480, LVGL 9).
#
# Self-contained LVGL app. Public API used by app_loader / launcher:
#   TITLE / DESCRIPTION      short texts for the launcher (TITEL/BESCHREIBUNG aliases)
#   start(parent=None)       builds the UI, returns a handle with .stop()
#
# Rules kept: only lvgl + stdlib, our own lv.timer_create where needed, full
# cleanup in stop(), touch targets >= 40x40 px, LVGL only from the main thread.

import lvgl as lv

TITLE = "Sokoban"
DESCRIPTION = "Push every box onto a goal. Arrows move, undo and reset help."
TITEL = TITLE
BESCHREIBUNG = DESCRIPTION

CELL = 40          # 8 x 8 tiles -> 320 x 320 pixels, 40 px touch targets
N = 8

BG = 0x101820
FLOOR = 0x202830
WALL = 0x5A4632
GOAL = 0x8FD4FF
BOX = 0xC08030
BOX_OK = 0x40C060
PLAYER = 0x30A0E0
TEXT = 0xFFFFFF
ACCENT = 0x3A6EA5

# Level maps: '#' wall, ' ' floor, '.' goal, '$' box, '*' box on goal,
# '@' player, '+' player on goal. Rows are padded to 8 wide / tall.
LEVELS = [
    [
        "########",
        "#      #",
        "# $  . #",
        "# @  . #",
        "#      #",
        "#      #",
        "#      #",
        "########",
    ],
    [
        "########",
        "#  #   #",
        "# $#.  #",
        "# @    #",
        "#  $ . #",
        "#      #",
        "#      #",
        "########",
    ],
]


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


def _button(parent, x, y, w, h, text, cb, bg, size=18):
    btn = _rect(parent, x, y, w, h, bg, radius=8)
    btn.add_flag(lv.obj.FLAG.CLICKABLE)
    lab = _label(btn, text, 0, 0, TEXT, size)
    lab.center()
    btn.add_event_cb(lambda _e, cb=cb: cb(), lv.EVENT.CLICKED, None)
    return btn


class _Sokoban:
    def __init__(self, parent):
        self.parent = parent
        self.timer = None
        self.level_index = 0
        self.history = []
        self._build()
        self._load_level(0)

    # ------------------------------------------------------------- UI
    def _build(self):
        self.root_ = lv.obj(self.parent)
        self.root_.set_pos(0, 0)
        self.root_.set_size(320, 480)
        self.root_.set_style_bg_color(lv.color_hex(BG), 0)
        self.root_.set_style_border_width(0, 0)
        _zero_pad(self.root_)

        self.info = _label(self.root_, "Level 1", 10, 8, TEXT, 18)
        self.status = _label(self.root_, "", 180, 8, BOX_OK, 16)

        field = _rect(self.root_, 0, 40, N * CELL, N * CELL, FLOOR)
        field.remove_flag(lv.obj.FLAG.SCROLLABLE)
        self.cells = []
        for r in range(N):
            row = []
            for c in range(N):
                row.append(_rect(field, c * CELL, r * CELL, CELL - 2, CELL - 2, FLOOR))
            self.cells.append(row)

        # Arrow pad (cross) + undo/reset, all >= 40x40.
        _button(self.root_, 94, 366, 56, 48, "^", lambda: self._move(-1, 0), ACCENT)
        _button(self.root_, 34, 366, 56, 48, "<", lambda: self._move(0, -1), ACCENT)
        _button(self.root_, 154, 366, 56, 48, ">", lambda: self._move(0, 1), ACCENT)
        _button(self.root_, 94, 418, 56, 48, "v", lambda: self._move(1, 0), ACCENT)
        _button(self.root_, 220, 366, 92, 48, "Undo", self._undo, ACCENT)
        _button(self.root_, 220, 418, 92, 48, "Reset", self._reset, ACCENT)

        self.hint = _label(self.root_, "Make every box green", 10, 466, TEXT, 12)

    # ------------------------------------------------------------- game
    def _load_level(self, index):
        self.level_index = index % len(LEVELS)
        raw = LEVELS[self.level_index]
        self.grid = []      # static: '#' or ' ' or '.'
        self.boxes = set()
        self.goals = set()
        self.player = (0, 0)
        for r in range(N):
            row = []
            text = raw[r] if r < len(raw) else " " * N
            for c in range(N):
                ch = text[c] if c < len(text) else " "
                if ch == "#":
                    row.append("#")
                elif ch == ".":
                    row.append(".")
                    self.goals.add((r, c))
                elif ch == "$":
                    row.append(" ")
                    self.boxes.add((r, c))
                elif ch == "*":
                    row.append(".")
                    self.goals.add((r, c))
                    self.boxes.add((r, c))
                elif ch == "@":
                    row.append(" ")
                    self.player = (r, c)
                elif ch == "+":
                    row.append(".")
                    self.goals.add((r, c))
                    self.player = (r, c)
                else:
                    row.append(" ")
            self.grid.append(row)
        self.history = []
        self.status.set_text("")
        self.info.set_text("Level %d" % (self.level_index + 1))
        self._draw()

    def _draw(self):
        for r in range(N):
            for c in range(N):
                if self.grid[r][c] == "#":
                    color = WALL
                elif (r, c) in self.boxes:
                    color = BOX_OK if (r, c) in self.goals else BOX
                elif (r, c) == self.player:
                    color = PLAYER
                elif (r, c) in self.goals:
                    color = GOAL
                else:
                    color = FLOOR
                self.cells[r][c].set_style_bg_color(lv.color_hex(color), 0)

    def _move(self, dr, dc):
        pr, pc = self.player
        tr, tc = pr + dr, pc + dc
        if self.grid[tr][tc] == "#":
            return
        self.history.append((tuple(self.boxes), self.player))
        if (tr, tc) in self.boxes:
            br, bc = tr + dr, tc + dc
            if self.grid[br][bc] == "#" or (br, bc) in self.boxes:
                self.history.pop()
                return
            self.boxes.discard((tr, tc))
            self.boxes.add((br, bc))
        self.player = (tr, tc)
        self._draw()
        self._check_win()

    def _undo(self):
        if self.history:
            self.boxes, self.player = self.history.pop()
            self.boxes = set(self.boxes)
            self._draw()
            self.status.set_text("")

    def _reset(self):
        self._load_level(self.level_index)

    def _check_win(self):
        if self.boxes and self.boxes.issubset(self.goals):
            self.status.set_text("SOLVED!")
            self.info.set_text("Level %d done" % (self.level_index + 1))

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
    return _Sokoban(parent if parent is not None else lv.screen_active())
