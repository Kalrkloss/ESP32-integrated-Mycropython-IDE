# 11 -- Weboberflaeche (Konsole, Editor, Dateimanager, Konfiguration)

Erreichbar unter `http://<board-ip>/`. Reines HTML/CSS/JS, das **vom Board selbst**
ausgeliefert wird -- der Browser laedt nichts aus dem Internet, die Oberflaeche
funktioniert also auch in einem Netz ohne Internetzugang.

| Reiter | Inhalt |
|---|---|
| **Konsole** | REPL-Ersatz: Python-Zeilen ausfuehren, Ausgabe und Geraetelog ansehen, Bildvorschau, Board neu starten |
| **Editor** | Dateien oeffnen/aendern/speichern/ausfuehren (CodeMirror mit Python-Hervorhebung, Zeilennummern, Suche) |
| **Dateien** | Verzeichnisse durchsuchen, hoch- und herunterladen, umbenennen, loeschen, neue Dateien/Ordner, freier Speicher |
| **Konfiguration** | WLAN (SSID/Passwort), Hostname, Helligkeit, Hintergrundlicht, Geraeteinfo |

## API (JSON, auch mit curl nutzbar)

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/` , `/ui` | Oberflaeche |
| GET | `/app.js`, `/app.css` | Bedienlogik und Stil |
| GET | `/editor/*` | mitgelieferter Codeeditor (Praefix-Route) |
| GET | `/api/state` | IP, Heap, Laufzeit, Dateisystem, Bildquelle |
| POST | `/api/exec` | Python ausfuehren (`{"code": "..."}` oder reiner Text) |
| GET | `/api/log` | Konsole/Logring (`?clear=1` leert) |
| GET | `/api/files?path=/` | Verzeichnis auflisten |
| GET | `/api/file?path=...` | Datei lesen (`?download=1` als Anhang) |
| POST | `/api/file?path=...` | Datei schreiben (Body = Inhalt) |
| DELETE | `/api/file` | Datei/Ordner loeschen (`{"path": "..."}`) |
| POST | `/api/mkdir`, `/api/rename` | Ordner anlegen, umbenennen |
| GET/POST | `/api/config` | Konfiguration lesen/schreiben |
| GET | `/api/screen.png` , `/screen.raw` | Bildschirm als PNG / Rohpuffer |
| POST | `/api/reset` | Board neu starten |
| GET | `/status` | Klartext-Status (Tools, Bildquelle) fuer den schnellen Blick |

## Aufbau

* **Dateien statt eingebetteter Seite:** HTML, CSS und JS liegen in
  `firmware/webfiles/` und auf dem Geraet unter `/web/`. Grund: in einem
  Python-String werden aus `\n` in JS-Zeichenketten echte Zeilenumbrueche -- die
  erste Fassung scheiterte genau daran, das ganze Skript wurde nicht mehr geparst
  und die Seite blieb ohne Funktion. Nebeneffekt: die Dateien sind im
  Dateimanager editierbar. Der Host-Test prueft die JS-Syntax deshalb mit
  `node --check`.
* **Kein CDN:** Der Editor (CodeMirror 5.65.16, MIT) liegt mit allen noetigen
  Addons in `firmware/webfiles/editor/`. Fehlt er auf dem Geraet, faellt die
  Oberflaeche auf ein einfaches Textfeld zurueck.
* **Praefix-Routen:** Routen mit `*` am Ende (`GET /editor/*`) liefern ganze
  Dateibaeume aus; der Pfad wird streng geprueft (nur `<WEB_DIR>/editor`, kein `..`).
* **Gestueckte Auslieferung:** `Response(..., datei=pfad)` sendet grosse Dateien in
  2-KB-Stuecken. Eine 174-KB-Datei am Stueck in den Speicher zu holen war der
  Ausloeser dafuer, dass die Annahmeschleife des Servers starb (das Board
  antwortete danach auf ping, aber nichts lauschte mehr auf Port 80).
* **Aufsicht ueber die Annahmeschleife:** `mcp_serve._aufsicht` startet den
  Listener neu, falls er doch einmal ausfaellt, und schreibt den Grund in den
  Logring. Fehler in Handlern landen ebenfalls im Log (`HTTP-Fehler: ...`).

## Bildvorschau: Rohpuffer statt PNG

Ein LVGL-Snapshot mit PNG-Kodierung in reinem Python kostet auf diesem Board
**3 bis 22 Sekunden** (Massstab 2 laeuft in die Zeitueberschreitung). Deshalb:

* `main.py` meldet nach dem Display-Start dessen **Framebuffer** an
  (`mcp_screen.attach_framebuffer()`). Abzuege lesen dann direkt daraus, ohne
  LVGL-Snapshot. Messwerte: Massstab 1 = 0,45 s, Massstab 4 = 1,2 s.
* Die Oberflaeche holt den **Rohpuffer** (`/screen.raw?scale=4`) und rechnet ihn
  im Browser in ein Bild um (Canvas, RGB565 → RGBA). Auf dem Board entfaellt damit
  jede Kodierung.

## Konfiguration

`config.json` auf dem Geraet (`ssid`, `password`, `hostname`, `brightness`,
`backlight`). `boot.py` liest zuerst `config.json` und fuellt leere Felder aus dem
Altbestand `wifi.json` -- beide Stellen nutzen dieselbe Regel, damit die
Oberflaeche und der Startvorgang dieselbe wirksame Konfiguration sehen.

* Das **Passwort wird nie an den Browser zurueckgegeben**; die Seite zeigt nur, ob
  eines hinterlegt ist. Ein leeres Feld bedeutet "bestehendes behalten".
* WLAN und Hostname greifen nach einem Neustart, die Helligkeit laesst sich sofort
  anwenden (die Seite ruft dafuer `/api/exec` auf).

## Sicherheit

**Keine Authentifizierung.** Die Oberflaeche kann beliebigen Code auf dem Board
ausfuehren und Dateien schreiben -- sie gehoert in ein vertrauenswuerdiges,
abgeschottetes Netz. Wer das nicht will, muss den Port sperren (oder den
Debug-Server aus `main.py` entfernen).

## Testen und Ausrollen

```bash
python3 tests/test_webui.py     # 139 Pruefungen ohne Hardware (Seite, API, HTTP, Editor)
python3 tests/test_boot.py      # Zugangsdaten-Zusammenfuehrung
python3 tests/test_mcpsrv.py    # Server-Kern (Regression)

./tools/deploy.sh all           # Module, Treiber, Webdateien, main.py, boot.py
./tools/deploy.sh web           # nur die Weboberflaeche
```
