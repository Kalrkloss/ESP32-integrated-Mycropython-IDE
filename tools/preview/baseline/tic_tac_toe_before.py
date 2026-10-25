# tic_tac_toe.py -- Tic-tac-toe for the JC3248W535 (ESP32-S3, 320x480, LVGL 9).
#
# Self-contained LVGL app. Public API used by app_loader / launcher:
#   TITLE / DESCRIPTION      short texts for the launcher (TITEL/BESCHREIBUNG aliases)
#   start(parent=None)       builds the UI, returns a handle with .stop()
#
# Single player against a small unbeatable-ish computer: it wins if it can, blocks
# if it must, otherwise takes the centre or a random corner.
#
# Rules kept: only lvgl + stdlib, full cleanup in stop(), touch targets >= 40x40 px.

import random

import lvgl as lv

TITLE = "Tic-Tac-Toe"
DESCRIPTION = "You are X. Beat the computer, or take a draw."
TITEL = TITLE
BESCHREIBUNG = DESCRIPTION

CELL = 90          # 3 x 3 -> 270 x 270 pixels, touch targets far over 40
BG = 0x101820
GRID = 0x2C3646
X = 0x30A0E0
O = 0xE0A030
TEXT = 0xFFFFFF
ACCENT = 0x3A6EA5

LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8),
         (0, 3, 6), (1, 4, 7), (2, 5, 8),
         (0, 4, 8), (2, 4, 6)]


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


class _TicTacToe:
    def __init__(self, parent):
        self.parent = parent
        self.board = [""] * 9
        self.done = False
        self._build()

    def _build(self):
        self.root_ = lv.obj(self.parent)
        self.root_.set_pos(0, 0)
        self.root_.set_size(320, 480)
        self.root_.set_style_bg_color(lv.color_hex(BG), 0)
        self.root_.set_style_border_width(0, 0)
        _zero_pad(self.root_)

        self.status = _label(self.root_, "Your turn (X)", 10, 8, TEXT, 18)

        grid = _rect(self.root_, 20, 60, 3 * CELL, 3 * CELL, GRID)
        grid.remove_flag(lv.obj.FLAG.SCROLLABLE)
        self.cells = []
        for i in range(9):
            r, c = divmod(i, 3)
            cell = _rect(grid, c * CELL, r * CELL, CELL - 2, CELL - 2, BG)
            cell.add_flag(lv.obj.FLAG.CLICKABLE)
            lab = _label(cell, "", 0, 0, TEXT, 48)
            lab.center()
            cell.add_event_cb(lambda _e, i=i: self._tap(i), lv.EVENT.CLICKED, None)
            self.cells.append((cell, lab))

        self.new_btn = _rect(self.root_, 95, 360, 130, 56, ACCENT, radius=8)
        self.new_btn.add_flag(lv.obj.FLAG.CLICKABLE)
        nlab = _label(self.new_btn, "New game", 0, 0, TEXT, 18)
        nlab.center()
        self.new_btn.add_event_cb(lambda _e: self._reset(), lv.EVENT.CLICKED, None)

    def _tap(self, i):
        if self.done or self.board[i]:
            return
        self._place(i, "X")
        if self._finished():
            return
        self._ai_move()
        self._finished()

    def _place(self, i, mark):
        self.board[i] = mark
        cell, lab = self.cells[i]
        lab.set_text(mark)
        lab.set_style_text_color(lv.color_hex(X if mark == "X" else O), 0)
        lab.center()

    def _winner(self):
        for a, b, c in LINES:
            if self.board[a] and self.board[a] == self.board[b] == self.board[c]:
                return self.board[a]
        if all(self.board):
            return "draw"
        return None

    def _finished(self):
        result = self._winner()
        if result is None:
            return False
        self.done = True
        if result == "draw":
            self.status.set_text("Draw")
        elif result == "X":
            self.status.set_text("You win!")
        else:
            self.status.set_text("Computer wins")
        return True

    def _free(self):
        return [i for i in range(9) if not self.board[i]]

    def _ai_move(self):
        # Win if possible.
        for mark in ("O", "X"):
            for i in self._free():
                self.board[i] = mark
                won = self._winner() == mark
                self.board[i] = ""
                if won:
                    self._place(i, "O")
                    return
        # Otherwise centre, then a random free cell.
        if not self.board[4]:
            self._place(4, "O")
            return
        free = self._free()
        if free:
            self._place(random.choice(free), "O")

    def _reset(self):
        self.board = [""] * 9
        self.done = False
        self.status.set_text("Your turn (X)")
        for _cell, lab in self.cells:
            lab.set_text("")
            lab.center()

    # ------------------------------------------------------------- lifecycle
    def stop(self):
        try:
            self.root_.delete()
        except Exception:  # noqa: BLE001
            pass


def start(parent=None):
    """Build the game on `parent` (default: the active screen). Returns a handle."""
    return _TicTacToe(parent if parent is not None else lv.screen_active())
