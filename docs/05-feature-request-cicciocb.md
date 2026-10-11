# Draft: Feature request to cicciocb (USB audio / UAC host, ESP32-S3)

Way A from [04-einhaengen-in-fremde-firmware.md](04-einhaengen-in-fremde-firmware.md):
instead of reverse engineering, a request to the author — he has source code, task level and
command table, and the USB host stack is already present in the S3 build.

Target platform: <https://cicciocb.com/forum> (registration as a forum member required).
Language: English (forum language).

## Subject

`Feature request: USB Audio Class (UAC) host support on ESP32-S3`

## Text (to post)

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

## If yes — what must be tested

- Detection/enumeration of the sound card, hotplug (device removed during operation).
- 44.1 and 48 kHz, 16 bit, mono/stereo; behavior with an unsupported format.
- Playback from file and from stream, vol/mute at the sound card.
- Coexistence with the existing I2S engine (not both audio paths at the same time).
- Power supply of the host port on the respective S3 board (5 V for the host port is on
  many boards not enabled from the factory).

## If no

Then way B (own firmware) — see [02-plan.md](02-plan.md).
