# scenes/tic_tac_toe_win.py -- a finished game, for the preview render.
#
# Renders the same application module in a later state so the marks, the winning-line
# highlight and the status colour can be judged without playing on the device.
#
#   python3 tools/preview/preview.py tools/preview/scenes/tic_tac_toe_win.py

import os
import sys

import lvgl as lv

sys.path.insert(0, os.getenv("PREVIEW_APPS_DIR") or "firmware/apps")

import tic_tac_toe as app


def start(screen):
    game = app.start(screen)
    for index, mark in ((0, "X"), (3, "O"), (1, "X"), (4, "O"), (2, "X")):
        game._place(index, mark)
    game._finished()
    return game
