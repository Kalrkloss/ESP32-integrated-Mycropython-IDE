#!/bin/bash
# esp32sim-fs.sh -- give esp32sim an image of the board's filesystem.
#
# boot.py, main.py, /apps and /web live on the FAT partition `vfs` (offset 0x820000, size
# 0x7E0000), not in the application image. Without it esp32sim boots to the bare REPL and
# never runs the firmware. The partition is passed with `--flash-at 0x820000=<image>`.
#
#   tools/esp32sim-fs.sh            # dump the partition from the attached board
#   tools/esp32sim-fs.sh --check    # say which image would be used
#
# The image is read from the device with esptool, not built here: creating a FAT
# filesystem is blocked for the agent (mkfs is on the hardline blocklist), and a dump is
# the more honest input anyway -- it is exactly what the panel runs.
#
# Needs the board on USB. 8 MB at 230400 baud takes about four minutes.
set -euo pipefail

ARGS=()
OUT=""
for arg in "$@"; do
  case "$arg" in
    --check) MODE=check ;;
    *) OUT="$arg" ;;
  esac
done
OUT="${OUT:-/root/.hermes/cache/scratch/board-vfs.img}"
MODE="${MODE:-dump}"
PORT="${PORT:-/dev/ttyACM1}"
OFFSET=0x820000
SIZE=0x7E0000
ESPTOOL_PY="${ESPTOOL_PY:-/opt/esp-tools/bin/python3}"

if [ "$MODE" = "check" ]; then
  [ -f "$OUT" ] && echo "filesystem image: $OUT ($(stat -c %s "$OUT") bytes)" \
                || echo "no filesystem image at $OUT -- run tools/esp32sim-fs.sh with the board attached"
  exit 0
fi

[ -e "$PORT" ] || { echo "no board at $PORT (PORT=... to override)"; exit 1; }

for attempt in 1 2 3; do
  if "$ESPTOOL_PORT" -m esptool --chip esp32s3 -p "$PORT" -b 230400 \
       --before default_reset --after hard_reset \
       read_flash $OFFSET $SIZE "$OUT"; then
    echo "dumped $OUT ($(stat -c %s "$OUT") bytes)"
    exit 0
  fi
  echo "attempt $attempt failed, retrying"
  sleep 5
done
echo "dump failed after 3 attempts"
exit 1
