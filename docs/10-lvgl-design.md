# LVGL design system and the off-device preview

Two things live here: the design tokens every application shares (`firmware/apps/_ui.py`),
and the loop that renders a screen to a PNG on the host so a change can be judged without
flashing the board (`tools/preview/`).

## Why a token module

The examples looked like eight different products: seven used `BG = 0x101820`, the launcher
used `0xEFF3F8`, every file carried its own palette, its own radii and its own positions, and
`_font()` silently fell back to 16 px whenever a size was not compiled in -- so a "20 px title"
and a "12 px caption" both rendered at 16 px. Colours, spacing and type have to come from one
place, otherwise a restyle means editing twenty call sites.

`firmware/apps/_ui.py` is that place. It starts with `_`, so `app_loader` does not list it as an
application.

## Tokens

| Group | Tokens | Values |
|-------|--------|--------|
| Surfaces | `BG`, `SURFACE`, `SURFACE_ALT`, `LINE` | `0x0E141B`, `0x18222D`, `0x22303E`, `0x2A3947` |
| Text | `TEXT`, `DIM` | `0xF2F6FA` (14.8:1 on surface), `0x9FB0C0` (7.2:1) |
| Accent | `ACCENT`, `ACCENT_PRESSED`, `ACCENT_TEXT`, `ACCENT_SOFT` | `0x1F6FEB` (white text 4.6:1), `0x17509E`, `0xFFFFFF`, `0x152438` |
| Semantic | `OK`, `WARN`, `DANGER` | `0x3FB950`, `0xD29922`, `0xF85149` |
| Markers | `MARK_X`, `MARK_O` | `0x58B4F5`, `0xE3B341` |
| Spacing | `S1`..`S6` | 4, 8, 12, 16, 24, 32 (8 px grid) |
| Radius | `R_SM`, `R_MD`, `R_LG`, `R_PILL` | 8, 12, 16, pill |
| Targets | `TOUCH_MIN`, `HEADER_H` | 48, 56 |

Contrast numbers are WCAG ratios measured against the surface the colour sits on. `LINE` is a
hairline and never carries text.

## Widgets

| Call | What it gives you |
|------|-------------------|
| `ui.screen(parent)` | The screen, normalised: token background, radius 0, no padding, no scroll |
| `ui.header(screen, title, subtitle)` | 56 px band, hairline rule, title 20 px, subtitle 12 px exposed as `.subtitle` so a screen can update its status line |
| `ui.card(parent, x, y, w, h)` | Surface + 1 px hairline, one elevation level -- never nest cards |
| `ui.button(parent, text, x, y, ...)` | The only button builder: `primary`, `ghost`, `quiet`; pressed/disabled states are set as selectors on the object, not by hand in a callback; refuses a height below `TOUCH_MIN` |
| `ui.label`, `ui.pill`, `ui.box` | Text, capsule badge, plain rectangle |
| `ui.tap(obj, cb)` | Clickable + 8 px extra click area (glossy panels have parallax at the edge) |
| `ui.font(size)` | Largest compiled Montserrat at or below `size` -- no silent jump to 16 |
| `ui.set_enabled` / `ui.set_checked` | Real `DISABLED` / `CHECKED` states, not colour guesses |

Rules that the module enforces by construction and the tests check where they can:

* No raw `lv.color_hex(0x...)` in an application; colour arrives as a token.
* Every interactive element is at least 48 px tall and clickable beyond its pixels.
* One button anatomy, one card anatomy -- states are part of the widget, not of the call site.
* 8 px grid for sibling gaps, consistent outer margin (`S4`).

## Off-device preview

`tools/preview/` renders an application to a PNG on the host, so the design loop is
"edit -> render -> look" instead of "edit -> deploy -> photograph the panel".

```
tools/preview/
  build_runtime.sh   builds the lv_micropython unix port (SDL2) used as the renderer
  preview.py         host side: runs the renderer, converts the frame to PNG
  render.py          runs inside the renderer: registers a display, calls start(screen)
  stub/app_loader.py host stand-in for the device module the launcher imports
  baseline/          the screens as they looked before the token migration
```

```bash
bash tools/preview/build_runtime.sh            # once, ~5 min, needs libsdl2-dev
python3 tools/preview/preview.py firmware/apps/launcher.py
python3 tools/preview/preview.py firmware/apps/tic_tac_toe.py --out /tmp/tictactoe.png
```

The renderer is the `unix` port of `lv_micropython` in `/opt/lv_micropython`; `$LVMP_BIN`
overrides the path. Output defaults to `tools/preview/out/<app>.png`.

How it works: `render.py` registers a single full-screen ARGB8888 buffer as the display,
imports the application, calls its normal `start(screen)` entry point and refreshes one frame
with `lv.refr_now()`. The buffer therefore holds the whole frame, and it is written out as
raw BGRA (8-byte header: width, height, both little endian) for pillow to convert. Two
consequences matter:

* No board-specific code is added to the applications: the same `start()` the loader calls.
* What it cannot show is the panel itself -- colour inversion, gamma and backlight are still
  hardware properties. The preview answers "is the layout right", the camera on the panel
  answers "is the glass right".

`SDL_VIDEODRIVER=dummy` is set by `preview.py`, so no window opens and the whole thing runs
over SSH. `tools/preview/scenes/` holds extra entry points for a state that only occurs
after interaction (a finished game, for instance): a scene module calls the real
`start(screen)` and then drives the app's own methods.

## Fonts: the reason the hierarchy was flat

`lib/lv_conf.h` enabled only `LV_FONT_MONTSERRAT_12/14/16`. Every application asked for
18/20/48 px and every request silently landed on 16 px, so titles, digits and captions had
one size on the glass -- the "all text looks the same" symptom. `20`, `24`, `28` and `40`
are now enabled in the same `lv_conf.h` the firmware build uses. **The board has to be
re-flashed with a rebuilt firmware for those sizes to appear**; until then the on-device
render still shows 16 px everywhere while the preview shows the intended sizes.

Probe what a build actually carries:

```bash
$LVMP_BIN -c "import lvgl as lv; print([n for n in dir(lv) if n.startswith('font_montserrat')])"
```

## Measured geometry, not impressions

The board block on the tic-tac-toe screen was described as "off-centre to the left" in a
visual review; measuring the PNG showed content from x=20 to x=299 on a 320 px panel, i.e.
exactly symmetric. Check positions numerically (`PIL`, count columns that differ from the
background colour) before "fixing" a layout, and use the visual check for hierarchy,
weight and readability instead.

## Panel notes

320x480 portrait, bright content on a dark surface. A dark UI on an LCD reads as a dead
display in a photo (see `09-lessons-learned.md`): keep text luminance high, avoid large
near-black areas with nothing on them, and remember the splash screen when judging
"is the display alive".
