#!/bin/bash
# Board-Ansprache fuer den JC3248W535 (Debug-Board).
# WICHTIG: Der Zigbee-Stick (ttyACM0, ZBOSS) darf NICHT angefasst werden -- Z2M haelt ihn offen.
# Dieses Skript verwendet ausschliesslich den by-id-Pfad des Boards.

set -euo pipefail

BOARD_ID="/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_98:3D:AE:E9:18:10-if00"
ZIGBEE_ID="/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_F0:F5:BD:03:09:5C-if00"
DOCK_HUB="1-4.4"
DOCK_PORT="3"          # Dock-Port des Boards; Port 4 = MAX!-Cube-Nachbarport
ESPTOOL="/root/.espressif/python_env/idf5.5_py3.13_env/bin/esptool.py"

die() { echo "FEHLER: $*" >&2; exit 1; }

[ -e "$BOARD_ID" ] || die "Board nicht gefunden ($BOARD_ID). Ist es am Dock-Port $DOCK_HUB.$DOCK_PORT?"
[ -e "$ZIGBEE_ID" ] && echo "Zigbee-Stick erkannt ($ZIGBEE_ID) -- wird nicht angefasst." >&2

case "${1:-help}" in
  info)
    "$ESPTOOL" --chip esp32s3 --port "$BOARD_ID" flash_id
    ;;
  reset)
    echo "Power-Cycle Dock-Port $DOCK_HUB Port $DOCK_PORT"
    uhubctl -l "$DOCK_HUB" -p "$DOCK_PORT" -a cycle -d 2
    ;;
  flash)
    # $2 = Firmware.bin (gemergtes Image ab 0x0)
    [ -n "${2:-}" ] || die "Aufruf: $0 flash <firmware.bin>"
    [ -f "$2" ] || die "Datei nicht gefunden: $2"
    "$ESPTOOL" --chip esp32s3 --port "$BOARD_ID" -b 460800 \
      --before default_reset --after hard_reset write_flash \
      --flash_mode dio --flash_size 16MB --flash_freq 80m --erase-all \
      0x0 "$2"
    ;;
  erase)
    "$ESPTOOL" --chip esp32s3 --port "$BOARD_ID" erase_flash
    ;;
  monitor)
    exec python3 -m serial.tools.miniterm "$BOARD_ID" 115200
    ;;
  *)
    cat <<EOF
Aufruf: $0 {info|reset|flash <firmware.bin>|erase|monitor}

  info     Chip/Flash des Boards abfragen
  reset    Board per uhubctl power-cyceln (Dock-Port $DOCK_HUB.$DOCK_PORT)
  flash    Firmware ab 0x0 schreiben (16 MB, dio, 80 MHz, mit --erase-all)
  erase    Flash loeschen
  monitor  serieller Monitor (115200)

Board:  $BOARD_ID
Zigbee: $ZIGBEE_ID  (nicht verwenden!)
EOF
    ;;
esac
