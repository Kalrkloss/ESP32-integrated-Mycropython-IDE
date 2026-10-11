# 12 -- LVGL remote control: show and operate the board UI live in the browser

Goal: see the LVGL UI of the JC3248W535 (ESP32-S3, MicroPython + LVGL 9) in one's
own browser **and** operate it with mouse/touch -- a "TV remote control"
mode, but exclusively over the **existing own HTTP server**
(`mcp_httpd.py`), without new dependencies and without touching LVGL from a foreign
thread.

All numbers in this document are measured on the real board (192.168.1.168),
read-only. Measurement script: `tools/bench_vorschau.py`. Reproducible with
`python3 tools/bench_vorschau.py 3`.

---

## 1. Context: what others do

### 1.1 LVGLRemoteServer (CubeCoders)

Reference for "mirror the LVGL window to the desktop". Important properties:

* **C++ library** for ESP32/Arduino. Insert into `disp_flush(disp, area, pixelmap)`
  (`remoteDisplay.sendRLE(area, pixelmap)`), then as usual `lv_disp_flush_ready()`.
* **RLE-compressed packets**, **one UDP packet per update** -- deliberately not TCP, so
  that each packet stands on its own (no loss-induced follow-on state).
* Transmits only the **bounding-rectangle `area`** of the flush, not the whole screen;
  the receiver knows the image size and colour format and renders the rectangle.
* **Zero allocation**: no dynamic memory management, constant footprint.
* **Input** comes back as simulated touch events (mouse -> pointer).
* Desktop client (Flutter/Windows) -- no browser.

Core idea that can be carried over: **hook into the flush, send only the changed
rectangle, one self-contained packet per update.** This idea is worth gold on our
board (see section 4.3) -- because LVGL already delivers the rectangle to us.

### 1.2 lv_port_esp32_web (danjulio)

WebSocket driver: LVGL sends **region refresh** over a WebSocket to a
bundled HTML page with `<canvas>`; mouse/touch events go **over the same
WebSocket** back. Payload header: pixel depth, canvas width/height, redraw region
(X1,Y1,X2,Y2), then pixel data. Reverse direction: flag (touch/release) + X + Y. Multiple
browsers at once are possible; on connecting, the screen is redrawn once completely.
Exactly this model fits our plan best.

### 1.3 WebAssembly solutions (lv_web_emscripten, lvgl-wasm)

LVGL is translated to **WebAssembly** with Emscripten and runs **entirely in the
browser**. No device, no transmission -- but it is a **second, independent
UI instance**: it does not show what happens on the real panel and cannot control the real
hardware (GPIO, Wi-Fi). Useless for "debug and remote control of the running
device". (It would be different if one developed the UI browser-first.)

### 1.4 MJPEG/multipart streaming and canvas delta

* **MJPEG/`multipart/x-mixed-replace`:** a persistent HTTP response that continuously
  writes finished images (`JPEG`/`PNG`); the browser displays them with
  `<img src="/stream">` on its own. Problem on our board: **every** image file
  would have to be encoded on the device -- and PNG in pure Python costs here
  **3-22 s** (see `docs/11`). JPEG does not exist in this MicroPython build. Without a
  finished image format the browser cannot use `<img>`; one then needs own JS
  that reads the raw bytes -- and then it is effectively its own push stream.
* **Canvas delta updates:** the browser draws only changed rectangles into a
  canvas -- that is the browser side of the already recommended delta transmission
  (section 2/4).

### 1.5 Conclusion of the context

For **our** board the viable line is: **raw buffer RGB565 over the own
HTTP server, only changed rectangles, input back into a second LVGL indev.**
Whether polling, a long-lived push stream or a WebSocket lies in between is
a detail question -- all three are feasible with the existing server (section 2).

---

## 2. Concrete design for our board

### 2.1 Transport: polling vs. multipart push vs. WebSocket

Starting point of the server (`mcp_httpd.py`): HTTP/1.1, route table
`"METHOD /path" -> handler(Request) -> Response`, **no WebSocket, no
chunked transfer, every response closes the connection**, up to 4 worker threads.

The measured bottleneck is **not the computation time, but the Wi-Fi throughput**:
throughout **~660-830 KB/s** when sending a 307200-byte frame. In addition
**every new connection setup costs ~67 ms** (measured: `GET /screen`, small
response). Hence the three paths:

| Path | Principle | Advantage | Disadvantage | Rating |
|---|---|---|---|---|
| **Polling** (as today) | `fetch("/screen.raw?scale=1")` on a timer | uses the server **unchanged**; robust against aborts; no new server code | 67 ms overhead **per** frame; fixed rate even without change | **P0** |
| **Multipart/length push** | **one** long-lived `GET` response into which the handler continuously writes `[4 byte length][RGB565]` frames | no connection overhead (2.2 instead of 1.9 fps at full screen); change push possible | handler must "own" the connection; browser reads via `ReadableStream`; one worker thread permanently occupied per viewer | **P2 alternative** |
| **WebSocket** (binary) | real bidirectional session; image out, pointer back | lowest overhead; input on the **same** line; close to `lv_port_esp32_web` | handshake must be computed **by oneself**; `mcp_httpd` must pass the socket through to the handler; one thread per session | **Recommended target** |

**Important finding on WebSocket feasibility:** this MicroPython build almost
brings it. Verified on the board (read-only):

* `import websocket` delivers a **C module** (`extmod/modwebsocket.c`,
  object `websocket.websocket(sock)`) with `read`, `readinto`, `readline`, `write`,
  `close`, `ioctl` -- it handles **the entire frame parsing/masking**.
* `import asyncio` present (`start_server`).
* `hashlib.sha1(b"...").digest()` **works** (only `hexdigest()` is missing) and
  `ubinascii.b2a_base64()` delivers the Base64 form -- so
  `Sec-WebSocket-Accept = base64(sha1(key + GUID))` is computable.
* `_thread.allocate_lock()` present.

So only the **HTTP upgrade handshake** is missing (about 30 lines of Python) and a
**way to hand the accepted socket to a handler**. The latter is the only
real change to the server: either a second listener on its own port (e.g. 81)
with its own accept loop -- **additive, without touching `mcp_httpd`** -- or a
small `Response` variant "connection stays open" that passes the `stream` to the handler.

**Recommendation:**

* **P0/P1 (now):** polling. No rebuild, immediately visible. Full screen at ~2 fps.
* **P2 (target):** **WebSocket** on its own port (route `/ws`), binary frames,
  the same session carries image **and** pointer. The `websocket` extmod takes the
  framing off our hands; that is the smallest risk effort for the best effect. The
  multipart length push is the fallback variant if the handshake fails.

### 2.2 Image format

**Raw buffer RGB565, 2 bytes/pixel, `rgb565_byte_swap=True`** -- exactly what
`/screen.raw?scale=1` delivers today and what `app.js` already converts correctly in the canvas
(lines 167-173: `roh[i] | roh[i+1]<<8`, then RGB565->RGBA). No
device-side encoding.

Evaluation of the format alternatives **on this board**:

| Format | Effort on the device | Verdict |
|---|---|---|
| **Raw RGB565** | only copy (307200 B = **38 ms**, 8.1 MB/s memcpy) | **standard** |
| **Deflate** (`deflate.DeflateIO` exists) | pure-Python deflate costs **3-22 s** per frame | **excluded** |
| **RLE** | encoder would be pure Python; even the *diff scan* costs 395 ms (see 4.3) | **only sensible in C** -- unusable with pure Python |
| **Delta rectangles** | LVGL delivers the rectangle **for free** (C side, see 4.3) | **preferred from P2** |
| **PNG/JPEG** | PNG 3-22 s; JPEG missing | **excluded** |

Mnemonic: **Do not run over pixels on the device in Python.** Neither shrink
(2.3), nor compress, nor diff. The **browser** (JS is fast) or a C path in the
LVGL flush runs over pixels.

### 2.3 Frame rate, memory, CPU

* Native resolution 320x480 is the **only** sensible transmission size: the
  device-side shrinking is the slowest path of all (section 4.2). If one wants
  to display smaller, **the browser scales** the canvas up/down -- that is
  free.
* **Full-screen push** reaches **~2.2 fps** (0.455 s transfer + ~0.067 s overhead
  during polling). That is usable for "following/debugging", not for fluid
  animations.
* **Delta rectangles from P2** raise that to **8-26 fps** for typical UI changes
  (extrapolation, section 4.4); at idle **0 bytes** flow.
* **Memory:** an incoming full screen needs a shadow/send buffer of
  307200 B in PSRAM. The MicroPython GC heap is PSRAM-backed (measured free: **~6.0-6.5 MB**).
  The **internal SRAM** is very tight at **~32 KB free** -- keep every extra structure
  there (queues, socket buffers) small and leave data buffers in PSRAM.
* **CPU:** the real bottleneck is the radio link; the sending runs in C. The
  Python share per full screen is ~2 copies (38 ms). Important: the **framebuffer capture
  does not touch LVGL** -- it only reads memory, the main loop continues.

---

## 3. Input path: browser pointer -> LVGL

We cannot "remote-control" an existing LVGL indev, because the physical touch
(`axs15231.AXS15231`) reads its coordinates itself on I2C. Instead we register a
**second pointer indev** whose Python read callback pulls the events from
a queue. Verified API (from
`/opt/lvgl_micropython/api_drivers/py_api_drivers/frozen/indev/_indev_base.py`,
`pointer_framework.py` and `lvgl.pyi`):

* `lv.indev_create()` -> `indev_t` (`lvgl.pyi:19701`)
* `indev.set_type(lv.INDEV_TYPE.POINTER)` (`:10842`, `INDEV_TYPE` from `:979`)
* `indev.set_display(lv.display_get_default())` (`:10866`)
* `indev.set_read_cb(cb)` (`:10848`) -- `cb(drv, data)`; `data` is `indev_data_t`
  with `data.point.x`, `data.point.y`, `data.state`, `data.continue_reading`
  (`:11204-11278`)
* `indev.enable(True)` (`:10836`)

`_indev_base.IndevBase._read` is exactly that pattern: set `data.point.x/y`,
set `data.state`, `data.continue_reading = False`.

### 3.1 Recommended code (runs in the LVGL/main thread)

```python
# New file: firmware/mcpsrv/mcp_pointer.py
# A second LVGL pointer indev fed from a queue. LVGL is not thread-safe, so this
# object is created in the main thread; only the plain list is touched by the
# server thread (guarded by a lock). No LVGL call happens outside the main loop.
import _thread
import lvgl as lv

_LOCK = _thread.allocate_lock()
_EVENTS = []          # each item: (pressed: bool, x: int, y: int)
_INDEV = None


def push(x, y, pressed):
    """Called from the HTTP server thread with raw panel coordinates."""
    with _LOCK:
        _EVENTS.append((bool(pressed), int(x), int(y)))


def _pop():
    with _LOCK:
        return _EVENTS.pop(0) if _EVENTS else None


def _read_cb(drv, data):
    ev = _pop()
    if ev is None:
        data.state = lv.INDEV_STATE.RELEASED
    else:
        pressed, x, y = ev
        data.point.x, data.point.y = x, y
        data.state = (lv.INDEV_STATE.PRESSED if pressed
                      else lv.INDEV_STATE.RELEASED)
    data.continue_reading = False


def create():
    """Create and enable the web-pointer indev. MUST run in the LVGL thread,
    after the display is initialised (IndevBase requires a display)."""
    global _INDEV
    if _INDEV is not None:
        return _INDEV
    indev = lv.indev_create()
    indev.set_type(lv.INDEV_TYPE.POINTER)
    indev.set_display(lv.display_get_default())
    indev.set_read_cb(_read_cb)
    indev.enable(True)
    _INDEV = indev
    return _INDEV
```

`main.py` gets **one** line after `start_touch()`: `mcp_pointer.create()`
(in the LVGL thread, i.e. before the main loop). The existing physical touch indev
remains unchanged next to it -- LVGL evaluates both pointer sources.

### 3.2 Alternative: `PointerDriver` subclass

Whoever wants to use the existing chain with calibration can
subclass `pointer_framework.PointerDriver` and override `_get_coords()`:

```python
class WebPointer(pointer_framework.PointerDriver):
    def _get_coords(self):
        ev = _pop()
        if ev is None:
            return None                      # -> driver reports RELEASED
        pressed, x, y = ev
        return (self.PRESSED if pressed else self.RELEASED), x, y
```

`PointerDriver._read` treats `None` correctly (state RELEASED, coordinates
stay at the last value). Disadvantage: forces calibration data and the
display wrapper logic. For injected pixel coordinates the direct
`lv.indev_create` path (3.1) is leaner and more exact.

### 3.3 The server side (input)

A tiny POST endpoint suffices, because the input direction moves **very** little data
(a few dozen bytes per event) -- the 67-ms overhead does not matter here:

```python
# GET/POST /api/pointer?x=..&y=..&p=1   (p=1 down, p=0 up)
def api_pointer(req):
    x = int(req.arg("x", "0")); y = int(req.arg("y", "0"))
    p = req.arg("p", "1") == "1"
    mcp_pointer.push(x, y, p)          # only touch the list, no LVGL
    return mcp_httpd.json_response({"ok": True})
```

In the browser (in `app.js` of the viewer): `pointerdown`/`pointermove`/`pointerup` on the
canvas; `clientX/Y` minus canvas origin, divided by the display scale
-> panel coordinates -> `fetch("/api/pointer?x=..&y=..&p=..")`. With a WebSocket
(P2) the second channel is dropped: the same session carries the pointer packet
`[flag][x_hi][x_lo][y_hi][y_lo]` (pattern from `lv_port_esp32_web`).

**Thread safety:** LVGL is touched **exclusively** in the read callback in the main thread.
The server thread only pushes tuples into a list under a lock -- the same
discipline as `mcp_screen.request()`.

---

## 4. Measured values on the real board

Board: 192.168.1.168, `gc_free` ~6.0-6.5 MB, `freq 240 MHz`, image source
`Display-Framebuffer 1` (320x480 RGB565, `byte_swap=True`). All measurements **read-only**
(GET + `exec_python` without state change).

### 4.1 Full screen / throughput (`tools/bench_vorschau.py`)

| Call | Bytes | Resolution | Time | Throughput |
|---|---|---|---|---|
| `/screen.raw?scale=1` | 307200 | 320x480 | **0.397-0.602 s**, mean **0.457 s** (n=10) | **657 KB/s**, **~2.2 fps** |
| `/screen.raw?scale=2` | 76800 | 160x240 | **4.6-6.0 s** | ~16 KB/s |
| `/screen.raw?scale=4` | 19200 | 80x120 | 1.19-1.32 s | ~15 KB/s |
| `/screen.raw?scale=8` | 4800 | 40x60 | ~0.39 s | ~12 KB/s |
| `GET /screen` (small) | ~120 | -- | **~0.067 s** | (overhead measurement) |

Reading:

* **`scale=1` is the fastest path** -- it is the pure framebuffer copy plus
  radio link. Every shrinking is **slower**, not faster (4.2).
* Real net rate: **~660-830 KB/s**. That is the bandwidth budget for everything.
* **~67 ms per connection** -- negligible at full screen (400 ms dominates), at
  small delta rectangles the **dominating** item (4.4). Precisely why a
  persistent channel is important for P2.

### 4.2 Why shrinking on the device fails

`mcp_screen._downscale()` runs as a **Python loop over every target pixel**
(line 123-137). `scale=2` = 76800 Python iterations -> **4.6-6.0 s**. Therefore the
`scale=4` path used today in the web interface (~1.2 s/frame) is **not** a good
starting point for a live viewer. For live: **send the full screen raw** and scale
in the browser.

### 4.3 Memory/CPU costs on the board (`exec_python`, computation only)

* **Framebuffer copy** 307200 B (`bytearray(fb)`): **38 ms** -> **8.1 MB/s**
  memory bandwidth. That is the only necessary Python share; it is 12x faster
  than the radio link, so irrelevant.
* **Diff scan in pure Python** (480 rows as a row comparison): **395 ms/frame** ->
  **unusable** for a frame diff. A Python shadow-buffer comparison is therefore
  **not** a viable path.
* **Idle diff** (two full screens 1 s apart): **0 differing pixels** of
  153600. When the UI is static the delta transmission is **0 bytes** -- so the benefit of
  delta rectangles is maximal.
* **Heap:** `gc_free` fluctuated during the benchmark round by ~0.4 MB
  (6.44 -> 6.04 MB, then recovered) -- the full-screen buffers create allocation churn.
  No leak, but reason to reuse send buffers instead of building them anew per frame.
  **Internal SRAM free: ~32 KB** -- very tight.

### 4.4 Delta rectangles: the decisive reuse (key finding)

The running display driver is in **FULL-render mode with full framebuffers**
(`display_driver_framework.py:253`, 2 x 307200 B), and **`_flush_cb(_, area, color_p)`
receives from LVGL the changed rectangle `area`** (`:580`). Exactly the approach of
`LVGLRemoteServer`: **instead of diffing the screen, take the finished rectangle from the flush.**
No Python scan needed, no 395 ms.

Extrapolation of the achievable frame-rate budget at **660 KB/s** (measured
`_flush`-`area` rectangle -> bytes):

| Rectangle | Bytes | Polling (with 67 ms) | **persistent channel** |
|---|---|---|---|
| 320x480 (full screen) | 307200 | 1.9 fps | 2.2 fps |
| 320x240 | 153600 | 3.4 fps | 4.4 fps |
| 320x120 | 76800 | 5.5 fps | 8.8 fps |
| 160x120 | 38400 | 8.1 fps | 17.6 fps |
| 320x40 (counter/label) | 25600 | 9.5 fps | 26.4 fps |
| 80x60 | 9600 | 12.3 fps | 70 fps (LVGL refresh caps it) |

**Conclusion:** full screen = "following/debugging"; typical UI changes via flush rectangle
+ persistent channel = fluid remote control.

---

## 5. Implementation plan in stages

### P0 -- display only, low frame rate (no firmware change in LVGL)

* **New file** `firmware/webfiles/viewer.html` + `viewer.js` (or a tab
  "Screen" in the existing `index.html`). Fetches on a timer
  `fetch("/screen.raw?scale=1", {cache:"no-store"})`, reads `X-Screen` and
  `X-Byte-Swap`, computes RGB565 in the canvas (template: `app.js` `shot()`, line 145-179),
  draws. Do **not** use `scale>1` (4.2).
* **New endpoint** in `mcp_tools.build_routes()`: nothing needed -- `/screen.raw`
  exists. Optionally a `GET /viewer` -> `statisch("viewer.html")` in
  `mcp_webui.build_routes()`.
* **Result:** ~2 fps, display only. Immediately usable, without risk.

### P1 -- input (remote control)

* **New file** `firmware/mcpsrv/mcp_pointer.py` (code from 3.1).
* **`firmware/device/main.py`:** one line `mcp_pointer.create()` after
  `start_touch()` (LVGL thread!). That is the **only** touch of an
  existing file -- deliberately minimal.
* **New endpoint** `GET/POST /api/pointer` in `mcp_webui.build_routes()` +
  `api_pointer()` (3.3).
* **`viewer.js`:** `pointerdown/move/up` -> convert coordinates -> `/api/pointer`.
* **Result:** clicking/dragging in the browser operates the real UI; visible on the panel.

### P2 -- optimisation to changed areas + persistent channel

* **Delta source (firmware, small):** tap the display flush without duplicating
  LVGL. Most elegant variant: **extend** `axs15231b.AXS15231B._flush_cb` or the
  `display_driver_framework` flush with a hook that passes the `area` +
  `color_p` region to `mcp_screen` (e.g. `mcp_screen.push_region(x1,y1,x2,y2, view)`).
  The driver lies in `firmware/device/drivers/axs15231b.py` (already forked) or
  `display_driver_framework.py`. Note: run the hook **in the LVGL thread**, only
  copy/store.
* **Channel:** `websocket` extmod + `asyncio` on its own port (e.g. 81, route `/ws`),
  additive next to `mcp_httpd` -- so the existing server stays untouched. Handshake
  with `hashlib.sha1().digest()` + `ubinascii.b2a_base64()`; binary frames
  `[x1][y1][x2][y2][rgb565...]` (pattern `lv_port_esp32_web`); pointer return packet on
  the same line.
  Fallback variant without WebSocket: long-lived `GET` response with
  `[4 byte length][Frame]` prefix; for that `mcp_httpd` must pass the socket through
  to the handler.
* **Browser:** draw canvas delta (`ctx.putImageData(img, x1, y1)`), only the
  received rectangle.
* **Result:** idle = 0 bytes; typical UI changes ~8-26 fps (4.4).

### Affected / new files at a glance

| File | Stage | Kind |
|---|---|---|
| `firmware/webfiles/viewer.html`, `viewer.js` | P0 | **new** |
| `firmware/webfiles/app.js` (tab) | P0 | existing (optional) |
| `firmware/mcpsrv/mcp_pointer.py` | P1 | **new** |
| `firmware/device/main.py` | P1 | existing (one line) |
| `firmware/mcpsrv/mcp_webui.py` (`/api/pointer`) | P1 | existing (additive) |
| `firmware/mcpsrv/mcp_screen.py` (`push_region`) | P2 | existing (additive) |
| `firmware/device/drivers/axs15231b.py` / `display_driver_framework.py` (flush hook) | P2 | existing (small) |
| `firmware/mcpsrv/mcp_ws.py` (WS server, port 81) | P2 | **new** |
| `tools/bench_vorschau.py` | measurement | **new** (already created) |

---

## 6. Risks and open points

* **Thread safety (biggest danger).** LVGL may **only** be touched in the main thread.
  The pointer callback runs there (good); the queue is shared via a lock.
  Any shortcut -- e.g. `lv.obj` calls from the server thread -- leads to
  sporadic crashes. Keep the discipline as with `mcp_screen.request()`.
* **Memory.** A 307200-byte send buffer must lie in **PSRAM**; the **internal
  SRAM at ~32 KB free** is practically full. With several viewers (up to 4 workers)
  compute beforehand: 4 x full-screen buffer = ~1.2 MB -- doable in PSRAM, impossible in
  internal SRAM. **Reuse** buffers (churn measured: ~0.4 MB per round).
* **LVGL invalidate/flush behaviour.** The delta benefit depends on the
  flush `area` **really being small**. With **full-screen refresh** (this panel needs
  a full frame rebuild with chunked transfer over `SPIBusFast`) the
  `area` can turn out **large** -- then the delta advantage shrinks. **Measure** before P2:
  log the size of the `flush` `area` for typical UI changes. If it is
  permanently ~full screen, only full-screen push (2.2 fps) or SCALE in the browser remains.
* **Tearing / consistency.** The capture reads the framebuffer **while** LVGL
  writes. Irrelevant for preview, but important for delta rectangles from the flush:
  there, copy the buffer **at the flush moment**, not later from the
  framebuffer (otherwise the rectangle tears). The flush `color_p` view is the right
  place.
* **Connection overhead (67 ms).** With polling it limits small deltas hard
  (12 fps ceiling for 80x60). Either a **persistent channel** (P2) or deliberately
  **full screen @ 2 fps**.
* **WebSocket effort.** Handshake and socket passing are manual work; `asyncio`
  and the radio driver share the CPU. If a session permanently occupies a worker,
  the number of simultaneous debug connections drops -- run port 81/`/ws` separately
  so that the debug server stays reachable.
* **Supervision.** `mcp_serve._aufsicht` restarts only the **own** listener. A
  second WS listener needs the same supervision, otherwise it dies silently (known
  pattern: board pings, but port dead).
* **No authentication.** As with the existing interface: arbitrary code executable from the
  network, now **plus** active operation of the panel. Only a trusted
  LAN; ideally an emergency-off lock ("remote control off").
* **Open question, frame-rate perception.** The browser only draws as often as `requestAnimationFrame`
  runs (60 Hz) -- the real ceiling is set by the network. At full screen ~2 fps are to be expected
  in the still image; for animations (progress bars) only P2 delivers fluidity.

---

## Appendix: raw measurement data

```
copy 307200 bytes: 37957 us (8.09 MB/s)           # bytearray(frame_buffer1)
scan 480 rows (307200 B): 395049 us               # pure Python row comparison
gc_free=6313760 gc_alloc=410336                   # during measurement
internal heap free: ~32031 bytes

scale=1 x10: 0.602 0.423 0.428 0.407 0.592 0.431 0.428 0.432 0.397 0.429
             mean 0.457 s -> 2.19 fps, ~657 KB/s
scale=2 x3 : 6.048 4.606 4.621 s
scale=4 x3 : 1.187 1.199 1.324 s
scale=8 x3 : 0.391 0.381 0.387 s
GET /screen x10: mean 0.067 s

idle diff (2 frames, 1 s apart): 0 changed pixels / 153600

Board features: websocket(extmod, framing)  asyncio: ok  hashlib.sha1().digest(): ok
                ubinascii.b2a_base64: ok     _thread.allocate_lock: ok
                deflate.DeflateIO: present
Display: FULL-render mode, 2 x 307200-B framebuffers, _flush_cb receives area=rectangle
```
