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
    echo "== Treiber (flach, Altbestand) =="
    mp fs cp "$REPO"/firmware/device/drivers/*.py :
    ;;
  all|code)
    echo "== Server-Module =="
    mp fs cp "$REPO"/firmware/mcpsrv/mcp_*.py :
    echo "== Treiber (flach, Altbestand) =="
    mp fs cp "$REPO"/firmware/device/drivers/*.py :
    echo "== Weboberflaeche =="
    mp fs mkdir :web 2>/dev/null || true
    mp fs cp "$REPO"/firmware/webfiles/index.html "$REPO"/firmware/webfiles/setup.html "$REPO"/firmware/webfiles/app.css "$REPO"/firmware/webfiles/app.js "$REPO"/firmware/webfiles/setup.js :web/
    mp fs cp -r "$REPO"/firmware/webfiles/editor :web/
    echo "== App =="
    mp fs cp "$REPO"/firmware/device/main.py "$REPO"/firmware/device/display_config.py \
              "$REPO"/firmware/device/portal.py "$REPO"/firmware/device/profiles.json :
    if [ -f "$REPO"/firmware/device/wifi.json ]; then
      mp fs cp "$REPO"/firmware/device/wifi.json :
    else
      echo "Hinweis: firmware/device/wifi.json fehlt -- Board kommt ohne WLAN hoch." >&2
    fi
    echo "== Beispiel-Apps =="
    if [ -d "$REPO"/firmware/apps ] && ls "$REPO"/firmware/apps/*.py >/dev/null 2>&1; then
      mp fs mkdir :apps 2>/dev/null || true
      mp fs cp "$REPO"/firmware/apps/*.py :apps/
      [ -f "$REPO"/firmware/device/app_loader.py ] && mp fs cp "$REPO"/firmware/device/app_loader.py :
    else
      echo "Hinweis: firmware/apps fehlt -- keine Beispiel-Apps auf dem Board." >&2
    fi
    echo "== boot.py (zuletzt: aktiv ab dem naechsten Reset) =="
    mp fs cp "$REPO"/firmware/device/boot.py :
    ;;
  drv)
    echo "== Treiber nach /drv (Auswahl zur Laufzeit) =="
    mp fs mkdir :drv 2>/dev/null || true
    mp fs mkdir :drv/display :drv/indev 2>/dev/null || true
    for dir in "$REPO"/firmware/device/drv/display/*/; do
      name="$(basename "$dir")"
      mp fs mkdir ":drv/display/$name" 2>/dev/null || true
      mp fs cp "$dir"*.py ":drv/display/$name/"
      echo "   $name"
    done
    mp fs cp "$REPO"/firmware/device/drv/indev/*.py :drv/indev/
    echo "   Touch-Treiber: $(ls "$REPO"/firmware/device/drv/indev | wc -l)"
    ;;
  drv-one)
    [ -n "${2:-}" ] || die "Aufruf: $0 drv-one <name>"
    name="$2"
    mp fs mkdir :drv 2>/dev/null || true
    mp fs mkdir :drv/display 2>/dev/null || true
    mp fs mkdir :drv/indev 2>/dev/null || true
    if [ -d "$REPO/firmware/device/drv/display/$name" ]; then
      mp fs mkdir ":drv/display/$name" 2>/dev/null || true
      mp fs cp "$REPO"/firmware/device/drv/display/"$name"/*.py ":drv/display/$name/"
      echo "Anzeige-Treiber $name kopiert"
    elif [ -f "$REPO/firmware/device/drv/indev/$name.py" ]; then
      mp fs cp "$REPO"/firmware/device/drv/indev/"$name".py :drv/indev/
      echo "Touch-Treiber $name kopiert"
    else
      die "Treiber $name nicht gefunden"
    fi
    ;;
  apps)
    [ -d "$REPO"/firmware/apps ] || die "firmware/apps fehlt"
    mp fs mkdir :apps 2>/dev/null || true
    mp fs cp "$REPO"/firmware/apps/*.py :apps/
    [ -f "$REPO"/firmware/device/app_loader.py ] && mp fs cp "$REPO"/firmware/device/app_loader.py :
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
  web)
    echo "== Weboberflaeche (HTML/CSS/JS + Editor) =="
    mp fs mkdir :web 2>/dev/null || true
    mp fs cp "$REPO"/firmware/webfiles/index.html "$REPO"/firmware/webfiles/setup.html "$REPO"/firmware/webfiles/app.css "$REPO"/firmware/webfiles/app.js "$REPO"/firmware/webfiles/setup.js :web/
    mp fs cp -r "$REPO"/firmware/webfiles/editor :web/
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
Aufruf: $0 {mods|all|test|lib|web|drv|drv-one <name>|apps|ls|rm <datei>|reset|run <datei.py>|exec <python>|repl}

  mods    Server-Module + Treiber kopieren (fuer den Bring-up, ohne main.py)
  all     wie mods, zusaetzlich Weboberflaeche, main.py, portal.py, profiles.json,
          Beispiel-Apps und boot.py
  web     nur die Weboberflaeche (HTML/CSS/JS + Editor) nach /web kopieren
  drv     alle Treiber nach /drv kopieren (Auswahl zur Laufzeit, ~1 MB)
  drv-one einen einzelnen Treiber nach /drv kopieren
  apps    nur die Beispiel-Apps nach /apps kopieren (plus app_loader.py)
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
