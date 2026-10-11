# Initial Situation & Feasibility

Status: 2026-10-10

## 1. What is delivered

- Firmware download: <https://updates.cicciocb.com/> ("ANNEX RDS FIRMWARE UPDATES v9",
  last change shown there: 04.08.2026). What is delivered are **ready-made `.bin` files**,
  per chip, variant and flash mode.
- Web installer: <https://flasher.cicciocb.com/>
- ESP32-S3 variants (excerpt from the download list): `Annex32-S3_LVGL_HID_OTG_2.99.x_qio_opi.bin`,
  `Annex32-S3_DMT_LVGL_HID_OTG_ATS_2.99.x_qio_opi.bin`, `Annex32-S3_CAN_USB_DMT_HID_OTG_2.00.92_qio_qspi.bin`.
- Example size: the S3 file `Annex32-S3_LVGL_HID_OTG_2.99.07_qio_opi.bin` is
  **2,871,232 bytes** (HTTP `content-length`). This is a merged flash image
  (bootloader + partition table + application).
- Relevance for this project: names such as `USB`, `HID`, `OTG` show that the S3 build
  **already contains a USB host stack**; the documentation lists "USB HID INTERFACE
  (Mouse, Keyboard, Gamepad) – ESP32-S3 only". For the author, a UAC host driver
  is therefore a comparatively small addition.

## 2. License situation (decisive)

- FAQ (<https://cicciocb.com/annexwifi/faq.html>):
  > "Q: If Annex is free, where I can find the source codes?
  >  A: Annex is free, but it is not open source, so the source code is not available."
- Copyright (<https://cicciocb.com/annexwifi/copyright.html>):
  > "It is not allowed to reverse engineer, decompile or disassemble the compiled objects
  >  (the .bin and the .exe files) or any attempt to do so."
- Manual (<https://cicciocb.com/annex32help/V2.9912/start.htm>): Copyright 2017–2025
  Francesco Ceccarella (ciccioCB). The **binary image** may be redistributed for
  non-commercial purposes, the source code may not.

Consequence: source code reconstructed from the binary would violate the license, and its
publication would be a copyright infringement. For this reason this project did **not**
decompile/disassemble. Only public metadata (HTTP headers, download list, docs) were used.

## 3. Question: can REA produce compilable source code?

Tools on this host: REA 6.3.0 (`/usr/local/bin/rea`), as analysis providers
Ghidra 12.1.4 (`/opt/ghidra_12.1.4_PUBLIC`) and Hopper 6.4.2 (`/opt/hopper`).
Firmware region extraction requires Binwalk/Unblob (not installed here).

What REA/Ghidra/Hopper can deliver as a result:

- per function **pseudo-C without types and without names**, without struct/header definitions,
- no build files, no linker script, no memory map, no partition layout to reproduce,
- **none** of the included libraries in source form (ESP-IDF, FreeRTOS, WLAN stack, LVGL,
  Annex' I2S sound engine, web UI, file system),
- no comments, no configuration, no rebuild parameters.

An image of this size contains several thousand functions. A project arising from it
is not compilable and not maintainable; it is analysis material, not source code.

There is also the functional part: a USB audio host driver reaches deep into the firmware
(USB host library, isochronous transfers, ring buffers, its own tasks, coupling to the
audio engine). Such interventions cannot sensibly be patched into a foreign, symbol-free
binary — every version would have to be re-patched.

**Result: No.** No compilable source code can be produced from the Annex binary
into which one could build USB sound. At most *small* insights
about individual functions would be plausible (analysis purposes), not an extensible project.

## 4. Options that actually work

### 4.1 Ask the author (smallest effort)

USB host stack and OTG are already present in the S3 build (see section 1).
A UAC host driver based on `espressif/usb_host_uac` would be a
manageable extension for cicciocb. Forum: <https://cicciocb.com/forum> — there is already
the precedent "USB HID" (S3-only), including a documentation entry.

### 4.2 Own ESP-IDF project (this repository)

Building blocks, officially from Espressif or from the community:

| Purpose | Building block | Source |
|---|---|---|
| USB host, Audio Class 1.0 (speaker + microphone, vol/mute) | `espressif/usb_host_uac` | <https://components.espressif.com/components/espressif/usb_host_uac> |
| USB host UVC+UAC streams (ring buffer, suspend/resume) | `usb_stream` (esp-iot-solution) | <https://docs.espressif.com/projects/esp-iot-solution/en/latest/usb/usb_host/usb_stream.html> |
| USB host, Audio Class 2.0 (ESP32-S3) | `esp-uac2-host` | presented at <https://blog.adafruit.com/2026/04/06/a-usb-audio-class-2-0-host-driver-for-esp32-s3/> |
| Opposite direction: S3 *is* the sound card on the PC (UAC device, TinyUSB) | `esp_device_uac` | <https://docs.espressif.com/projects/esp-iot-solution/en/latest/usb/usb_device/usb_device_uac.html> |
| Opposite direction, Arduino-based | arduino-audio-tools (UAC2) | <https://www.pschatzmann.ch/home/2026/06/22/usb-audio-class-2-0-for-arduino/> |

Hardware limits (ESP32-S3): USB-OTG is **full speed (12 Mbit/s)** and host and
device share the same port — usable audio quality here means 1 channel
microphone + 1 channel speaker, 44.1/48 kHz, 16 bit.

### 4.3 BASIC base (open source) for the own project

| Project | License | Suitability |
|---|---|---|
| [paladin-t/my_basic](https://github.com/paladin-t/my_basic) | MIT | 2 C files, < 128 KB, expressly intended for embedding/extending — smallest path to `SOUND.USB.*` |
| [slviajero/tinybasic](https://github.com/slviajero/tinybasic) | BSD-3 | very broad platform abstraction, ESP32 already supported |
| [legio-e/BasicPlus](https://github.com/legio-e/BasicPlus) | MIT | bytecode VM with debugger, ESP32-S3/P4 firmware available |

Not suitable: **Basic32** (Ferrazzi) — likewise closed source, only binaries
(<https://github.com/Ferrazzi/Basic32>).

## 5. Open / not examined

- Whether cicciocb already plans or rejects USB audio (not researched).
- Whether Annex has an extension interface for native code. No such interface emerges from the
  manual and download list; the documented commands are built in.
- Whether in reality a UAC 1.0 or UAC 2.0 sound card is present (depends on the test device).
