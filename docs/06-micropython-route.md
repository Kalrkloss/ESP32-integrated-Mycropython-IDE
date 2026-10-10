# Weg C: MicroPython + LVGL als Basis für ein „Annex-ähnliches" System

Frage: Wie viel Aufwand ist es, auf Basis von MicroPython + LVGL eine Firmware mit
Webserver, WebREPL, Web-Editor und Config-Page für verschiedene Boards und
Custom-Display-/Pin-Konfiguration zu bauen?

Kurz: deutlich weniger als ein eigener BASIC-Interpreter, weil ein großer Teil des
Systems schon existiert. Aufwändig bleiben genau die Teile, die Annex auch selbst
gebaut hat: Web-Editor-UI, Config-UI, Board-/Display-Matrix und der USB-Audio-Treiber.

Stand der geprüften Bausteine: 2026-10-10.

## Was MicroPython mitbringt (kein Aufwand)

| Baustein | Quelle | Anmerkung |
|---|---|---|
| REPL über UART **und** native USB | esp32-Port | auf dem S3 als USB-Serial-JTAG-Konsole |
| WebREPL (REPL im Browser + Dateitransfer) | `webrepl`-Modul, im Standard-Build | `webrepl.html` wird vom Gerät geliefert; Passwortschutz eingebaut |
| Dateisystem, `os`, frozen bytecode, `mip` (Paketmanager) | MicroPython-Kern | Annex hat dafür eigene Datei-/OTA-Logik |
| WLAN, Sockets, TLS, `asyncio`, `_thread` (echte FreeRTOS-Tasks) | MicroPython-Kern | `_thread` ist der Grund, warum „Task einhängen" **hier** funktioniert: wir besitzen den Build |
| Board-System mit Varianten für Flash-Größe/PSRAM | `ports/esp32/boards/*`, `mpconfigboard.cmake`, `pins.csv` | inkl. `ESP32_GENERIC_S3` mit `SPIRAM_OCT` |
| LVGL-Bindings + Display-Treiber | <https://github.com/lvgl/lv_micropython> | `lvgl`-Modul in Python, `lcd_bus`, `task_handler` |
| Lizenzen | MicroPython MIT, LVGL MIT, Microdot MIT, ViperIDE MIT, Espressif-Komponenten Apache-2.0 | kein Lizenzproblem — anders als bei Annex |

Aufwand für das Skelett auf dem S3: **unter einem Tag** (IDF v5.5.5 + MicroPython,
`make BOARD=ESP32_GENERIC_S3 BOARD_VARIANT=SPIRAM_OCT`).

## Was man selbst bauen muss (Schätzung, Vollzeit, eine Person)

| Baustein | Aufwand | Anmerkung |
|---|---|---|
| Webserver + Config-Page (WLAN-Scan/Connect, Pin-Belegung, Modul-/Panel-Auswahl, Neustart, Safe-Mode); Config als JSON in Flash | 3–6 Tage | [Microdot](https://github.com/miguelgrinberg/microdot) (Flask-artig, async, MIT) deckt Routing, WebSocket und Auth ab |
| Web-Editor | 1–3 Tage mit [ViperIDE](https://github.com/vshymanskyy/ViperIDE) (MIT, verbindet sich per WebREPL/USB, Dateimanager + Paketmanager + Terminal); selbst gebaut: 7–12 Tage | der Editor ist der größte Einzelposten, wenn man ihn selbst schreibt |
| LVGL-Build + erstes Display (SPI-TFT + Touch), Speicher-Tuning | 3–7 Tage | PSRAM praktisch Pflicht |
| jede weitere Board-Variante | 0,5–2 Tage je Definition | Pins, `sdkconfig`, Flash-/PSRAM-Variante, Deploy-Anleitung |
| RGB-/Parallel-Panels, weitere Panel-Typen | 3–8 Tage je Panel-Typ | Panel-Timings, `esp_lcd`, PSRAM-Anbindung |
| Laufzeit-Konfiguration von Displays (ein Image für viele Panels) | 5–10 Tage | Panel-Timings und Bus als Daten statt Compile-Zeit-Konstante — Annex macht das **nicht**, dort wird pro Modul eine eigene Firmware geflasht |
| **USB-Audio (UAC-Host) als C-Modul** | 4–8 Tage | eigenes Modul um `espressif/usb_host_uac`: Ringpuffer, Task, I2S-/DAC-Ausgang, Python-API `uac.play()`/`uac.rec()` |
| OTA, Recovery, Release-Verpackung, Doku | 3–6 Tage | |
| **Summe bis „nutzbar"** (1 Board, 1 Display, 1 Soundkarte) | **4–7 Wochen** | |
| Zusätzlich für die Variantenvielfalt à la Annex | + Wochen, überwiegend Panel-/Board-Arbeit | Annex' Matrix ist über Jahre entstanden |

Die Zahlen sind Erfahrungswerte für Arbeitsumfang, keine gemessenen Werte. Sie enthalten
keine Hardware-Iterationen (Board-Revisionen, Timing-Probleme) — die kosten bei Displays
erfahrungsgemäß am meisten.

## Vergleich der Wege

| | Weg B: eigener BASIC-Interpreter | Weg C: MicroPython + LVGL |
|---|---|---|
| Interpreter/REPL/FS/Treiber | selbst schreiben (Wochen) | vorhanden |
| Sprache für Nutzerprogramme | BASIC (Annex-Programme laufen) | Python (Annex-Programme laufen **nicht**) |
| Web-Editor | selbst bauen | ViperIDE vorhanden |
| LVGL | C, direkt, schnell | über Bindings, langsamer |
| RAM-Bedarf | geringer | höher (PSRAM nötig) |
| USB-Audio | selbst schreiben | selbst schreiben (gleicher Aufwand) |
| Fazit | mehr Arbeit, volle Kontrolle, Annex-Nähe | weniger Arbeit, Python-Ökosystem, träger bei GUIs |

## Fallstricke

1. **PHY-Sharing auf dem S3.** USB-OTG und USB-Serial-JTAG teilen sich einen PHY: solange
   USB-Host läuft (also die Soundkarte), ist USB-Debug/Flash weg. Debug dann über UART,
   oder eine externe PHY (SP5301 / TUSB1106) nach Datenblatt. Direkt relevant für das
   USB-Audio-Ziel.
2. **PSRAM ist Pflicht** für LVGL + Webserver + TLS. S3 mit 8 MB PSRAM einplanen.
3. **Performance:** LVGL über Python-Bindings ist spürbar langsamer als Annes C-Pfad;
   für aufwändige GUIs ein Kompromiss.
4. **WebREPL ist unverschlüsselt** (`ws`, Passwortschutz vorhanden) — nur im LAN betreiben,
   nicht ins Internet stellen. Annex' Web-UI hat hier eigene Auth-Logik.
5. **Firmware-Größe** mit LVGL: ~4 MB, also 16-MB-Flash-Modul.
6. **Fremde Firmware nachträglich ändern** bleibt unmöglich — dieser Weg liefert eine
   *eigene* Firmware. Der Vorteil gegenüber Annex: hier darf man C-Module einhängen.

## Empfohlene Meilensteine

- **M1** MicroPython für `ESP32_GENERIC_S3`/`SPIRAM_OCT` bauen, flashen, WebREPL im
  Browser öffnen und eine Datei übertragen. (verifizierbar an einem Tag)
- **M2** Config-Page mit Microdot: WLAN, Pins, Modul-/Panel-Auswahl, Config in Flash.
- **M3** ViperIDE über WebREPL als Editor benutzen (kein eigener Editor nötig).
- **M4** LVGL auf einem TFT (SPI + Touch), PSRAM-Tuning.
- **M5** USB-Audio-C-Modul (`usb_host_uac`) + Python-API + I2S-/DAC-Ausgabe.
- **M6** OTA, Recovery, Release-Pakete, Doku.
