# scenes/snake_mid.py -- a game in progress, for the preview render.
#
# Renders the same application module after a few moves so the body/head/food tiles
# and the score line can be judged without playing on the device. The state is set
# through the app's own attributes and its own _draw().
#
#   python3 tools/preview/preview.py tools/preview/scenes/snake_mid.py

import os
import sys

sys.path.insert(0, os.getenv("PREVIEW_APPS_DIR") or "firmware/apps")

import snake as app


def start(screen):
    game = app.start(screen)
    game.snake = [(3, 2), (3, 3), (2, 3), (1, 3), (1, 2), (0, 2)]
    game.food = (6, 5)
    game.score = 4
    game.score_label.set_text("Score: %d" % game.score)
    game._draw()
    return game
