# MCP debug server on the ESP32

Goal: the agent should be able to debug and test the board **itself** — see screenshots,
run code, read logs, write files, restart the board — without someone sitting next to it
holding a terminal.

## Structure

`firmware/mcpsrv/` (flat modules so they can be frozen easily on the device):

| File | Task |
|---|---|
| `mcp_serve.py` | entry point: builds MCP server + router, starts the HTTP server in a `_thread` |
| `mcp_protocol.py` | MCP/JSON-RPC core: `initialize`, `notifications/initialized`, `tools/list`, `tools/call`, `ping`; text/image results; Base64 |
| `mcp_httpd.py` | minimal HTTP/1.1 server (sockets, no third-party library), request parser, response writer, SSE writer |
| `mcp_tools.py` | tool definitions + plaintext endpoints |
| `mcp_screen.py` | image source: attached framebuffer (primary) or LVGL snapshot (fallback), downscaling, widget tree |
| `mcp_png.py` | RGB565 → PNG, without a third-party library (real deflate if `deflate` is present, otherwise valid stored blocks) |
| `mcp_logbuf.py` | stdout capture into a ring buffer (tee) |

## Endpoints

MCP (Streamable HTTP, one endpoint):

```
POST /mcp        JSON-RPC 2.0; response as application/json,
                 on request (Accept: text/event-stream) as SSE
```

Plaintext in addition — faster than MCP for iteration via `curl`:

```
GET  /               status + tool list
GET  /screen.png     screenshot (?scale=2 shrinks, ?format=raw = RGB565)
GET  /log            last console output (?clear=1 empties the buffer)
POST /exec           run a Python body on the device
GET  /info           device info (JSON)
POST /reset          restart (delayed)
```

## Tools

| Tool | Purpose |
|---|---|
| `screenshot(scale, format)` | **screen as PNG** — the most important tool for UI work |
| `exec_python(code)` | run code on the device, return stdout + log excerpt |
| `files(action, path, data)` | `list`, `read`, `write`, `remove`, `mkdir`, `stat`, `df` |
| `device_info()` | chip, frequency, memory, Wi-Fi status, uptime, image source |
| `logs(clear)` | console output |
| `lvgl_tree(max_nodes)` | widget tree of the active screen (classes, geometry, text) |
| `i2c_scan(sda, scl, freq)` | board bring-up, find touch controller |
| `wifi(action, ssid, password)` | `status`, `scan`, `connect`, `disconnect` |
| `reset(delay_ms)` | restart |

## Host tests (without hardware)

```bash
python3 tests/test_mcpsrv.py
```

49 checks: PNG encoding (chunk CRC, scanlines, byte order), MCP/JSON-RPC
(version negotiation, notifications, error paths), HTTP layer (parsing, `Content-Length`),
and an end-to-end run over real sockets (initialize → tools/list →
tools/call screenshot → PNG decoded and checked, `/screen.png`, `/exec`, 202 for
notifications, SSE response, 404).

## Verified on the device (MicroPython)

Measured on the board and therefore implemented this way:

- **LVGL is not thread-safe.** Snapshots and the widget tree run as a request via
  `mcp_screen.request(...)`; the main loop runs them with
  `mcp_screen.service_requests()`. Results are stored **per request number** in
  `_RESULTS` — otherwise a late result corrupted the next request
  (exactly that was observed). Timeout 20 s, because a snapshot takes 1.6 s (scale=4) to
  several seconds (scale=1).
- **One connection must not block the accept loop.** `HttpServer` serves
  each connection in its own thread (max. 3). Before, a single hanging
  handler paralysed the whole server (responses never arrived).
- **`_thread.start_new_thread(fn, args)`** — in MicroPython the third parameter is
  *kwargs*, not the stack size. Stack size globally via `_thread.stack_size(n)`;
  a numeric value as the third argument makes the thread fail silently.
- **`socket` has no `flush()`** — `write_response` now checks for it.
- **`sys.stdout` can be missing** (`mcp_logbuf.install()` no longer aborts) and
  **`bytes.decode()` takes `errors` only positional**
  (`bytes.decode()` → `TypeError: function doesn't take keyword arguments`).
- **Snapshot API** (LVGL 9.4 in the binding): `lv.snapshot_take(obj, lv.COLOR_FORMAT.RGB565)`
  returns `lv_draw_buf_t`; dimensions via `.header.w/.h/.stride` (`.cf = 18` = RGB565),
  data via `.data` as `C_Array` → with `__dereference__(size)` into a `memoryview`,
  downscale directly from that, and only then `snap.destroy()`.
- **`deflate` is present** (real PNG compression usable), `zlib` is missing; the
  PNG encoder has a stored-block fallback for that.
- **Pass KeyboardInterrupt through**: in MicroPython it inherits from `Exception`; a
  blanket `except Exception` in the main loop makes the board unreachable for Ctrl-C and
  therefore for `mpremote`.
- **scale=2 is the default for screenshots** (160×240): full-res takes so long on the ESP32
  that the HTTP client times out.

## Operation on the device (planned)

1. Call `mcp_serve.start()` after the Wi-Fi connect (from `main.py`).
2. The LVGL app attaches its framebuffer: `mcp_screen.attach(buf, w, h, byte_swap=True)`.
   Without `attach` the server tries an LVGL snapshot — its API differs per binding version,
   hence the defensive path.
3. On the server: `hermes mcp add esp32 --url http://<ip>/mcp`.
4. Check reachability: `curl -s http://<ip>/`, then `curl -s -X POST http://<ip>/mcp -d ...`.

## Open points (to verify on hardware)

- Whether Hermes' MCP client accepts the `application/json` response mode or requires SSE
  (both response types are implemented).
- LVGL `snapshot_take` API of the built binding (fallback path).
- Whether LVGL calls from the server thread are allowed; if not, LVGL actions
  run via a queue processed in the main thread (LVGL task).
- Power supply/clock of the QSPI panel during full refresh.
