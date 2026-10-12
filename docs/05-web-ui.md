# 11 -- Web interface (console, editor, file manager, configuration)

Reachable at `http://<board-ip>/`. Pure HTML/CSS/JS that is served **by the board itself**
-- the browser loads nothing from the internet, so the interface
also works on a network without internet access.

| Tab | Content |
|---|---|
| **Console** | REPL substitute: run Python lines, view output and device log, image preview, restart the board |
| **Editor** | open/edit/save/run files (CodeMirror with Python highlighting, line numbers, search) |
| **Files** | browse directories, upload and download, rename, delete, new files/folders, free space |
| **Configuration** | Wi-Fi (SSID/password), hostname, brightness, backlight, device info |

## API (JSON, also usable with curl)

| Method | Path | Purpose |
|---|---|---|
| GET | `/` , `/ui` | interface |
| GET | `/app.js`, `/app.css` | control logic and style |
| GET | `/editor/*` | bundled code editor (prefix route) |
| GET | `/api/state` | IP, heap, uptime, filesystem, image source |
| POST | `/api/exec` | run Python (`{"code": "..."}` or plain text) |
| GET | `/api/log` | console/log ring (`?clear=1` empties) |
| GET | `/api/files?path=/` | list directory |
| GET | `/api/file?path=...` | read file (`?download=1` as attachment) |
| POST | `/api/file?path=...` | write file (body = content) |
| DELETE | `/api/file` | delete file/folder (`{"path": "..."}`) |
| POST | `/api/mkdir`, `/api/rename` | create folder, rename |
| GET/POST | `/api/config` | read/write configuration |
| GET | `/api/screen.png` , `/screen.raw` | screen as PNG / raw buffer |
| POST | `/api/reset` | restart the board |
| GET | `/status` | plaintext status (tools, image source) for a quick look |

## Structure

* **Files instead of an embedded page:** HTML, CSS and JS lie in
  `firmware/webfiles/` and on the device under `/web/`. Reason: in a
  Python string, `\n` in JS string literals becomes real line breaks -- the
  first version failed exactly on that, the whole script was no longer parsed
  and the page remained without function. Side effect: the files are editable in the
  file manager. The host test therefore checks the JS syntax with
  `node --check`.
* **No CDN:** the editor (CodeMirror 5.65.16, MIT) lies with all necessary
  addons in `firmware/webfiles/editor/`. If it is missing on the device, the
  interface falls back to a simple text field.
* **Prefix routes:** routes ending with `*` (`GET /editor/*`) serve whole
  file trees; the path is strictly checked (only `<WEB_DIR>/editor`, no `..`).
* **Chunked delivery:** `Response(..., datei=pfad)` sends large files in
  2-KB chunks. Pulling a 174-KB file into memory in one piece was the
  trigger for the server's accept loop dying (the board
  then answered ping, but nothing listened on port 80 any more).
* **Supervision of the accept loop:** `mcp_serve._aufsicht` restarts the
  listener if it does fail once, and writes the reason into the
  log ring. Errors in handlers also land in the log (`HTTP-Fehler: ...`).

## Image preview: raw buffer instead of PNG

An LVGL snapshot with PNG encoding in pure Python costs on this board
**3 to 22 seconds** (scale 2 runs into the timeout). Therefore:

* `main.py` reports the display's **framebuffer** after display start
  (`mcp_screen.attach_framebuffer()`). Captures then read directly from it, without
  an LVGL snapshot. Measured values: scale 1 = 0.45 s, scale 4 = 1.2 s.
* The interface fetches the **raw buffer** (`/screen.raw?scale=4`) and converts it
  in the browser into an image (canvas, RGB565 → RGBA). On the board every
  encoding is therefore dispensed with.

## Configuration

`config.json` on the device (`ssid`, `password`, `hostname`, `brightness`,
`backlight`). `boot.py` first reads `config.json` and fills empty fields from the
legacy `wifi.json` -- both places use the same rule, so that the
interface and the boot process see the same effective configuration.

* The **password is never returned to the browser**; the page only shows whether
  one is stored. An empty field means "keep the existing one".
* Wi-Fi and hostname take effect after a restart, the brightness can be applied
  immediately (the page calls `/api/exec` for that).

## Security

**No authentication.** The interface can execute arbitrary code on the board
and write files -- it belongs in a trusted, isolated network. Anyone who does
not want that must block the port (or remove the debug server from `main.py`).

## Testing and deployment

```bash
python3 tests/test_webui.py     # 139 checks without hardware (page, API, HTTP, editor)
python3 tests/test_boot.py      # credential merge
python3 tests/test_mcpsrv.py    # server core (regression)

./tools/deploy.sh all           # modules, drivers, web files, main.py, boot.py
./tools/deploy.sh web           # only the web interface
```
