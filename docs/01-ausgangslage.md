# Ausgangslage & Machbarkeit

Stand: 2026-10-10

## 1. Was ausgeliefert wird

- Firmware-Download: <https://updates.cicciocb.com/> („ANNEX RDS FIRMWARE UPDATES v9",
  letzte Änderung dort angezeigt: 04.08.2026). Geliefert werden **fertige `.bin`-Dateien**,
  pro Chip, Variante und Flash-Modus.
- Web-Installer: <https://flasher.cicciocb.com/>
- ESP32-S3-Varianten (Auszug aus der Download-Liste): `Annex32-S3_LVGL_HID_OTG_2.99.x_qio_opi.bin`,
  `Annex32-S3_DMT_LVGL_HID_OTG_ATS_2.99.x_qio_opi.bin`, `Annex32-S3_CAN_USB_DMT_HID_OTG_2.00.92_qio_qspi.bin`.
- Beispielgröße: die S3-Datei `Annex32-S3_LVGL_HID_OTG_2.99.07_qio_opi.bin` ist
  **2.871.232 Bytes** (HTTP `content-length`). Das ist ein gemergtes Flash-Image
  (Bootloader + Partitionstabelle + Applikation).
- Relevanz für dieses Projekt: Namen wie `USB`, `HID`, `OTG` zeigen, dass im S3-Build
  **bereits ein USB-Host-Stack** enthalten ist; die Doku führt „USB HID INTERFACE
  (Mouse, Keyboard, Gamepad) – ESP32-S3 only". Für den Autor ist ein UAC-Host-Treiber
  damit ein vergleichsweise kleiner Zusatz.

## 2. Lizenz-Lage (entscheidend)

- FAQ (<https://cicciocb.com/annexwifi/faq.html>):
  > „Q: If Annex is free, where I can find the source codes?
  >  A: Annex is free, but it is not open source, so the source code is not available."
- Copyright (<https://cicciocb.com/annexwifi/copyright.html>):
  > „It is not allowed to reverse engineer, decompile or disassemble the compiled objects
  >  (the .bin and the .exe files) or any attempt to do so."
- Handbuch (<https://cicciocb.com/annex32help/V2.9912/start.htm>): Copyright 2017–2025
  Francesco Ceccarella (ciccioCB). Das **Binär-Abbild** darf für nicht-kommerzielle
  Zwecke weitergegeben werden, der Quellcode ist es nicht.

Konsequenz: Ein aus dem Binary rekonstruierter Quellcode wäre lizenzwidrig, und seine
Veröffentlichung wäre eine Urheberrechtsverletzung. Deshalb wurde in diesem Projekt
**nicht** dekompiliert/disassembliert. Es wurden ausschließlich öffentliche Metadaten
(HTTP-Header, Download-Liste, Doku) verwendet.

## 3. Frage: Lässt sich mit REA ein compilierbarer Quellcode erzeugen?

Werkzeuge auf diesem Host: REA 6.3.0 (`/usr/local/bin/rea`), als Analyse-Provider
Ghidra 12.1.4 (`/opt/ghidra_12.1.4_PUBLIC`) und Hopper 6.4.2 (`/opt/hopper`).
Firmware-Regionen-Extraktion setzt Binwalk/Unblob voraus (hier nicht installiert).

Was REA/Ghidra/Hopper als Ergebnis liefern können:

- pro Funktion **Pseudo-C ohne Typen und ohne Namen**, ohne Struktur-/Header-Definitionen,
- keine Build-Dateien, kein Linker-Skript, keine Memory-Map, kein Partitions-Layout zum Nachbau,
- **keine** der eingebundenen Bibliotheken im Quelltext (ESP-IDF, FreeRTOS, WLAN-Stack, LVGL,
  Annex' I2S-Sound-Engine, Web-UI, Dateisystem),
- keine Kommentare, keine Konfiguration, keine Rebuild-Parameter.

Ein Image dieser Größe enthält mehrere tausend Funktionen. Ein daraus entstehendes
Projekt ist nicht kompilierbar und nicht wartbar; es ist Analysematerial, kein Quelltext.

Hinzu kommt der funktionale Teil: Ein USB-Audio-Host-Treiber greift tief in die Firmware ein
(USB-Host-Library, isochrone Transfers, Ringpuffer, eigene Tasks, Anbindung an die
Audio-Engine). Solche Eingriffe lassen sich nicht sinnvoll in ein fremdes, symbolfreies
Binary patchen — jede Version müsste neu gepatcht werden.

**Ergebnis: Nein.** Aus dem Annex-Binary lässt sich kein compilierbarer Quellcode
erzeugen, in den man USB-Sound einbaut. Plausibel wären lediglich *kleine* Erkenntnisse
über einzelne Funktionen (Analyse-Zwecke), nicht ein erweiterbares Projekt.

## 4. Optionen, die tatsächlich funktionieren

### 4.1 Beim Autor anfragen (kleinster Aufwand)

USB-Host-Stack und OTG sind im S3-Build bereits vorhanden (siehe Abschnitt 1).
Ein UAC-Host-Treiber auf Basis von `espressif/usb_host_uac` wäre für cicciocb eine
überschaubare Erweiterung. Forum: <https://cicciocb.com/forum> — dort gibt es bereits
den Präzedenzfall „USB HID" (S3-only), samt Doku-Eintrag.

### 4.2 Eigenes ESP-IDF-Projekt (dieses Repository)

Bausteine, offiziell von Espressif bzw. aus der Community:

| Zweck | Baustein | Quelle |
|---|---|---|
| USB-Host, Audio-Klasse 1.0 (Lautsprecher + Mikrofon, Vol/Mute) | `espressif/usb_host_uac` | <https://components.espressif.com/components/espressif/usb_host_uac> |
| USB-Host UVC+UAC-Streams (Ringpuffer, Suspend/Resume) | `usb_stream` (esp-iot-solution) | <https://docs.espressif.com/projects/esp-iot-solution/en/latest/usb/usb_host/usb_stream.html> |
| USB-Host, Audio-Klasse 2.0 (ESP32-S3) | `esp-uac2-host` | vorgestellt unter <https://blog.adafruit.com/2026/04/06/a-usb-audio-class-2-0-host-driver-for-esp32-s3/> |
| Gegenrichtung: S3 *ist* die Soundkarte am PC (UAC-Device, TinyUSB) | `esp_device_uac` | <https://docs.espressif.com/projects/esp-iot-solution/en/latest/usb/usb_device/usb_device_uac.html> |
| Gegenrichtung, Arduino-Basis | arduino-audio-tools (UAC2) | <https://www.pschatzmann.ch/home/2026/06/22/usb-audio-class-2-0-for-arduino/> |

Grenzen der Hardware (ESP32-S3): USB-OTG ist **Full-Speed (12 Mbit/s)** und Host und
Gerät teilen sich denselben Port — brauchbare Audioqualität heißt hier 1 Kanal
Mikrofon + 1 Kanal Lautsprecher, 44,1/48 kHz, 16 Bit.

### 4.3 BASIC-Basis (Open Source) für das eigene Projekt

| Projekt | Lizenz | Eignung |
|---|---|---|
| [paladin-t/my_basic](https://github.com/paladin-t/my_basic) | MIT | 2 C-Dateien, < 128 KB, ausdrücklich zum Einbetten/Erweitern gedacht — kleinster Weg zu `SOUND.USB.*` |
| [slviajero/tinybasic](https://github.com/slviajero/tinybasic) | BSD-3 | sehr breite Plattform-Abstraktion, ESP32 bereits unterstützt |
| [legio-e/BasicPlus](https://github.com/legio-e/BasicPlus) | MIT | Bytecode-VM mit Debugger, ESP32-S3/P4-Firmware vorhanden |

Nicht geeignet: **Basic32** (Ferrazzi) — ebenfalls Closed Source, nur Binaries
(<https://github.com/Ferrazzi/Basic32>).

## 5. Offen / nicht geprüft

- Ob cicciocb USB-Audio bereits plant oder ablehnt (nicht recherchiert).
- Ob Annexe eine Erweiterungsschnittstelle für nativen Code hat. Aus Handbuch und
  Downloadliste ergibt sich keine; die dokumentierten Kommandos sind eingebaut.
- Ob real eine UAC-1.0- oder UAC-2.0-Soundkarte vorliegt (hängt vom Testgerät ab).
