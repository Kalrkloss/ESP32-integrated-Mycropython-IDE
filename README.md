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

## Status

- [x] Machbarkeits-Analyse (REA/Ghidra gegen die Annahme „Annex-Quellcode rekonstruieren")
- [ ] Auswahl der BASIC-Basis und Aufsetzen des ESP-IDF-Projekts
- [ ] UAC-Host-Treiber anbinden (`espressif/usb_host_uac`)
- [ ] I2S-Ausgang / Lautsprecherpfad
- [ ] BASIC-Kommandos + Beispielprogramme
- [ ] Test auf ESP32-S3-Hardware

## Build

ESP-IDF (v5.x), Ziel `esp32s3`. Wird hier ergänzt, sobald das Projektgerüst steht.

## Lizenz

MIT (siehe [LICENSE](LICENSE)). Gilt nur für den Inhalt dieses Repositories.
