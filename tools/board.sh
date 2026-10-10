#!/bin/bash
# Board-Ansprache fuer den JC3248W535 (Debug-Board).
# WICHTIG: Der Zigbee-Stick (Z2M, Adapter zboss) darf NICHT angefasst werden --
# die Port-Aufloesung schliesst ihn explizit aus (tools/_board_port.sh).

set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=_board_port.sh
. "$REPO/tools/_board_port.sh"

die() { echo "FEHLER: $*" >&2; exit 1; }

PORT="$(resolve_board_port)" || die "Board nicht gefunden (Dock-Port $BOARD_USB_PORT). Angeschlossen?"
warn_zigbee

case "${1:-help}" in
  port)
    echo "$PORT"
    ;;
  info)
    "$ESPTOOL_PY" --chip esp32s3 --port "$PORT" flash_id
    ;;
  reset)
    echo "Power-Cycle Dock-Port $DOCK_HUB Port $DOCK_PORT"
    uhubctl -l "$DOCK_HUB" -p "$DOCK_PORT" -a cycle -d 2
    ;;
  boot)
    # Bootmeldungen von der Konsole mitlesen (kurz, dann aufraeumen)
    timeout 8 cat "$PORT" 2>/dev/null | tr -d '\r' | tail -30 || true
    ;;
  flash)
    [ -n "${2:-}" ] || die "Aufruf: $0 flash <firmware.bin>"
    [ -f "$2" ] || die "Datei nicht gefunden: $2"
    "$ESPTOOL_PY" --chip esp32s3 --port "$PORT" -b 460800 \
      --before default_reset --after hard_reset write_flash \
      --flash_mode dio --flash_size 16MB --flash_freq 80m --erase-all \
      0x0 "$2"
    ;;
  erase)
    "$ESPTOOL_PY" --chip esp32s3 --port "$PORT" erase_flash
    ;;
  *)
    cat <<EOF
Aufruf: $0 {port|info|reset|boot|flash <firmware.bin>|erase}

  port     ermittelten seriellen Port ausgeben
  info     Chip/Flash des Boards abfragen
  reset    Board per uhubctl power-cyceln (Dock-Port $DOCK_HUB.$DOCK_PORT)
  boot     Bootmeldungen von der seriellen Konsole mitlesen
  flash    Firmware ab 0x0 schreiben (16 MB, dio, 80 MHz, mit --erase-all)
  erase    Flash loeschen

Zigbee-Stick wird nie verwendet (Serie $ZIGBEE_SERIAL_MATCH).
EOF
    ;;
esac
