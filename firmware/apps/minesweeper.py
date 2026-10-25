# minesweeper.py -- Minesweeper for the JC3248W535 (ESP32-S3, 320x480, LVGL 9).
#
# Self-contained LVGL app. Public API used by app_loader / launcher:
#   TITLE / DESCRIPTION      short texts for the launcher (TITEL/BESCHREIBUNG aliases)
#   start(parent=None)       builds the UI, returns a handle with .stop()
#
# Rules kept: only lvgl + stdlib, our own lv.timer_create where needed, full
# cleanup in stop(), every control at least 48 px tall, LVGL only from the main thread.
#
# Look and feel comes from _ui (tokens + widgets); this file only composes.

import random

import lvgl as lv

import _ui as ui

TITLE = "Minesweeper"
DESCRIPTION = "Find every safe tile. Tap to dig, toggle a mode to flag mines."
TITEL = TITLE
BESCHREIBUNG = DESCRIPTION

N = 8                                  # 8 x 8 board
CELL = 34
GAP = ui.S1                            # 4 px between tiles
BOARD = N * CELL + (N - 1) * GAP       # 300 px
BOARD_X = (320 - BOARD) // 2
BOARD_Y = ui.HEADER_H + ui.S2
ACTION_Y = BOARD_Y + BOARD + ui.S3
MINES = 10

# Tile colours, from the design tokens only.
HIDDEN = ui.SURFACE_ALT                # untouched tile
OPEN = ui.SURFACE                      # dug tile, reads as recessed
FLAG = ui.MARK_O
MINE = ui.DANGER

# Count colours. The token set has no eight-step ramp, so the ramp is built from
# the semantic and marker colours: still one place, still no raw hex.
NUM_COLORS = {1: ui.MARK_X, 2: ui.OK, 3: ui.DANGER, 4: ui.ACCENT,
              5: ui.MARK_O, 6: ui.WARN, 7: ui.TEXT, 8: ui.DIM}


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
        self.root_ = ui.screen(self.parent)
        self.header = ui.header(self.root_, TITLE, "Mines: %d" % MINES)
        self.status = ui.label(self.header.band, "", -ui.S4, 0, size=18,
                               color=ui.DIM, align=lv.ALIGN.RIGHT_MID)

        field = ui.box(self.root_, BOARD_X, BOARD_Y, BOARD, BOARD)
        self.cells = []
        self.labels = []
        for r in range(N):
            row, rowlab = [], []
            for c in range(N):
                cell = ui.card(field, c * (CELL + GAP), r * (CELL + GAP), CELL, CELL,
                               bg=HIDDEN, radius=ui.R_SM, border=ui.GRID_LINE)
                lab = ui.label(cell, "", 0, 0, size=18, color=ui.TEXT,
                               align=lv.ALIGN.CENTER)
                # No click-area extension: the 4 px gaps would make two neighbours'
                # hit areas touch, so the tile itself is the target.
                ui.tap(cell, lambda r=r, c=c: self._tap(r, c), extra=0)
                row.append(cell)
                rowlab.append(lab)
            self.cells.append(row)
            self.labels.append(rowlab)

        self.mode_btn = ui.button(self.root_, "Mode: Dig", 8, ACTION_Y, width=148,
                                  kind="ghost", callback=self._toggle_mode)
        ui.button(self.root_, "New game", 164, ACTION_Y, width=148,
                  kind="ghost", callback=self._reset)
        ui.footer(self.root_, "Tap a tile to reveal it")

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
            lab.set_style_text_color(lv.color_hex(NUM_COLORS.get(n, ui.TEXT)), 0)
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
            self.labels[mr][mc].set_style_text_color(lv.color_hex(ui.TEXT), 0)
            self.labels[mr][mc].center()
        self.cells[r][c].set_style_bg_color(lv.color_hex(MINE), 0)
        self.status.set_text("BOOM!")
        self.status.set_style_text_color(lv.color_hex(ui.DANGER), 0)

    def _check_win(self):
        if len(self.open_cells) == N * N - len(self.mines):
            self.state = "won"
            self.status.set_text("CLEAR!")
            self.status.set_style_text_color(lv.color_hex(ui.OK), 0)

    def _reset(self):
        self.state = "run"
        self.flag_mode = False
        self._first = True
        self.mines = set()
        self.open_cells = set()
        self.flags = set()
        self.status.set_text("")
        self.status.set_style_text_color(lv.color_hex(ui.DIM), 0)
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
            # root_ is the display's active screen -- clean it, never delete it.
            self.root_.clean()
        except Exception:  # noqa: BLE001
            pass


def start(parent=None):
    """Build the game on `parent` (default: the active screen). Returns a handle."""
    return _Minesweeper(parent if parent is not None else lv.screen_active())
