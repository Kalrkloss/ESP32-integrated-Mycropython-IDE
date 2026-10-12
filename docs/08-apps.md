# 14 - Example applications

The board ships with a set of MicroPython/LVGL applications and a loader that starts
them and switches between them at runtime. `launcher` is the default screen.

## Applications

| File                  | Title        | What it does                                             |
|-----------------------|--------------|----------------------------------------------------------|
| `launcher.py`         | Launcher     | Lists the other applications, tap a row to start one     |
| `snake.py`            | Snake        | 8x8 grid, arrow buttons, growing snake, score             |
| `minesweeper.py`      | Minesweeper  | Dig and flag mode, field size and mine count adjustable  |
| `sokoban.py`          | Sokoban      | Push boxes onto goals, undo and reset                     |
| `calculator.py`       | Calculator   | Four functions, large touch keypad                        |
| `clock.py`            | Clock        | Live clock, stopwatch and an alarm that flashes the panel |
| `game2048.py`         | 2048         | Slide and merge tiles with the arrow buttons              |
| `tic_tac_toe.py`      | Tic-Tac-Toe  | Human against the computer                                |

All of them fit a 320x480 portrait panel, use touch targets of at least 40x40 px and
keep the memory footprint small enough for the ESP32-S3.

## Contract

An application is one Python file in `/apps` (repo: `firmware/apps/`) that provides:

```python
TITLE = "Snake"                                    # text in the launcher
DESCRIPTION = "Steer the snake, eat the food."

def start(parent=None):                            # builds the UI
    ...
    return handle                                  # handle.stop() removes everything
```

* `start()` builds on `lv.screen_active()` (or the given `parent`) and returns a
  handle whose `stop()` deletes its own timers and objects again.
* Animation uses its own `lv.timer_create()`. There is no `lv.ANIM` in this binding.
* Only `lvgl` and the standard library are imported (checked by `tests/test_apps.py`),
  texts are ASCII (the device fonts have no umlauts).
* LVGL is touched only from the main thread: the game loops are LVGL timers, so they
  run inside the main loop.

## Choosing and switching applications

* `config.json`: `"app": "snake"` picks the application started at boot. The web UI's
  configuration tab offers the applications found on the device.
* At runtime: `POST /api/app {"name": "snake"}` (web UI: "Start application now") or a
  tap in the launcher. The request is stored by `app_loader.request_app()` and
  executed by `app_loader.service_requests()` in the main loop -- starting an
  application from inside an LVGL click callback would delete the objects the event
  is currently being dispatched to.
* `GET /api/apps` lists what is on the device, with title and description.

## Loader

`firmware/device/app_loader.py`:

| Function                     | Purpose                                                       |
|------------------------------|---------------------------------------------------------------|
| `list_apps()`                | Scans `/apps`; reads `TITLE`/`DESCRIPTION` from the text, so listing does not import every application |
| `app_names()`                | Names, launcher included (for validation)                      |
| `import_app(name)`           | Adds `/apps` to `sys.path`, rejects names with a path           |
| `start_app(name)` / `stop_app()` | Start and stop, always called from the main loop            |
| `request_app(name)`          | Thread safe request from the web UI                            |
| `service_requests()`         | Called from `main.py`'s loop; executes a pending request       |
| `running_app()` / `last_error()` | State for the web UI                                      |

`main.py` starts `display_config.load_config()["app"]` through the loader and adds
`app_loader.service_requests()` to the loop hooks. If the loader is missing on the
device, `main.py` falls back to the built-in demo screen instead of failing.

## Deploying

```sh
tools/deploy.sh apps     # /apps plus app_loader.py
tools/deploy.sh all      # everything, including the applications
tools/deploy.sh exec "import app_loader; print(app_loader.app_names())"
```

## Verification

`tests/test_apps.py` (host, no hardware) checks for every application that it parses,
exposes `TITLE`/`DESCRIPTION`/`start(parent=None)`, imports nothing outside the
allowed set, contains no non-ASCII characters and cleans up after itself; plus the
loader's listing, its rejection of path names and the request/start/stop sequence
against a temporary application directory.

`tools/apps_smoke.py` drives every application on the real board: it points
`config.json` at the application, power cycles the board, waits for the log line
`app_loader: started <name>`, and fetches the framebuffer to confirm that something
was actually drawn. Anything that fails to start is reported instead of being
swallowed.
