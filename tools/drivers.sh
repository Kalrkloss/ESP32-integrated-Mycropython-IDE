#!/bin/bash
# Collect display and touch drivers into firmware/device/drv/ so they ship with
# the firmware and can be selected on the device at runtime.
#
# Layout on the device (and in the repo):
#   /drv/display/<name>/<name>.py   (a package may hold several files)
#   /drv/indev/<name>.py
#
# Our own patched files win over the upstream ones: the AXS15231B driver and the
# AXS15231 touch driver carry the fixes from docs/03-display-bringup.md and
# docs/04-touch-bringup.md.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${SRC:-/opt/lvgl_micropython/api_drivers/common_api_drivers}"
DST="$REPO/firmware/device/drv"
PATCHED="$REPO/firmware/device/drivers"

[ -d "$SRC/display" ] || { echo "FEHLER: $SRC/display fehlt (SRC setzen)" >&2; exit 1; }

echo "== Quelle: $SRC"
rm -rf "$DST"
mkdir -p "$DST/display" "$DST/indev"

# --- display drivers: one directory per driver ---
count_display=0
for dir in "$SRC"/display/*/; do
  name="$(basename "$dir")"
  case "$name" in
    *.wip|__pycache__) continue ;;
  esac
  files=$(find "$dir" -maxdepth 1 -name '*.py' ! -name '*wip*' 2>/dev/null | wc -l)
  [ "$files" -gt 0 ] || continue
  mkdir -p "$DST/display/$name"
  find "$dir" -maxdepth 1 -name '*.py' ! -name '*wip*' -exec cp {} "$DST/display/$name/" \;
  count_display=$((count_display + 1))
done

# --- touch drivers: one file each ---
count_touch=0
for file in "$SRC"/indev/*.py; do
  name="$(basename "$file")"
  case "$name" in
    *wip*) continue ;;
  esac
  cp "$file" "$DST/indev/$name"
  count_touch=$((count_touch + 1))
done

# --- our patched drivers win ---
echo "== eigene gepatchte Treiber uebernehmen"
[ -f "$PATCHED/axs15231b.py" ] && cp "$PATCHED/axs15231b.py" "$DST/display/axs15231b/"
[ -f "$PATCHED/axs15231b_chunked.py" ] && cp "$PATCHED/axs15231b_chunked.py" "$DST/display/axs15231b/"
[ -f "$PATCHED/axs15231.py" ] && cp "$PATCHED/axs15231.py" "$DST/indev/"

echo "== Ergebnis: $count_display Anzeige-, $count_touch Touch-Treiber"
echo "   Display: $(ls "$DST/display" | tr '\n' ' ')"
echo "   Touch:   $(ls "$DST/indev" | sed 's/\.py$//' | tr '\n' ' ')"
du -sh "$DST"
echo "Hinweis: auf das Board bringen mit tools/deploy.sh drv (alles) oder drv-one <name>."
