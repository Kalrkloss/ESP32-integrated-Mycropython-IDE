#!/bin/bash
# Debug-Server + App auf das Board kopieren (mpremote ueber die native USB-Verbindung).
# Port-Aufloesung wie in board.sh: Dock-Port primaer, Zigbee-Stick ausgeschlossen.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=_board_port.sh
. "$REPO/tools/_board_port.sh"

MPY="${MPY:-/opt/esp-tools/bin/python3}"

die() { echo "FEHLER: $*" >&2; exit 1; }
PORT="$(resolve_board_port)" || die "Board nicht gefunden (Dock-Port $BOARD_USB_PORT)"
warn_zigbee
[ -x "$MPY" ] || die "$MPY fehlt (venv mit mpremote anlegen)"

mp() { "$MPY" -m mpremote connect "$PORT" "$@"; }

# Nach einem Reset verschwindet der USB-Port kurz (native USB-Verbindung) und kommt
# erst wieder, wenn der Boot durch ist. Blind zu warten ist unzuverlaessig --
# deshalb aktiv probieren, bis der Interpreter antwortet.
mp_wait_ready() {
  local tries="${1:-40}"
  for _ in $(seq 1 "$tries"); do
    if [ -e "$PORT" ] && "$MPY" -m mpremote connect "$PORT" eval "1" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.5
  done
  return 1
}

case "${1:-all}" in
  mods)
    echo "== Server-Module =="
    mp fs cp "$REPO"/firmware/mcpsrv/mcp_*.py :
    echo "== Treiber =="
    mp fs cp "$REPO"/firmware/device/drivers/*.py :
    ;;
  all|code)
    echo "== Server-Module =="
    mp fs cp "$REPO"/firmware/mcpsrv/mcp_*.py :
    echo "== Treiber =="
    mp fs cp "$REPO"/firmware/device/drivers/*.py :
    echo "== App =="
    mp fs cp "$REPO"/firmware/device/main.py :
    if [ -f "$REPO"/firmware/device/wifi.json ]; then
      mp fs cp "$REPO"/firmware/device/wifi.json :
    else
      echo "Hinweis: firmware/device/wifi.json fehlt -- Board kommt ohne WLAN hoch." >&2
    fi
    echo "== boot.py (zuletzt: aktiv ab dem naechsten Reset) =="
    mp fs cp "$REPO"/firmware/device/boot.py :
    ;;
  test)
    echo "== Bring-up-Test auf dem Board =="
    mp fs cp "$REPO"/firmware/device/test_screen.py :
    mp run "$REPO"/firmware/device/test_screen.py
    ;;
  lib)
    # Eigene (gepatchte) Treiber aus dem Repo -- Dateisystem ueberdeckt eingefrorene Module
    mp fs cp "$REPO"/firmware/device/drivers/*.py :
    ;;
  ls)
    mp fs ls
    ;;
  rm)
    [ -n "${2:-}" ] || die "Aufruf: $0 rm <datei>"
    mp fs rm ":$2"
    ;;
  reset)
    mp reset
    ;;
  run)
    [ -n "${2:-}" ] || die "Aufruf: $0 run <datei.py>"
    # Wichtig: vor jedem Lauf neu starten. Ein Skript, das den SPI-Bus (host=1)
    # initialisiert, laesst ihn C-seitig offen zurueck -- der naechste Aufruf von
    # machine.SPI.Bus(host=1) scheitert dann und reisst den Interpreter mit.
    mp reset >/dev/null 2>&1 || true
    mp_wait_ready || die "Board antwortet nach dem Reset nicht"
    exec "$MPY" -m mpremote connect "$PORT" run "$2"
    ;;
  exec)
    [ -n "${2:-}" ] || die "Aufruf: $0 exec <python>"
    exec "$MPY" -m mpremote connect "$PORT" exec "$2"
    ;;
  repl)
    exec "$MPY" -m mpremote connect "$PORT" repl
    ;;
  *)
    cat <<EOF
Aufruf: $0 {mods|all|test|lib|ls|rm <datei>|reset|run <datei.py>|exec <python>|repl}

  mods    Server-Module + Treiber kopieren (fuer den Bring-up, ohne main.py)
  all     wie mods, zusaetzlich main.py, wifi.json und boot.py
  test    test_screen.py hochladen und auf dem Board ausfuehren (Panel-Bring-up)
  lib     nur die eigenen Treiber kopieren
  ls      Dateien auf dem Board auflisten
  rm      Datei auf dem Board loeschen
  reset   Board neu starten
  run     lokale Datei auf dem Board ausfuehren (mit Reset davor)
  exec    Python auf dem Board ausfuehren
  repl    interaktive REPL
EOF
    ;;
esac
