#!/usr/bin/env python3
"""Render an application screen to a PNG without the board.

    python3 tools/preview/preview.py firmware/apps/launcher.py
    python3 tools/preview/preview.py firmware/apps/snake.py --out /tmp/snake.png
    python3 tools/preview/preview.py firmware/apps/clock.py --state '{"mode": "stopwatch"}'

Needs a lv_micropython unix binary (LVGL 9). Resolution order:
$LVMP_BIN, /opt/lv_micropython/ports/unix/micropython, ~/lv_micropython/ports/unix/micropython.
Build it with tools/preview/build_runtime.sh.

The pixel dump is raw BGRA from LVGL's 32-bit surface; pillow converts it to PNG.
Panel geometry comes from --size and defaults to the JC3248W535 (320x480).
"""

import argparse
import os
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
STUB = os.path.join(HERE, "stub")
CANDIDATES = [
    os.environ.get("LVMP_BIN"),
    "/opt/lvgl_unix/lib/micropython/ports/unix/build-standard/micropython",
    "/opt/lvgl_micropython/lib/micropython/ports/unix/build-standard/micropython",
    os.path.expanduser("~/lv_micropython/ports/unix/micropython"),
]


def find_binary():
    for path in CANDIDATES:
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    sys.exit("no lv_micropython unix binary; run tools/preview/build_runtime.sh "
             "or point $LVMP_BIN at ports/unix/micropython")


def raw_to_png(raw_path, png_path):
    from PIL import Image

    with open(raw_path, "rb") as fh:
        width, height = struct.unpack("<II", fh.read(8))
        data = fh.read()
    image = Image.frombytes("RGBA", (width, height), data, "raw", "BGRA").convert("RGB")
    image.save(png_path)
    return width, height


def main():
    parser = argparse.ArgumentParser(description="Render an LVGL app to PNG")
    parser.add_argument("app", help="path to an application module (needs start(parent))")
    parser.add_argument("--out", help="output PNG (default: <app>.png in tools/preview/out/)")
    parser.add_argument("--size", default="320x480", help="panel size WxH (default 320x480)")
    parser.add_argument("--state", default="", help="JSON kwargs for start(parent, **state)")
    parser.add_argument("--binary", help="override the lv_micropython binary")
    args = parser.parse_args()

    binary = args.binary or find_binary()
    app = os.path.abspath(args.app)
    if not os.path.isfile(app):
        sys.exit("no such app: " + app)
    width, height = (int(part) for part in args.size.lower().split("x"))

    if args.out:
        out = os.path.abspath(args.out)
    else:
        out_dir = os.path.join(HERE, "out")
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, os.path.splitext(os.path.basename(app))[0] + ".png")

    env = dict(os.environ)
    env["MICROPYPATH"] = STUB + (":" + env["MICROPYPATH"] if env.get("MICROPYPATH") else "")
    env["PREVIEW_APPS_DIR"] = os.path.join(REPO, "firmware", "apps")
    env.setdefault("SDL_VIDEODRIVER", "dummy")

    with tempfile.NamedTemporaryFile(suffix=".raw", delete=False) as handle:
        raw = handle.name
    try:
        result = subprocess.run(
            [binary, "-X", "heapsize=64m", os.path.join(HERE, "render.py"),
             app, raw, str(width), str(height), args.state],
            env=env, capture_output=True, text=True,
        )
        if result.stdout.strip():
            print(result.stdout.strip())
        if result.returncode != 0 or not os.path.getsize(raw):
            sys.stderr.write(result.stderr[-2000:])
            sys.exit("render failed (rc=%d)" % result.returncode)
        w, h = raw_to_png(raw, out)
        print("%dx%d -> %s" % (w, h, out))
    finally:
        try:
            os.remove(raw)
        except OSError:
            pass


if __name__ == "__main__":
    main()
