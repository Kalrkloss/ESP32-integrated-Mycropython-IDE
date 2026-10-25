#!/bin/bash
# Rebuild the ESP32-S3 firmware with the design font set enabled.
#
# lib/lv_conf.h now enables Montserrat 20/24/28/40; without a rebuild the panel keeps
# showing 16 px for every size the applications ask for.
#
#   bash tools/build_firmware.sh
#
# The 4 MB application partition is not cosmetic: with the design font set enabled the
# default partition left 3.9 KB free, so the next font or driver would have failed the link.
#
# Output: /opt/lvgl_micropython/build/lvgl_micropy_ESP32_GENERIC_S3-SPIRAM_OCT-16.bin
# Flashing needs the board on USB (docs/01-board-jc3248w535.md); this script only builds.
set -e
TREE=/opt/lvgl_micropython

# ESP-IDF's export.sh prepends its own python paths; with them exported the build
# aborts, so drop PYTHONPATH for the make.py call itself.
source /opt/esp-idf/export.sh > /dev/null 2>&1 || { echo "no ESP-IDF at /opt/esp-idf"; exit 1; }

cd "$TREE"
env -u PYTHONPATH python3 make.py esp32 \
  BOARD=ESP32_GENERIC_S3 BOARD_VARIANT=SPIRAM_OCT \
  --flash-size=16 DISPLAY=axs15231b INDEV=axs15231 --ota \
  --partition-size=4194304

ls -la "$TREE"/build/*.bin
