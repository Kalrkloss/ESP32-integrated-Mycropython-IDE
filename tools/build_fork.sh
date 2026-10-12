#!/bin/bash
# Baut die Board-Firmware (MicroPython + LVGL) fuer den JC3248W535.
#
# Verwendet den Fork-Branch straga/lvgl_micropython -> feature/spi_bus_fast:
# nur dieser bringt lcd_bus.SPIBusFast (DMA + gestueckelte Transfers), ohne den
# dieses QSPI-Panel am Buslimit (32768 Byte) scheitert. Siehe docs/03-display-bringup.md.
set -euo pipefail

SRC="${FORK_SRC:-/opt/lvgl_mp_fork}"
REPO="https://github.com/straga/lvgl_micropython"
BRANCH="feature/spi_bus_fast"
IDF_EXPORT="${IDF_EXPORT:-/opt/esp-idf/export.sh}"
LOG="${BUILD_LOG:-/tmp/fork_build.log}"

if [ ! -d "$SRC" ]; then
  echo "== Klone $REPO ($BRANCH) nach $SRC"
  # WICHTIG: NICHT --recursive -- das Projekt holt seine Submodule selbst
  git clone -b "$BRANCH" "$REPO" "$SRC"
fi

cd "$SRC"
echo "== Stand: $(git rev-parse --short HEAD) ($(git rev-parse --abbrev-ref HEAD))"

# shellcheck disable=SC1090
source "$IDF_EXPORT" >/dev/null 2>&1

echo "== Build laeuft, Protokoll: $LOG"
python3 make.py esp32 BOARD=ESP32_GENERIC_S3 BOARD_VARIANT=SPIRAM_OCT \
  --flash-size=16 DISPLAY=axs15231b INDEV=axs15231 \
  --ota --partition-size=4194304 > "$LOG" 2>&1

echo "== fertig:"
ls -l "$SRC"/build/*.bin
