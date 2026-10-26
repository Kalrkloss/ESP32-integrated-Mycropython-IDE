# Running the firmware in esp32sim

esp32sim boots the same image the board runs, so a change can be judged without flashing.
Two things differ from the hardware and have to be handled:

- The application is not passed with `--app`. That flag writes at `0x10000`; the
  partition table puts `ota_0` at `0x20000`. The merged image is a full flash dump, so it
  goes in with `--flash-image`.
- `boot.py`, `main.py`, `/apps` and `/web` live on the FAT partition `vfs` at `0x820000`.
  Without it esp32sim stops at the bare MicroPython REPL and the firmware never starts.

## Tools

| Script | What it does |
|--------|--------------|
| `tools/esp32sim-check.sh` | boots the image, prints boot line, `main.py` line, display line and the panel PNG; exit 0 = panel painted, 1 = booted without display, 3 = emulator has no JC3248W535 model yet, 4 = did not boot |
| `tools/esp32sim-fs.sh` | dumps the `vfs` partition from the attached board into an image for `--flash-at` |

```bash
tools/esp32sim-fs.sh                       # once, needs the board on USB (~4 min)
tools/esp32sim-check.sh                    # uses the newest firmware in /opt/lvgl_micropython
BOARD=none tools/esp32sim-check.sh         # what a stock board model does
```

The check reads `$ESP32SIM` (default `/root/esp32sim/target/release/esp32sim`), `$FW`,
`$ROM` and `$FS`, so it can point at another worktree's build without touching that tree.

## Baseline, measured (no JC3248W535 model)

Without the filesystem image the boot stops at the REPL (`booted : MicroPython ... Octal-SPIRAM`),
with it `boot.py` runs and reports its credentials, then the run goes quiet:

```
$ BOARD=none tools/esp32sim-check.sh
booted   : 1  boot: credentials loaded (app, board, configured, display, hostname, password, ssid)
app      : <no main.py line>      panel: <no display line>      png: missing
exit     : 1
```

So the interpreter, `boot.py` and the partition image all work; what is missing is the
panel. The AXS15231B hangs on QSPI, and until esp32sim models that controller the display
stays dark and `main.py` never gets past its display bring-up.

`tools/esp32sim-check.sh` picks the first emulator binary under `/root/esp32sim*/target/release`
that accepts the board name, so a model built in another worktree is used without touching
that tree; `$ESP32SIM` overrides the choice.

## Verified: the panel model drives this firmware

With esp32sim's `jc3248w535` board (commit `1d393bd2`, built in a separate worktree) the
firmware runs end to end:

```
display_config: board JC3248W535, display axs15231b (320x480, qspi)
display_config: SPIBusFast (DMA, chunked transfers)
display_config: two full frame buffers (307200 bytes each)
display_config: init ok
display_config: touch axs15231 at address 0x3B
main: touch ok
app_loader: started launcher
main: debug server on http://10.0.2.15/
qspi panel 320x480: 98 packets (98 commands), 614530 continuation bytes,
                    3 RAMWR, 307202 pixels, bbox=Some((0, 0, 319, 479))
```

The emulator's panel frame is **pixel-identical** to the frame the board puts on its own
glass: the launcher captures compared 153600 pixels, 0 differing, maximum channel delta 0
(the PNG files hash differently only because of encoding). So the QSPI framing, the
chunked `SPIBusFast` writes, the full-frame refresh and the touch init all match.

Reproduce:

```bash
tools/esp32sim-fs.sh                       # vfs partition from the board
WIFI="ssid=...\,psk=...\,chan=6" tools/esp32sim-check.sh   # credentials from wifi.json
```

**The `--wifi` is not optional.** Without a virtual AP the guest cannot join, `boot.py`
sits in its 45 s connect timeout and `main.py` never starts -- the panel model then reports
`0 packets` and the PNG is an empty white GRAM, which looks like a broken panel model but
is a firmware that never reached the display.

## Pitfalls

- `--max-seconds` is mandatory for a probe. Without it the emulator runs until killed, and
  an `--app /dev/null` probe hangs for minutes.
- A wrong `--board` value prints the accepted list and exits immediately -- that is the
  cheapest way to ask the emulator which boards it knows.
- Creating the FAT image with `mkfs` is not available to this agent (blocked), hence the
  dump from the device.
- esp32sim runs roughly 0.2-0.8x real time depending on the model; budget wall time, not
  emulated seconds.
