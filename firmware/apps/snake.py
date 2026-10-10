# snake.py -- Snake game for the JC3248W535 (ESP32-S3, 320x480, LVGL 9).
#
# Self-contained LVGL app. Public API used by app_loader / launcher:
#   TITLE / DESCRIPTION      short texts for the launcher (TITEL/BESCHREIBUNG aliases)
#   start(parent=None)       builds the UI, returns a handle with .stop()
#
# Rules kept: only lvgl + stdlib, animation via our own lv.timer_create, full
# cleanup in stop(), touch targets >= 40x40 px, LVGL is only touched from the
# main thread (the game loop is an LVGL timer, so it runs in the main loop).

import random

import lvgl as lv

TITLE = "Snake"
DESCRIPTION = "Steer the snake, eat the food, do not bite yourself."
TITEL = TITLE
BESCHREIBUNG = DESCRIPTION

CELL = 40          # touch target size; the field is CELL * N pixels
N = 8              # 8 x 8 cells -> 320 x 320 pixel field
TICK_MS = 200

BG = 0x101820
FIELD = 0x202830
SNAKE = 0x30D060
HEAD = 0x00FFA0
FOOD = 0xE04040
TEXT = 0xFFFFFF
ACCENT = 0x3A6EA5


def _font(size):
    """Largest available montserrat font at or below `size` (fallback 16)."""
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
        self.root_ = lv.obj(self.parent)
        self.root_.set_pos(0, 0)
        self.root_.set_size(320, 480)
        self.root_.set_style_bg_color(lv.color_hex(BG), 0)
        self.root_.set_style_border_width(0, 0)
        _zero_pad(self.root_)

        self.score_label = _label(self.root_, "Score: 0", 10, 8, TEXT, 20)

        field = _rect(self.root_, 0, 44, N * CELL, N * CELL, FIELD)
        field.remove_flag(lv.obj.FLAG.SCROLLABLE)
        self.cells = []
        for r in range(N):
            row = []
            for c in range(N):
                cell = _rect(field, c * CELL, r * CELL, CELL - 2, CELL - 2, FIELD)
                row.append(cell)
            self.cells.append(row)

        self.status = _label(self.root_, "", 10, 372, FOOD, 18)

        # Movement pad: 4 arrows in a cross, all >= 40x40.
        self._arrow(120, 400, "^", (0, -1))
        self._arrow(60, 400, "<", (-1, 0))
        self._arrow(180, 400, ">", (1, 0))
        self._arrow(120, 448, "v", (0, 1))
        _button(self.root_, 244, 424, 66, 56, "Restart", self._reset, ACCENT)

    def _arrow(self, x, y, text, direction):
        def press():
            self.next_dir = direction
        _button(self.root_, x, y, 56, 48, text, press, ACCENT)

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
                    color = SNAKE
                elif (c, r) == self.food:
                    color = FOOD
                else:
                    color = FIELD
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
        self.status.set_text("Game over -- score %d" % self.score)

    def _reset(self):
        self.state = "run"
        self.dir = (1, 0)
        self.next_dir = (1, 0)
        self.snake = [(2, 4), (1, 4), (0, 4)]
        self.score = 0
        self.score_label.set_text("Score: 0")
        self.status.set_text("")
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
    return _Snake(parent if parent is not None else lv.screen_active())
