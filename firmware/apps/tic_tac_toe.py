# tic_tac_toe.py -- Tic-tac-toe for the JC3248W535 (ESP32-S3, 320x480, LVGL 9).
#
# Self-contained LVGL app. Public API used by app_loader / launcher:
#   TITLE / DESCRIPTION      short texts for the launcher (TITEL/BESCHREIBUNG aliases)
#   start(parent=None)       builds the UI, returns a handle with .stop()
#
# Single player against a small unbeatable-ish computer: it wins if it can, blocks
# if it must, otherwise takes the centre or a random corner.
#
# Look and feel comes from _ui (tokens + widgets); this file only composes.

import random

import lvgl as lv

import _ui as ui

TITLE = "Tic-Tac-Toe"
DESCRIPTION = "You are X. Beat the computer, or take a draw."
TITEL = TITLE
BESCHREIBUNG = DESCRIPTION

CELL = 88
GAP = 8
GRID = 3 * CELL + 2 * GAP          # 280 px
BOARD_X = (320 - GRID) // 2
BOARD_Y = ui.HEADER_H + ui.S5

LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8),
         (0, 3, 6), (1, 4, 7), (2, 5, 8),
         (0, 4, 8), (2, 4, 6)]


class _TicTacToe:
    def __init__(self, parent):
        self.parent = parent
        self.board = [""] * 9
        self.done = False
        self._build()

    def _build(self):
        self.root_ = ui.screen(self.parent)
        self.header = ui.header(self.root_, TITLE, "Your turn (X)")

        board = ui.box(self.root_, BOARD_X, BOARD_Y, GRID, GRID)
        board.set_style_pad_all(0, 0)

        self.cells = []
        for i in range(9):
            row, column = divmod(i, 3)
            cell = ui.card(board, column * (CELL + GAP), row * (CELL + GAP), CELL, CELL,
                           bg=ui.SURFACE_ALT, radius=ui.R_MD, border=ui.GRID_LINE)
            mark = ui.label(cell, "", 0, 0, size=48, color=ui.MARK_X, align=lv.ALIGN.CENTER)
            ui.tap(cell, lambda index=i: self._tap(index), extra=0)
            self.cells.append((cell, mark))

        self.new_btn = ui.button(self.root_, "New game", (320 - 160) // 2, 400,
                                 width=160, kind="ghost", callback=self._reset)

    # ------------------------------------------------------------------ game logic
    def _tap(self, index):
        if self.done or self.board[index]:
            return
        self._place(index, "X")
        if self._finished():
            return
        self._ai_move()
        self._finished()

    def _place(self, index, mark):
        self.board[index] = mark
        cell, label = self.cells[index]
        label.set_text(mark)
        label.set_style_text_color(
            lv.color_hex(ui.MARK_X if mark == "X" else ui.MARK_O), 0)

    def _winner(self):
        for a, b, c in LINES:
            if self.board[a] and self.board[a] == self.board[b] == self.board[c]:
                return self.board[a], (a, b, c)
        if all(self.board):
            return "draw", ()
        return None, ()

    def _finished(self):
        result, line = self._winner()
        if result is None:
            return False
        self.done = True
        if result == "draw":
            self._status("Draw", ui.WARN)
        elif result == "X":
            self._status("You win", ui.OK)
        else:
            self._status("Computer wins", ui.DANGER)
        for index in line:
            cell = self.cells[index][0]
            cell.set_style_bg_color(lv.color_hex(ui.ACCENT_SOFT), 0)
            cell.set_style_border_color(lv.color_hex(ui.ACCENT), 0)
        return True

    def _status(self, text, color):
        if self.header.subtitle is not None:
            self.header.subtitle.set_text(text)
            self.header.subtitle.set_style_text_color(lv.color_hex(color), 0)

    def _free(self):
        return [i for i in range(9) if not self.board[i]]

    def _ai_move(self):
        for mark in ("O", "X"):                      # win, then block
            for index in self._free():
                self.board[index] = mark
                won = self._winner()[0] == mark
                self.board[index] = ""
                if won:
                    self._place(index, "O")
                    return
        if not self.board[4]:
            self._place(4, "O")
            return
        free = self._free()
        if free:
            self._place(random.choice(free), "O")

    def _reset(self):
        self.board = [""] * 9
        self.done = False
        self._status("Your turn (X)", ui.DIM)
        for cell, label in self.cells:
            label.set_text("")
            cell.set_style_bg_color(lv.color_hex(ui.SURFACE_ALT), 0)
            cell.set_style_border_color(lv.color_hex(ui.GRID_LINE), 0)

    # ------------------------------------------------------------- lifecycle
    def stop(self):
        # root_ is the display's active screen (ui.screen returns it), so clean it
        # instead of deleting it -- otherwise the next application has no screen.
        try:
            self.root_.clean()
        except Exception:  # noqa: BLE001
            pass


def start(parent=None):
    """Build the game on `parent` (default: the active screen). Returns a handle."""
    return _TicTacToe(parent if parent is not None else lv.screen_active())
