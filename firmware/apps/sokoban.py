# sokoban.py -- Sokoban for the JC3248W535 (ESP32-S3, 320x480, LVGL 9).
#
# Self-contained LVGL app. Public API used by app_loader / launcher:
#   TITLE / DESCRIPTION      short texts for the launcher (TITEL/BESCHREIBUNG aliases)
#   start(parent=None)       builds the UI, returns a handle with .stop()
#
# Rules kept: only lvgl + stdlib, our own lv.timer_create where needed, full
# cleanup in stop(), LVGL only from the main thread.
#
# Look and feel comes from _ui (tokens + widgets); this file only composes.
# A cell carries colour *and* the classic ASCII glyph, so the board still reads on
# a display where the accent shades are close together.

import lvgl as lv

import _ui as ui

TITLE = "Sokoban"
DESCRIPTION = "Push every box onto a goal. Arrows move, undo and reset help."
TITEL = TITLE
BESCHREIBUNG = DESCRIPTION

N = 8
CELL = 36                      # 8 x 8 slots -> 288 x 288 px board
TILE = CELL - ui.S1            # 32 px square, 4 px gap from the S scale
BOARD = N * CELL
BOARD_X = (320 - BOARD) // 2
BOARD_Y = ui.HEADER_H + ui.S2

ARROW_W = 56
ARROW_GAP = ui.S2
SIDE_W = 96
SIDE_X = 320 - ui.S4 - SIDE_W
PAD_Y = BOARD_Y + BOARD + ui.S3
PAD_ROW2 = PAD_Y + ui.TOUCH_MIN + ui.S2

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
        self.root_ = ui.screen(self.parent)
        self.header = ui.header(self.root_, TITLE, self._level_text(1))

        board = ui.box(self.root_, BOARD_X, BOARD_Y, BOARD, BOARD)
        self.cells = []
        for r in range(N):
            row = []
            for c in range(N):
                # Floor slots are dark wells with a hairline outline; a wall is the
                # same slot filled with the raised surface, so the two never blend.
                cell = ui.card(board, c * CELL, r * CELL, TILE, TILE,
                               bg=ui.BG, radius=ui.R_SM)
                mark = ui.label(cell, "", 0, 0, size=20, color=ui.TEXT,
                                align=lv.ALIGN.CENTER)
                row.append((cell, mark))
            self.cells.append(row)

        # Arrow pad (inverted T) on the left, undo/reset in the right-hand column:
        # up above, left/down/right in the row below -- the usual gamepad silhouette.
        ui.button(self.root_, "^", BOARD_X + (ARROW_W + ARROW_GAP), PAD_Y,
                  width=ARROW_W, callback=lambda: self._move(-1, 0), kind="primary")
        lower_row = [("<", 0, 0, -1), ("v", 1, 1, 0), (">", 2, 0, 1)]
        for text, column, dr, dc in lower_row:
            ui.button(self.root_, text, BOARD_X + column * (ARROW_W + ARROW_GAP), PAD_ROW2,
                      width=ARROW_W, callback=lambda a=dr, b=dc: self._move(a, b),
                      kind="primary")

        ui.button(self.root_, "Undo", SIDE_X, PAD_Y, width=SIDE_W,
                  callback=self._undo, kind="ghost")
        ui.button(self.root_, "Reset", SIDE_X, PAD_ROW2, width=SIDE_W,
                  callback=self._reset, kind="ghost")

    def _level_text(self, index):
        return "Level %d - every box on a goal" % index

    def _status(self, text, color=ui.DIM):
        self.header.set_status(text, color)

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
        self._status(self._level_text(self.level_index + 1))
        self._draw()

    def _tile(self, r, c):
        """State -> (surface, ink, glyph), all of them tokens."""
        if self.grid[r][c] == "#":
            return ui.WALL, ui.TEXT, ""
        if (r, c) in self.boxes:
            if (r, c) in self.goals:
                return ui.OK, ui.BG, "*"
            return ui.WARN, ui.BG, "$"
        if (r, c) == self.player:
            return ui.ACCENT, ui.ACCENT_TEXT, "@"
        if (r, c) in self.goals:
            return ui.BG, ui.DIM, "o"
        return ui.BG, ui.TEXT, ""

    def _draw(self):
        for r in range(N):
            for c in range(N):
                cell, mark = self.cells[r][c]
                surface, ink, glyph = self._tile(r, c)
                cell.set_style_bg_color(lv.color_hex(surface), 0)
                cell.set_style_border_color(
                    lv.color_hex(ui.LINE if surface == ui.BG else ui.GRID_LINE), 0)
                mark.set_style_text_color(lv.color_hex(ink), 0)
                mark.set_text(glyph)

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
            self._status(self._level_text(self.level_index + 1))

    def _reset(self):
        self._load_level(self.level_index)

    def _check_win(self):
        if self.boxes and self.boxes.issubset(self.goals):
            self._status("Level %d solved" % (self.level_index + 1), ui.OK)

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
    return _Sokoban(parent if parent is not None else lv.screen_active())
