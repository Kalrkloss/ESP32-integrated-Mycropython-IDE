# Vorgesehene BASIC-Kommandos

Angelehnt an die Namensgebung der Annex-RDS-Firmware (`SOUND.*`, `PLAY.*`), damit
bestehende Programme leicht portierbar sind. Punktnamen wie in Annex üblich; alle
Kommandos blockieren nicht und liefern einen Rückgabecode.

## Gerät & Status

| Kommando | Bedeutung |
|---|---|
| `USB.SOUND.INIT [rate]` | USB-Host-Stack + UAC-Treiber starten; optional Abtastrate (z. B. 48000) |
| `USB.SOUND.DEVICE$` | Beschreibung der erkannten Soundkarte (Hersteller/Produkt), leer wenn keine |
| `USB.SOUND.STATE` | 0 = gestoppt, 1 = bereit, 2 = läuft, negativ = Fehler |
| `USB.SOUND.FORMAT` | aktive Rate/Bit/Kanäle (z. B. 48000/16/2) |
| `USB.SOUND.CLOSE` | Gerät schließen, USB-Host stoppen |

## Wiedergabe

| Kommando | Bedeutung |
|---|---|
| `USB.SOUND.VOLUME v` | Lautstärke 0–100 (an die Soundkarte gemeldet, falls Feature-Unit vorhanden) |
| `USB.SOUND.MUTE on` | Stummschalten |
| `PLAY.USB file$ [,rate]` | Datei (WAV/MP3/PCM) über die USB-Soundkarte ausgeben |
| `PLAY.STREAM_USB url$` | Stream über die USB-Soundkarte ausgeben |
| `USB.SOUND.TONE freq, ms [,vol]` | Testton — erstes Prüfkommando für Aufbau und Verkabelung |
| `USB.SOUND.WRITE iobuf$` | rohes PCM aus dem IO-Puffer senden |

## Aufnahme

| Kommando | Bedeutung |
|---|---|
| `USB.SOUND.MIC.LEVEL` | aktueller Eingangspegel (0–100) |
| `USB.SOUND.REC file$ [,seconds]` | Mikrofon der Soundkarte in Datei aufnehmen (WAV) |
| `USB.SOUND.READ iobuf$` | rohes PCM in den IO-Puffer lesen |

## Ereignisse

| Kommando | Bedeutung |
|---|---|
| `USB.SOUND.ONERROR label$` | Sprungziel bei Hotplug/Fehler (Gerät entfernt, Format nicht unterstützt) |

## Nicht geplant (Gegenrichtung)

Wenn die S3 selbst als USB-Soundkarte am PC erscheinen soll, wäre das eine eigene
Kommandofamilie (z. B. `USB.DEVICE.INIT`), umgesetzt mit dem TinyUSB-Device-Stack
(`esp_device_uac`) statt mit dem Host-Treiber.
