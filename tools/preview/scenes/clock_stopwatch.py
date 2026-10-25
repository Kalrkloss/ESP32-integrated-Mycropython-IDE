# scenes/clock_stopwatch.py -- the stopwatch tab, running, for the preview render.
#
# start() only builds the clock tab, so the other two modes are reached by driving the
# application's own methods: this switches to the stopwatch page, starts it and fakes
# 83.4 s of elapsed time (the render is one frame, no timer runs).
#
#   python3 tools/preview/preview.py tools/preview/scenes/clock_stopwatch.py \
#       --out tools/preview/out/clock-stopwatch.png

import os
import sys
import time

import lvgl as lv

sys.path.insert(0, os.getenv("PREVIEW_APPS_DIR") or "firmware/apps")

import clock as app


def start(screen):
    handle = app.start(screen)
    handle._show("stopwatch")
    handle._sw_start()
    handle.sw_start = time.ticks_ms() - 83400      # scene only: pretend the clock ran
    handle._refresh_stopwatch()
    return handle
