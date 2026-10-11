# Plan

## Target picture

An ESP-IDF project for the ESP32-S3 that

1. addresses a USB sound card over the OTG port as host (UAC),
2. routes the audio data via I2S to a DAC/speaker or from a microphone away,
3. makes this capability accessible via BASIC commands (`USB.SOUND.*`, see
   [03-command-surface.md](03-command-surface.md)),
4. can be flashed and tested on real hardware.

## Assumption

"Support for USB sound cards" means: the **S3 is USB host** and addresses an
attached USB sound card (playback, optionally recording via the sound card's
microphone). The opposite direction (the S3 itself appears as a sound card on the PC) is
technically also feasible, but is a different feature — see section 4.2 in the initial
situation.

## Stages

### E1 — Project skeleton
- ESP-IDF v5.x, target `esp32s3`, partition table with room for app + file system.
- Console output via USB-Serial-JTAG (debug) and console via UART.
- Evidence: `idf.py build` runs, device boots, console prompt appears.

### E2 — UAC host
- `espressif/usb_host_uac` as a dependency, device detection, format negotiation,
  error/hotplug handling.
- Evidence: log shows detected sound card with rate/channels/bit depth.

### E3 — Audio path
- Playback: file/stream → ring buffer → `uac_host_device_write` (sound card's speaker).
- Alternative output: UAC → I2S → DAC (in case the sound card only has an input).
- Recording: `uac_host_device_read` → buffer/file.
- Evidence: test tone audible through the USB sound card; recording provable in a file.

### E4 — BASIC integration
- Integrate a BASIC base (recommendation: my_basic, MIT — two C files, extensible via
  native functions).
- Register native commands `USB.SOUND.*`, return errors as BASIC errors.
- Evidence: BASIC program starts playback and sets the volume.

### E5 — Test & Docs
- Test scripts, example programs, command reference, assembly guide (wiring,
  power supply of the host port — on many S3 boards 5 V for the host port
  must first be enabled via a solder bridge/jumper).

## Constraints

- ESP32-S3 OTG is full speed: realistically 44.1/48 kHz, 16 bit, 1–2 channels.
- The OTG port is used at the same time for console/flash — clarify power supply and
  pin assignment beforehand, otherwise debugging via USB-Serial-JTAG during
  host operation is not possible.
- No code from the Annex firmware, no third-party binaries in the repository.

## Decisions that are still open

1. BASIC base (my_basic vs. tinybasic vs. BasicPlus vs. own mini interpreter).
2. Direction: host (sound card at the S3) — or additionally device (S3 as sound card).
3. Target board/test hardware and the specific USB sound card actually present.
