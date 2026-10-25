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

```
booted : MicroPython 78ff170de9-dirty on 2026-10-25; Generic ESP32S3 module with Octal-SPIRAM
exit   : 1  (no display line, no PNG)
```

So the firmware itself runs under the emulator: ROM boot chain, bootloader, MicroPython
banner and REPL all come up. What is missing is the panel model -- the AXS15231B is driven
over QSPI, and until esp32sim models that controller the display stays dark and `main.py`
cannot finish its display bring-up.

## Pitfalls

- `--max-seconds` is mandatory for a probe. Without it the emulator runs until killed, and
  an `--app /dev/null` probe hangs for minutes.
- A wrong `--board` value prints the accepted list and exits immediately -- that is the
  cheapest way to ask the emulator which boards it knows.
- Creating the FAT image with `mkfs` is not available to this agent (blocked), hence the
  dump from the device.
- esp32sim runs roughly 0.2-0.8x real time depending on the model; budget wall time, not
  emulated seconds.
