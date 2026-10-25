#!/bin/bash
# esp32sim-check.sh -- boot this firmware in esp32sim and say what happened.
#
#   tools/esp32sim-check.sh              # uses the newest firmware build
#   BOARD=jc3248w535 tools/esp32sim-check.sh
#   FS=/root/.hermes/cache/scratch/board-vfs.img tools/esp32sim-check.sh
#
# Exit codes: 0 the panel was painted, 1 firmware booted but no display, 3 the emulator
# has no JC3248W535 board model yet, 4 the firmware did not boot at all.
#
# The firmware is a merged flash image (full dump at 0x0), so it is passed as
# --flash-image rather than as --app: the application lives in ota_0 at 0x20000, while
# --app always writes at 0x10000. The vfs FAT partition (config.json, wifi.json, /apps)
# sits at 0x820000; without it the board boots into setup mode, which is a valid run but
# not the one that shows the launcher.
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
EMU="${ESP32SIM:-/root/esp32sim/target/release/esp32sim}"
ROM="${ROM:-/root/esp32sim/roms/esp32s3_rev0_rom.elf}"
FW="${FW:-/opt/lvgl_micropython/build/lvgl_micropy_ESP32_GENERIC_S3-SPIRAM_OCT-16.bin}"
FS="${FS:-/root/.hermes/cache/scratch/board-vfs.img}"   # FAT dump of the vfs partition, 0x820000
SECS="${SECS:-15}"
BOARD="${BOARD:-jc3248w535}"
OUT="${OUT:-/root/.hermes/cache/scratch/esp32sim-check}"
mkdir -p "$OUT"

[ -x "$EMU" ] || { echo "no emulator at $EMU (set ESP32SIM)"; exit 4; }
[ -f "$ROM" ] || { echo "no ROM ELF at $ROM (set ROM)"; exit 4; }
[ -f "$FW" ] || { echo "no firmware at $FW (set FW)"; exit 4; }

extra=()
if [ -n "$FS" ] && [ -f "$FS" ]; then
  extra+=(--flash-at "0x820000=$FS")
else
  echo "note: no filesystem image ($FS) -- the board boots without boot.py/main.py"
fi

run() {
  "$EMU" --chip s3 --boot rom --board "$BOARD" --rom "$ROM" \
         --flash-image "$FW" --flash-mb 16 --psram-mb 8 \
         "${extra[@]}" --console both --max-seconds "$1" 2>&1
}

# --- board model present? -------------------------------------------------------------
probe="$(run 1)"
case "$probe" in
  *"unknown board"*)
    known="$(printf '%s\n' "$probe" | sed -n 's/^unknown board [^(]*(\(.*\))$/\1/p')"
    echo "esp32sim has no '$BOARD' model yet."
    echo "boards it knows: $known"
    exit 3 ;;
esac

# --- real run -------------------------------------------------------------------------
log="$OUT/run.log"
png="$OUT/panel.png"
rm -f "$png"
"$EMU" --chip s3 --boot rom --board "$BOARD" --rom "$ROM" \
       --flash-image "$FW" --flash-mb 16 --psram-mb 8 \
       "${extra[@]}" --console both --max-seconds "$SECS" \
       --tft-png "$png" > "$log" 2>&1

booted=0
grep -q 'MicroPython .* on ' "$log" && booted=1
banner="$(grep -m1 'MicroPython .* on ' "$log" | tr -d '\r')"
panel="$(grep -m1 -i '\[emu\].*bbox=\|\[emu\].*panel\|\[emu\].*tft' "$log" | tr -d '\r')"
setup=0
grep -q 'setup mode' "$log" && setup=1
app_ok="$(grep -m1 -E 'main: debug server|started launcher' "$log" | tr -d '\r')"

echo "emulator : $EMU"
echo "board    : $BOARD   (${SECS}s emulated, fs=${FS:-none})"
echo "booted   : $booted  ${banner}"
echo "app      : ${app_ok:-<no main.py line>}"
echo "setup    : $setup (1 means no WiFi config on the guest filesystem)"
echo "panel    : ${panel:-<no display line>}"
echo "png      : $([ -f "$png" ] && stat -c '%s bytes' "$png" || echo missing)"
echo "log      : $log"

[ "$booted" -eq 1 ] || exit 4
[ -f "$png" ] && [ -n "$panel" ] && exit 0
exit 1
