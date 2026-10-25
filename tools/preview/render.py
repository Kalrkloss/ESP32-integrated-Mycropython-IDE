# render.py -- run an application module headless and dump the framebuffer.
#
# Runs inside the lv_micropython unix port (not on the board):
#   <lvmp_bin> -X heapsize=64m render.py <app.py> <out.raw> <W> <H> [state_json]
#
# It registers a full-screen single-buffer display, imports the app module, calls its
# start() and refreshes one frame synchronously. The buffer is a full frame after
# lv.refr_now(), so it is written out as-is (8-byte header + BGRA pixels).
#
# The app is imported from its own directory, so sibling imports resolve. A stub
# directory placed first in the search path provides the device-only modules
# (app_loader) that an app imports but cannot run on a desktop.

import sys

import lvgl as lv

if len(sys.argv) < 5:
    sys.exit("usage: render.py <app.py> <out.raw> <W> <H> [state_json]")

app_path = sys.argv[1]
out_raw = sys.argv[2]
WIDTH = int(sys.argv[3])
HEIGHT = int(sys.argv[4])
state = {}
if len(sys.argv) > 5 and sys.argv[5] not in ("", "{}"):
    import json
    state = json.loads(sys.argv[5])

lv.init()

# Full-screen single buffer: after one refresh it holds the whole frame. The
# reference must be kept alive, LVGL only stores the pointer.
frame = bytearray(WIDTH * HEIGHT * 4)
V8 = hasattr(lv, "disp_drv_t")

if V8:
    draw_buf = lv.disp_draw_buf_t()
    draw_buf.init(frame, None, WIDTH * HEIGHT)
    drv = lv.disp_drv_t()
    drv.init()
    drv.draw_buf = draw_buf
    drv.hor_res = WIDTH
    drv.ver_res = HEIGHT

    def _flush(d, area, color_p):
        d.flush_ready()

    drv.flush_cb = _flush
    drv.register()
else:
    create = getattr(lv, "disp_create", None) or getattr(lv, "display_create", None)
    disp = create(WIDTH, HEIGHT)
    color_format = getattr(lv, "COLOR_FORMAT", None)
    if color_format is not None and hasattr(disp, "set_color_format"):
        disp.set_color_format(color_format.ARGB8888)
    render_mode = getattr(lv, "DISPLAY_RENDER_MODE", None) or getattr(lv, "DISP_RENDER_MODE", None)

    # The binding's signature is set_buffers(buf1, buf2, size, mode) -- four
    # arguments. set_draw_buffers() wants an lv_draw_buf_t, not a bytearray, so it is
    # not an option here.
    if hasattr(disp, "set_buffers"):
        disp.set_buffers(frame, None, len(frame), render_mode.FULL)
    else:
        disp.set_buffer(frame, len(frame), render_mode.FULL)

    def _flush_v9(d, area, px):
        d.flush_ready()

    set_flush = getattr(disp, "set_flush_cb", None)
    if set_flush is not None:
        set_flush(_flush_v9)

directory, base = (app_path.rsplit("/", 1) + [""])[:2] if "/" in app_path else (".", app_path)
if base.endswith(".py"):
    base = base[:-3]
sys.path.insert(0, directory)

module = __import__(base)
screen_getter = getattr(lv, "scr_act", None) or getattr(lv, "screen_active", None)
screen = screen_getter()
if screen is None:
    sys.exit("no active screen -- the display was not registered")

build = getattr(module, "start")
if state:
    build(screen, **state)
else:
    build(screen)

default_display = getattr(lv, "disp_get_default", None) or getattr(lv, "display_get_default", None)
lv.refr_now(default_display())

with open(out_raw, "wb") as fh:
    fh.write(WIDTH.to_bytes(4, "little"))
    fh.write(HEIGHT.to_bytes(4, "little"))
    fh.write(frame)
print("rendered %s -> %s (%dx%d, %s)" % (app_path, out_raw, WIDTH, HEIGHT, "v8" if V8 else "v9"))
