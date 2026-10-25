# scenes/minesweeper_revealed.py -- a partly solved board, for the preview render.
#
# Mines are placed by hand so the frame is reproducible; everything else goes through
# the app's own _tap / flood path, so the number ramp, the flag marker and the mode
# button label are the ones the device draws.
#
#   python3 tools/preview/preview.py tools/preview/scenes/minesweeper_revealed.py

import os
import sys

sys.path.insert(0, os.getenv("PREVIEW_APPS_DIR") or "firmware/apps")

import minesweeper as app

MINES = {(0, 0), (0, 2), (0, 4), (0, 6), (1, 4), (2, 3),
         (3, 2), (4, 2), (4, 6), (7, 7)}
FLAGS = [(0, 0), (0, 4), (4, 6)]


def start(screen):
    game = app.start(screen)
    game.mines = set(MINES)
    game._first = False
    game._tap(4, 4)              # floods the safe area
    game._toggle_mode()          # switch to flag mode
    for r, c in FLAGS:
        game._tap(r, c)
    return game
