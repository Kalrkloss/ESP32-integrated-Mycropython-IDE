# Entwurf: Feature-Request an cicciocb (USB-Audio / UAC-Host, ESP32-S3)

Weg A aus [04-einhaengen-in-fremde-firmware.md](04-einhaengen-in-fremde-firmware.md):
statt Reverse Engineering eine Anfrage an den Autor — er hat Quellcode, Task-Ebene und
Kommando-Tabelle, und der USB-Host-Stack ist im S3-Build schon vorhanden.

Ziel-Plattform: <https://cicciocb.com/forum> (Anmeldung als Forum-Mitglied nötig).
Sprache: Englisch (Forumssprache).

## Betreff

`Feature request: USB Audio Class (UAC) host support on ESP32-S3`

## Text (zum Posten)

> Hi Francesco,
>
> first of all: thank you for Annex — the interpreter running directly on the module is
> what makes it useful for me every day.
>
> **What I would like to use:** a USB sound card (USB Audio Class device) plugged into the
> ESP32-S3 OTG port, controlled from BASIC — e.g. playback to the card's headphone output,
> and optionally recording from its microphone input, plus volume/mute.
>
> **Why I think it fits the S3 builds:** the S3 firmware variants already carry the USB
> host stack (`..._HID_OTG_...`) and the help documents the USB HID interface
> (mouse/keyboard/gamepad, S3 only). So the host side is already there.
>
> **What I am asking for:** a UAC host class driver on top of the existing host stack.
> Espressif publishes a ready component for this — `espressif/usb_host_uac`
> (UAC 1.0 host: speaker and microphone streams, volume/mute), and `usb_stream` in
> esp-iot-solution (UVC + UAC with ring buffers) as a fuller alternative.
>
> **Suggested BASIC surface** (naming follows the existing `SOUND.*` / `PLAY.*` style):
>
> - `USB.SOUND.INIT [rate]`, `USB.SOUND.CLOSE`, `USB.SOUND.STATE`
> - `USB.SOUND.DEVICE$`, `USB.SOUND.FORMAT`
> - `USB.SOUND.VOLUME v`, `USB.SOUND.MUTE on`
> - `PLAY.USB file$`, `PLAY.STREAM_USB url$`
> - `USB.SOUND.TONE freq, ms` (simple bring-up test)
> - `USB.SOUND.REC file$ [,seconds]`, `USB.SOUND.MIC.LEVEL`
>
> Even a minimal subset (init, device$, tone, volume) would already make the feature
> usable and testable.
>
> **Hardware limits I am aware of:** the S3 OTG is full speed (12 Mbit/s) and host/device
> share the same port, so 44.1/48 kHz, 16 bit, one to two channels is the realistic target.
>
> I can test on an ESP32-S3 with a USB sound card and report back, including logs, if that
> helps. Would you consider adding this? And if it is already somewhere on your roadmap,
> I would be glad to hear how you plan to expose it.
>
> Thanks!

## Wenn ja — was getestet werden muss

- Erkennung/Enumeration der Soundkarte, Hotplug (Gerät im Betrieb entfernt).
- 44,1 und 48 kHz, 16 Bit, mono/stereo; Verhalten bei nicht unterstütztem Format.
- Wiedergabe aus Datei und aus Stream, Vol/Mute an der Soundkarte.
- Koexistenz mit der bestehenden I2S-Engine (nicht gleichzeitig beide Audio-Pfade).
- Stromversorgung des Host-Ports am jeweiligen S3-Board (5 V für den Host-Port ist bei
  vielen Boards nicht ab Werk freigegeben).

## Wenn nein

Dann Weg B (eigene Firmware) — siehe [02-plan.md](02-plan.md).
