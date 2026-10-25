# scenes/calculator_result.py -- a evaluated expression, for the preview render.
#
# Drives the key handlers of the real calculator so the readout path (expression line,
# result line, "=" handling) is exercised instead of only the empty screen.
#
#   python3 tools/preview/preview.py tools/preview/scenes/calculator_result.py

import os
import sys

import lvgl as lv

sys.path.insert(0, os.getenv("PREVIEW_APPS_DIR") or "firmware/apps")

import calculator as app


def start(screen):
    calculator = app.start(screen)
    for key in ("7", "*", "8", "="):
        calculator._press(key)
    return calculator
