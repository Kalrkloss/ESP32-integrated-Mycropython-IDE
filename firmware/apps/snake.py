# snake.py -- Snake game for the JC3248W535 (ESP32-S3, 320x480, LVGL 9).
#
# Self-contained LVGL app. Public API used by app_loader / launcher:
#   TITLE / DESCRIPTION      short texts for the launcher (TITEL/BESCHREIBUNG aliases)
#   start(parent=None)       builds the UI, returns a handle with .stop()
#
# Rules kept: only lvgl + stdlib, animation via our own lv.timer_create, full
# cleanup in stop(), every control at least 48 px tall, LVGL is only touched from
# the main thread (the game loop is an LVGL timer, so it runs in the main loop).
#
# Look and feel comes from _ui (tokens + widgets); this file only composes.

import random

import lvgl as lv

import _ui as ui

TITLE = "Snake"
DESCRIPTION = "Steer the snake, eat the food, do not bite yourself."
TITEL = TITLE
BESCHREIBUNG = DESCRIPTION

N = 8                      # 8 x 8 cells
GAP = ui.S1                # 4 px between tiles
CELL = 32                  # tile size -> 8 * 32 + 7 * 4 = 284 px field
FIELD = N * CELL + (N - 1) * GAP
FIELD_X = (320 - FIELD) // 2
FIELD_Y = ui.HEADER_H + ui.S2
TICK_MS = 200

PAD = 48                   # arrow buttons: square, exactly the touch minimum
PAD_Y = FIELD_Y + FIELD + ui.S2
RESET_Y = PAD_Y + PAD + ui.S2

# Tile colours, from the design tokens only.
EMPTY = ui.SURFACE_ALT     # free cell
BODY = ui.OK               # snake body
HEAD = ui.MARK_X           # snake head
FOOD = ui.DANGER           # food


class _Snake:
    def __init__(self, parent):
        self.parent = parent
        self.timer = None
        self.state = "run"           # run | over
        self.dir = (1, 0)
        self.next_dir = (1, 0)
        self.snake = [(2, 4), (1, 4), (0, 4)]
        self.food = (N - 2, 4)
        self.score = 0
        self._build()
        self._draw()
        self._spawn_food()
        self.timer = lv.timer_create(self._tick, TICK_MS, None)

    # ------------------------------------------------------------- UI
    def _build(self):
        self.root_ = ui.screen(self.parent)
        self.header = ui.header(self.root_, TITLE, "Steer with the pad")
        self.score_label = ui.label(self.header.band, "Score: 0", -ui.S4, 0, size=16,
                                    color=ui.DIM, align=lv.ALIGN.RIGHT_MID)

        field = ui.box(self.root_, FIELD_X, FIELD_Y, FIELD, FIELD)
        self.cells = []
        for r in range(N):
            row = []
            for c in range(N):
                tile = ui.card(field, c * (CELL + GAP), r * (CELL + GAP), CELL, CELL,
                               bg=EMPTY, radius=ui.R_SM, border=ui.GRID_LINE)
                row.append(tile)
            self.cells.append(row)

        # Movement pad: four arrows in one row, each a full touch target.
        step = PAD + ui.S2
        left = (320 - (4 * PAD + 3 * ui.S2)) // 2
        self._arrow(left, PAD_Y, "<", (-1, 0))
        self._arrow(left + step, PAD_Y, "^", (0, -1))
        self._arrow(left + 2 * step, PAD_Y, "v", (0, 1))
        self._arrow(left + 3 * step, PAD_Y, ">", (1, 0))

        ui.button(self.root_, "Restart", (320 - 160) // 2, RESET_Y, width=160,
                  kind="ghost", callback=self._reset)

    def _arrow(self, x, y, text, direction):
        def press():
            self.next_dir = direction
        ui.button(self.root_, text, x, y, width=PAD, height=PAD,
                  callback=press, kind="ghost")

    # ------------------------------------------------------------- game
    def _spawn_food(self):
        free = [(c, r) for r in range(N) for c in range(N) if (c, r) not in self.snake]
        if free:
            self.food = random.choice(free)

    def _draw(self):
        body = set(self.snake)
        for r in range(N):
            for c in range(N):
                if (c, r) == self.snake[0]:
                    color = HEAD
                elif (c, r) in body:
                    color = BODY
                elif (c, r) == self.food:
                    color = FOOD
                else:
                    color = EMPTY
                self.cells[r][c].set_style_bg_color(lv.color_hex(color), 0)

    def _tick(self, _timer=None):
        if self.state != "run":
            return None
        self.dir = self.next_dir
        hx, hy = self.snake[0]
        nx, ny = hx + self.dir[0], hy + self.dir[1]
        if nx < 0 or nx >= N or ny < 0 or ny >= N or (nx, ny) in self.snake[:-1]:
            self._game_over()
            return None
        self.snake.insert(0, (nx, ny))
        if (nx, ny) == self.food:
            self.score += 1
            self.score_label.set_text("Score: %d" % self.score)
            self._spawn_food()
        else:
            self.snake.pop()
        self._draw()
        return None

    def _game_over(self):
        self.state = "over"
        self.header.set_status("Game over - score %d" % self.score, ui.DANGER)

    def _reset(self):
        self.state = "run"
        self.dir = (1, 0)
        self.next_dir = (1, 0)
        self.snake = [(2, 4), (1, 4), (0, 4)]
        self.score = 0
        self.score_label.set_text("Score: 0")
        self.header.set_status("Steer with the pad", ui.DIM)
        self._spawn_food()
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
            # root_ is the display's active screen -- clean it, never delete it.
            self.root_.clean()
        except Exception:  # noqa: BLE001
            pass


def start(parent=None):
    """Build the game on `parent` (default: the active screen). Returns a handle."""
    return _Snake(parent if parent is not None else lv.screen_active())
