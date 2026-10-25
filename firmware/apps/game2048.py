# game2048.py -- 2048 for the JC3248W535 (ESP32-S3, 320x480, LVGL 9).
#
# Self-contained LVGL app. Public API used by app_loader / launcher:
#   TITLE / DESCRIPTION      short texts for the launcher (TITEL/BESCHREIBUNG aliases)
#   start(parent=None)       builds the UI, returns a handle with .stop()
#
# Movement is via four arrow buttons (a swipe would need gesture handling the
# binding does not expose comfortably). Each tile shows its value; the surface
# steps from the raised card colour to the accent as the value grows.
#
# Rules kept: only lvgl + stdlib, full cleanup in stop().
#
# Look and feel comes from _ui (tokens + widgets); this file only composes. The
# tile ramp is derived from tokens, so no palette of hex literals lives here.

import random

import lvgl as lv

import _ui as ui

TITLE = "2048"
DESCRIPTION = "Slide and merge tiles with the arrow buttons. Reach 2048."
TITEL = TITLE
BESCHREIBUNG = DESCRIPTION

N = 4
BOARD = 288
BOARD_X = (320 - BOARD) // 2
BOARD_Y = ui.HEADER_H + ui.S2
PAD = ui.S2                     # breathing room inside the board frame
GAP = ui.S2                     # gap between two slots, from the S scale
CELL = (BOARD - 2 * PAD - (N - 1) * GAP) // N

ARROW_W = 56
ARROW_GAP = ui.S2
SIDE_W = 96
SIDE_X = 320 - ui.S4 - SIDE_W
PAD_Y = BOARD_Y + BOARD + ui.S3
PAD_H = 2 * ui.TOUCH_MIN + ui.S2
PAD_ROW2 = PAD_Y + ui.TOUCH_MIN + ui.S2


def _mix(low, high, percent):
    """Blend two token colours: percent 0 -> low, 100 -> high. Integer channel math."""
    def channel(shift):
        a = (low >> shift) & 0xFF
        b = (high >> shift) & 0xFF
        return (a * (100 - percent) + b * percent) // 100
    return (channel(16) << 16) | (channel(8) << 8) | channel(0)


# Exponent 2 -> step 0, exponent 2048 -> last step. Every shade is computed from
# SURFACE_ALT and ACCENT, so the whole ramp moves when the tokens move.
TILE_STEPS = (0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100)
TILE_SHADES = tuple(_mix(ui.SURFACE_ALT, ui.ACCENT, step) for step in TILE_STEPS)


def _tile_shade(value):
    """Step along the ramp by powers of two; capped at the last shade."""
    index = 0
    step = 2
    while step < value and index + 1 < len(TILE_SHADES):
        step *= 2
        index += 1
    return TILE_SHADES[index]


def _digit_size(value):
    """Four digits at 28 px would fill the whole 62 px slot, so the type steps down."""
    if value >= 1000:
        return 20
    if value >= 100:
        return 24
    return 28


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
        self.root_ = ui.screen(self.parent)
        self.header = ui.header(self.root_, TITLE, "Score 0")
        self.header.set_status("Score 0", ui.TEXT)

        board = ui.card(self.root_, BOARD_X, BOARD_Y, BOARD, BOARD,
                        bg=ui.SURFACE, radius=ui.R_LG)
        self.cells = []
        for r in range(N):
            row = []
            for c in range(N):
                cell = ui.box(board, PAD + c * (CELL + GAP), PAD + r * (CELL + GAP),
                              CELL, CELL, bg=ui.BG, radius=ui.R_MD)
                mark = ui.label(cell, "", 0, 0, size=28, color=ui.TEXT,
                                align=lv.ALIGN.CENTER)
                row.append((cell, mark))
            self.cells.append(row)

        # Arrow pad (inverted T) on the left, reset spanning both rows on the right:
        # up above, left/down/right in the row below -- the usual gamepad silhouette.
        ui.button(self.root_, "^", BOARD_X + (ARROW_W + ARROW_GAP), PAD_Y,
                  width=ARROW_W, callback=lambda: self._move("up"), kind="primary")
        lower_row = [("<", 0, "left"), ("v", 1, "down"), (">", 2, "right")]
        for text, column, direction in lower_row:
            ui.button(self.root_, text, BOARD_X + column * (ARROW_W + ARROW_GAP), PAD_ROW2,
                      width=ARROW_W,
                      callback=lambda d=direction: self._move(d), kind="primary")
        ui.button(self.root_, "Reset", SIDE_X, PAD_Y, width=SIDE_W, height=PAD_H,
                  callback=self._reset, kind="ghost")

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
                cell, mark = self.cells[r][c]
                surface = _tile_shade(value) if value else ui.BG
                cell.set_style_bg_color(lv.color_hex(surface), 0)
                mark.set_text(str(value) if value else "")
                if value:
                    mark.set_style_text_font(ui.font(_digit_size(value)), 0)
        self.header.set_status("Score %d" % self.score, ui.TEXT)

    def _check_state(self):
        for r in range(N):
            for c in range(N):
                if self.grid[r][c] >= 2048:
                    self.header.set_status("Score %d - you win" % self.score, ui.OK)
                    return
        if not self._any_move():
            self.done = True
            self.header.set_status("Score %d - game over" % self.score, ui.DANGER)

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
        self.header.set_status("Score 0", ui.TEXT)
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
        # root_ IS the active screen (ui.screen(parent)), so its widgets are removed
        # instead of the screen itself: deleting the screen leaves the display without
        # one and the next application has nothing to build on.
        try:
            self.root_.clean()
        except Exception:  # noqa: BLE001
            pass


def start(parent=None):
    """Build the game on `parent` (default: the active screen). Returns a handle."""
    return _Game2048(parent if parent is not None else lv.screen_active())
