# Plan

## Zielbild

Ein ESP-IDF-Projekt für den ESP32-S3, das

1. eine USB-Soundkarte über den OTG-Port als Host anspricht (UAC),
2. die Audio-Daten über I2S an einen DAC/Lautsprecher bzw. von einem Mikrofon wegleitet,
3. diese Fähigkeit über BASIC-Kommandos zugänglich macht (`USB.SOUND.*`, siehe
   [03-command-surface.md](03-command-surface.md)),
4. sich auf echter Hardware flashen und testen lässt.

## Annahme

„Support für USB-Soundkarten" heißt: die **S3 ist USB-Host** und spricht eine
angeschlossene USB-Soundkarte an (Wiedergabe, optional Aufnahme über das Mikrofon der
Soundkarte). Die Gegenrichtung (S3 erscheint selbst als Soundkarte am PC) ist technisch
ebenfalls machbar, aber ein anderes Feature — siehe Abschnitt 4.2 in der Ausgangslage.

## Etappen

### E1 — Projektgerüst
- ESP-IDF v5.x, Target `esp32s3`, Partitionstabelle mit Platz für App + Dateisystem.
- Konsolenausgabe über USB-Serial-JTAG (Debug) und Konsole über UART.
- Nachweis: `idf.py build` läuft, Gerät bootet, Konsolenprompt erscheint.

### E2 — UAC-Host
- `espressif/usb_host_uac` als Abhängigkeit, Geräte-Erkennung, Format-Aushandlung,
  Fehler-/Hotplug-Behandlung.
- Nachweis: Log zeigt erkannte Soundkarte mit Rate/Kanälen/Bitbreite.

### E3 — Audiopfad
- Wiedergabe: Datei/Stream → Ringpuffer → `uac_host_device_write` (Lautsprecher der Soundkarte).
- Alternative Ausgabe: UAC → I2S → DAC (für den Fall, dass die Soundkarte nur Eingang hat).
- Aufnahme: `uac_host_device_read` → Puffer/Datei.
- Nachweis: Testton über die USB-Soundkarte hörbar; Aufnahme in einer Datei nachweisbar.

### E4 — BASIC-Anbindung
- BASIC-Basis einbinden (Empfehlung: my_basic, MIT — zwei C-Dateien, erweiterbar über
  native Funktionen).
- Native Kommandos `USB.SOUND.*` registrieren, Fehler als BASIC-Fehler zurückgeben.
- Nachweis: BASIC-Programm startet Wiedergabe und setzt die Lautstärke.

### E5 — Test & Doku
- Testskripte, Beispielprogramme, Kommando-Referenz, Aufbauanleitung (Verkabelung,
  Stromversorgung des Host-Ports — bei vielen S3-Boards muss 5 V für den Host-Port
  erst per Lötbrücke/Jumper freigegeben werden).

## Randbedingungen

- ESP32-S3-OTG ist Full-Speed: realistisch 44,1/48 kHz, 16 Bit, 1–2 Kanäle.
- Der OTG-Port wird gleichzeitig für Konsole/Flash genutzt — Stromversorgung und
  Pinbelegung vorher klären, sonst ist ein Debugging per USB-Serial-JTAG während
  des Host-Betriebs nicht möglich.
- Kein Code aus der Annex-Firmware, keine Binaries Dritter im Repository.

## Entscheidungen, die noch offen sind

1. BASIC-Basis (my_basic vs. tinybasic vs. BasicPlus vs. eigener Mini-Interpreter).
2. Richtung: Host (Soundkarte an der S3) — oder zusätzlich Device (S3 als Soundkarte).
3. Zielboard/Testhardware und die konkret vorhandene USB-Soundkarte.
