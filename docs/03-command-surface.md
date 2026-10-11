# Intended BASIC commands

Modeled on the naming of the Annex-RDS firmware (`SOUND.*`, `PLAY.*`), so that
existing programs are easily portable. Dotted names as usual in Annex; all
commands are non-blocking and return a return code.

## Device & status

| Command | Meaning |
|---|---|
| `USB.SOUND.INIT [rate]` | start USB host stack + UAC driver; optional sample rate (e.g. 48000) |
| `USB.SOUND.DEVICE$` | description of the detected sound card (vendor/product), empty if none |
| `USB.SOUND.STATE` | 0 = stopped, 1 = ready, 2 = running, negative = error |
| `USB.SOUND.FORMAT` | active rate/bits/channels (e.g. 48000/16/2) |
| `USB.SOUND.CLOSE` | close device, stop USB host |

## Playback

| Command | Meaning |
|---|---|
| `USB.SOUND.VOLUME v` | volume 0–100 (reported to the sound card if a feature unit is present) |
| `USB.SOUND.MUTE on` | mute |
| `PLAY.USB file$ [,rate]` | output file (WAV/MP3/PCM) via the USB sound card |
| `PLAY.STREAM_USB url$` | output stream via the USB sound card |
| `USB.SOUND.TONE freq, ms [,vol]` | test tone — first check command for assembly and wiring |
| `USB.SOUND.WRITE iobuf$` | send raw PCM from the IO buffer |

## Recording

| Command | Meaning |
|---|---|
| `USB.SOUND.MIC.LEVEL` | current input level (0–100) |
| `USB.SOUND.REC file$ [,seconds]` | record the sound card's microphone to a file (WAV) |
| `USB.SOUND.READ iobuf$` | read raw PCM into the IO buffer |

## Events

| Command | Meaning |
|---|---|
| `USB.SOUND.ONERROR label$` | jump target on hotplug/error (device removed, format not supported) |

## Not planned (opposite direction)

If the S3 itself is to appear as a USB sound card on the PC, that would be its own
command family (e.g. `USB.DEVICE.INIT`), implemented with the TinyUSB device stack
(`esp_device_uac`) instead of with the host driver.
