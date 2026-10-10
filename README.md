# ESP32-S3 BASIC-Firmware mit USB-Audio (UAC)

Ziel: Auf einem ESP32-S3 soll eine USB-Soundkarte (USB-Audio-Class-Gerät) nutzbar sein —
ansteuerbar aus BASIC heraus, im Stil der Annex-RDS-Kommandos (`SOUND.*`, `PLAY.*`).

Dieses Repository enthält den **eigenen, compilierbaren Quellcode** dafür (ESP-IDF-Projekt).
Es enthält **keinen** Code und keine Artefakte aus der Annex-Firmware.

## Warum ein eigenes Projekt und kein umgebautes Annex

Annex RDS (cicciocb) ist **nicht** Open Source, und die Lizenz verbietet ausdrücklich
Reverse Engineering, Dekompilieren und Disassemblieren der Firmware-Binaries. Aus dem
fertigen Binary lässt sich zudem kein rück-compilierbares Projekt gewinnen.

Details, Belege und Quellen: [docs/01-ausgangslage.md](docs/01-ausgangslage.md)

## Weg

Empfohlener Weg: eigenes ESP-IDF-Projekt
= BASIC-Interpreter (Open-Source-Basis) + UAC-Host-Treiber + I2S-Ausgang.

- Bausteine und Bewertung der Optionen: [docs/02-plan.md](docs/02-plan.md)
- Vorgesehene BASIC-Kommandos: [docs/03-command-surface.md](docs/03-command-surface.md)
- Warum man keine Task „in Annex einhängen" kann:
  [docs/04-einhaengen-in-fremde-firmware.md](docs/04-einhaengen-in-fremde-firmware.md)
- Fertiger Feature-Request an den Autor, falls Weg A gewählt wird:
  [docs/05-feature-request-cicciocb.md](docs/05-feature-request-cicciocb.md)
- Weg C: MicroPython + LVGL als Basis (Aufwandsschätzung, Bausteine, Fallstricke):
  [docs/06-micropython-route.md](docs/06-micropython-route.md)

## Wege

| Weg | Was | Status |
|---|---|---|
| A | Der Autor (cicciocb) baut UAC-Host in Annex ein — er hat Quellcode, Task-Ebene, Kommandotabelle; der USB-Host-Stack ist im S3-Build schon drin | Feature-Request-Text liegt bereit |
| B | Eigene ESP-IDF-Firmware mit eigenem BASIC-Kern | Plan steht, Code offen |
| C | Eigene MicroPython+LVGL-Firmware (Webserver, WebREPL, Web-Editor, Config-Page) | Aufwand geschätzt, favorisiert |

„USB-Audio-Support in eine fremde Firmware einhängen" ist nicht möglich — Begründung in
[docs/04-einhaengen-in-fremde-firmware.md](docs/04-einhaengen-in-fremde-firmware.md).

## Status

- [x] Machbarkeits-Analyse (REA/Ghidra gegen die Annahme „Annex-Quellcode rekonstruieren")
- [x] Analyse „FreeRTOS-Task in eine fremde Firmware einhängen"
- [ ] Auswahl der BASIC-Basis und Aufsetzen des ESP-IDF-Projekts
- [ ] UAC-Host-Treiber anbinden (`espressif/usb_host_uac`)
- [ ] I2S-Ausgang / Lautsprecherpfad
- [ ] BASIC-Kommandos + Beispielprogramme
- [ ] Test auf ESP32-S3-Hardware

## Build

ESP-IDF (v5.x), Ziel `esp32s3`. Wird hier ergänzt, sobald das Projektgerüst steht.

## Lizenz

MIT (siehe [LICENSE](LICENSE)). Gilt nur für den Inhalt dieses Repositories.
