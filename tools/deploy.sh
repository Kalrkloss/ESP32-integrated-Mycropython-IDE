#!/bin/bash
# Debug-Server + App auf das Board kopieren (mpremote ueber die native USB-Verbindung).
# Verwendet ausschliesslich den by-id-Pfad des Boards -- der Zigbee-Stick bleibt unberuehrt.
set -euo pipefail

BOARD_ID="/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_98:3D:AE:E9:18:10-if00"
ZIGBEE_ID="/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_F0:F5:BD:03:09:5C-if00"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
MPY="${MPY:-/opt/esp-tools/bin/python3}"

die() { echo "FEHLER: $*" >&2; exit 1; }
[ -e "$BOARD_ID" ] || die "Board nicht gefunden ($BOARD_ID)"
[ -e "$ZIGBEE_ID" ] && echo "Zigbee-Stick vorhanden -- wird nicht benutzt." >&2
[ -x "$MPY" ] || die "$MPY fehlt (venv mit mpremote anlegen)"

MPREMOTE="$MPY -m mpremote connect $BOARD_ID"

run() { echo "+ $*"; "$@"; }

case "${1:-all}" in
  all|code)
    echo "== Server-Module =="
    $MPREMOTE fs cp "$REPO"/firmware/mcpsrv/mcp_*.py :
    echo "== App =="
    $MPREMOTE fs cp "$REPO"/firmware/device/boot.py "$REPO"/firmware/device/main.py :
    if [ -f "$REPO"/firmware/device/wifi.json ]; then
      $MPREMOTE fs cp "$REPO"/firmware/device/wifi.json :
    else
      echo "Hinweis: firmware/device/wifi.json fehlt -- Board kommt ohne WLAN hoch." >&2
    fi
    ;;
  lib)
    # Treiber/Configs des Boards (aus dem Binding-Build des lvgl_micropython-Checkouts)
    SRC="${LVGL_SRC:-/opt/lvgl_micropython}"
    [ -d "$SRC/api_drivers/common_api_drivers/display/axs15231b" ] || die "Treiber nicht gefunden in $SRC"
    $MPREMOTE fs cp "$SRC"/api_drivers/common_api_drivers/display/axs15231b/axs15231b.py :
    $MPREMOTE fs cp "$SRC"/api_drivers/common_api_drivers/display/axs15231b/_axs15231b_init.py :
    $MPREMOTE fs cp "$SRC"/api_drivers/common_api_drivers/indev/axs15231.py :
    ;;
  ls)
    $MPREMOTE fs ls
    ;;
  repl)
    exec $MPREMOTE repl
    ;;
  reset)
    $MPREMOTE reset
    ;;
  run)
    # $2 = Skript auf dem Board ausfuehren
    [ -n "${2:-}" ] || die "Aufruf: $0 run <datei.py>"
    exec $MPREMOTE run "$2"
    ;;
  *)
    cat <<EOF
Aufruf: $0 {all|lib|ls|repl|reset|run <datei.py>}

  all    Server-Module + boot.py/main.py (+ wifi.json, falls vorhanden) kopieren
  lib    Display-/Touch-Treiber des Boards kopieren (axs15231b, axs15231)
  ls     Dateien auf dem Board auflisten
  repl   interaktive REPL ueber USB
  reset  Board neu starten
  run    Skript auf dem Board ausfuehren
EOF
    ;;
esac
