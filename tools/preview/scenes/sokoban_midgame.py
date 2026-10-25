# scenes/sokoban_midgame.py -- two pushes in, for the preview render.
#
# Renders the same application module in a later state so the box, box-on-goal,
# goal and player treatments can be judged without playing on the device.
#
#   python3 tools/preview/preview.py tools/preview/scenes/sokoban_midgame.py

import os
import sys

import lvgl as lv

sys.path.insert(0, os.getenv("PREVIEW_APPS_DIR") or "firmware/apps")

import sokoban as app


def start(screen):
    game = app.start(screen)
    # level 1: walk round the box and push it two squares to the right
    for dr, dc in ((0, -1), (-1, 0), (0, 1), (0, 1)):
        game._move(dr, dc)
    return game
