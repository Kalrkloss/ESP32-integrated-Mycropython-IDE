#!/bin/bash
# Build the LVGL MicroPython unix port used by tools/preview for headless rendering.
#
# Uses the lvgl_micropython integration tree (the same one that builds the ESP32
# firmware) in a separate clone, so the ESP32 build directory stays untouched.
# The builder compiles its own static SDL2 from lib/SDL, so no system SDL2 dev
# package is needed -- but do not pass SDL_FLAGS: those are extra *cmake* arguments
# for that SDL build, and pkg-config flags there abort with "Unknown argument -lSDL2".
#
# The binary lands under lib/micropython/ports/unix/build-standard/micropython.
set -e
SRC=/opt/lvgl_micropython
TREE=/opt/lvgl_unix

if [ ! -d "$TREE" ]; then
  # A real git clone, not a plain copy: make.py runs git commands (submodule and
  # version lookups) and dies with "not a git repository" if .git is missing.
  git clone -q --shared "$SRC" "$TREE"
fi

cd "$TREE"
env -u PYTHONPATH -u IDF_PATH -u IDF_PYTHON_ENV_PATH -u IDF_TOOLS_PATH \
  python3 make.py unix

BIN=$(find "$TREE/lib/micropython/ports/unix" "$TREE/build" -maxdepth 3 \
        -name micropython -type f -perm -u+x 2>/dev/null | head -1)
if [ -z "$BIN" ]; then
  echo "BUILD_FAILED no micropython binary in $TREE"
  exit 1
fi
echo "BUILD_OK $BIN"
echo "export LVMP_BIN=$BIN"
