# Wird von board.sh und deploy.sh eingebunden: ermittelt den seriellen Port des
# Debug-Boards -- NIE den Zigbee-Stick.
#
# Warum nicht einfach /dev/ttyACM1?
#   * Die by-id-Namen aendern sich mit der laufenden Firmware (Werksimage:
#     "USB JTAG/serial debug unit", MicroPython: "Espressif Device").
#   * /dev/ttyACM* wird in Reihenfolge der Erkennung vergeben -- nicht stabil.
# Deshalb: primaer der USB-Pfad (Dock-Port), sonst by-id mit Zigbee-Ausschluss.

ZIGBEE_SERIAL_MATCH="F0:F5:BD:03:09:5C"
BOARD_USB_PATH="/dev/serial/by-path/pci-0000:00:15.0-usb-0:4.4.3:1.0"
BOARD_USB_PORT="1-4.4.3"
DOCK_HUB="1-4.4"
DOCK_PORT="3"
ESPTOOL_PY="${ESPTOOL_PY:-/root/.espressif/python_env/idf5.5_py3.13_env/bin/esptool.py}"

resolve_board_port() {
  if [ -e "$BOARD_USB_PATH" ]; then
    echo "$BOARD_USB_PATH"
    return 0
  fi
  for p in /dev/serial/by-id/*Espressif*; do
    [ -e "$p" ] || continue
    case "$p" in
      *"$ZIGBEE_SERIAL_MATCH"*) continue ;;
    esac
    echo "$p"
    return 0
  done
  return 1
}

zigbee_present() {
  for p in /dev/serial/by-id/*Espressif*; do
    [ -e "$p" ] || continue
    case "$p" in
      *"$ZIGBEE_SERIAL_MATCH"*) return 0 ;;
    esac
  done
  return 1
}


warn_zigbee() {
  if zigbee_present; then
    echo "Hinweis: Zigbee-Stick ist angeschlossen -- wird nicht beruehrt." >&2
  fi
}
