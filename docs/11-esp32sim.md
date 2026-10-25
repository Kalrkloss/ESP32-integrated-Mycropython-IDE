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

## Pitfalls

- `--max-seconds` is mandatory for a probe. Without it the emulator runs until killed, and
  an `--app /dev/null` probe hangs for minutes.
- A wrong `--board` value prints the accepted list and exits immediately -- that is the
  cheapest way to ask the emulator which boards it knows.
- Creating the FAT image with `mkfs` is not available to this agent (blocked), hence the
  dump from the device.
- esp32sim runs roughly 0.2-0.8x real time depending on the model; budget wall time, not
  emulated seconds.
