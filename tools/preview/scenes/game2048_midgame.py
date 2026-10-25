# scenes/game2048_midgame.py -- a board with mixed values, for the preview render.
#
# Renders the same application module in a later state so the tile ramp, the digit
# contrast and the empty-slot contrast can be judged without playing on the device.
#
#   python3 tools/preview/preview.py tools/preview/scenes/game2048_midgame.py

import os
import sys

import lvgl as lv

sys.path.insert(0, os.getenv("PREVIEW_APPS_DIR") or "firmware/apps")

import game2048 as app


def start(screen):
    game = app.start(screen)
    game.grid = [
        [2, 4, 8, 16],
        [32, 64, 128, 256],
        [512, 1024, 2048, 0],
        [0, 0, 0, 2],
    ]
    game.score = 20348
    game._draw()
    return game
