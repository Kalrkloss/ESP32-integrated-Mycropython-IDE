# Tool definitions of the debug MCP server.
# All hardware accesses happen in try/except: if a module is missing (e.g. in a host
# test), the tool returns a readable error message instead of crashing.

import sys
import time

import mcp_png
import mcp_screen
import mcp_logbuf
from mcp_protocol import Tool, b64


def _json_ok(**kw):
    return kw


def tool_screenshot(scale=1, format="png"):
    """Screen as an image. format: png|raw, scale: 1,2,4 (sampling)."""
    data, w, h, swap = mcp_screen.capture(scale=scale)
    if format == "raw":
        return {"content": [
            {"type": "text", "text": "raw RGB565 %dx%d byte_swap=%s, %d bytes "
                                     "(endpoint /screen.raw?scale=%s)" % (w, h, swap, len(data), scale)}]}
    blob = mcp_png.encode_rgb565_png(data, w, h, byte_swap=swap)
    return {"content": [
        {"type": "image", "data": b64(blob), "mimeType": "image/png"},
        {"type": "text", "text": "screenshot %dx%d (scale=%s), PNG %d bytes, buffer: %s"
                                 % (w, h, scale, len(blob), mcp_screen.describe())}]}


def tool_exec(code):
    """Run Python code on the device and return the output.

    `print` is replaced in the namespace of the code: MicroPython writes with `print`
    directly to the C stdout (not via sys.stdout), so a capture there would see
    nothing. Output of `print(...)` is collected here and returned.
    """
    lines = []

    def _print(*args, **kwargs):
        sep = kwargs.get("sep", " ")
        end = kwargs.get("end", "\n")
        lines.append(sep.join(str(a) for a in args) + end)

    namespace = {"__name__": "__mcp__", "print": _print}
    ok = True
    err = None
    started = time.time()
    try:
        exec(compile(code, "<mcp>", "exec"), namespace)
    except Exception as exc:  # noqa: BLE001
        ok = False
        err = "%s: %s" % (type(exc).__name__, exc)
    took = int((time.time() - started) * 1000)

    out = "".join(lines)
    if err:
        out += ("\n" if out and not out.endswith("\n") else "") + "ERROR: " + err
    out += "\n[exec %s in %d ms]" % ("ok" if ok else "failed", took)
    return out


def tool_files(action="list", path="/", data=None, encoding="utf-8"):
    import os
    action = (action or "list").lower()
    if action == "list":
        try:
            names = os.listdir(path)
        except OSError as exc:
            return "listdir(%s) failed: %s" % (path, exc)
        rows = []
        for name in sorted(names):
            full = path.rstrip("/") + "/" + name
            try:
                st = os.stat(full)
                rows.append("%9d  %s%s" % (st[6], name, "/" if st[0] & 0x4000 else ""))
            except OSError:
                rows.append("        ?  %s" % name)
        return "\n".join(rows) or "(empty)"
    if action == "read":
        with open(path, "r" if encoding else "rb") as fh:
            return fh.read()
    if action == "write":
        if data is None:
            return "data missing"
        with open(path, "w" if encoding else "wb") as fh:
            fh.write(data)
        return "written: %s (%d characters)" % (path, len(data))
    if action == "remove":
        try:
            os.remove(path)
            return "deleted: %s" % path
        except OSError as exc:
            return "remove failed: %s" % exc
    if action == "mkdir":
        try:
            os.mkdir(path)
            return "created: %s" % path
        except OSError as exc:
            return "mkdir failed: %s" % exc
    if action == "stat":
        try:
            st = os.stat(path)
            return "mode=%o size=%d" % (st[0], st[6])
        except OSError as exc:
            return "stat failed: %s" % exc
    if action == "df":
        try:
            st = os.statvfs("/")
            return "free=%d bytes of %d" % (st[0] * st[3], st[0] * st[2])
        except OSError as exc:
            return "statvfs failed: %s" % exc
    return "unknown action: %s" % action


def tool_device_info():
    info = {"board": "JC3248W535 (ESP32-S3, 16MB Flash, 8MB PSRAM)"}
    try:
        import machine
        info["freq_mhz"] = machine.freq() // 1000000
        info["unique_id"] = "".join("%02x" % b for b in machine.unique_id())
        try:
            info["reset_cause"] = machine.reset_cause()
            info["wake_reason"] = machine.wake_reason()
        except Exception:
            pass
    except ImportError:
        info["machine"] = "not available (host test?)"
    try:
        import gc
        if hasattr(gc, "mem_free"):
            info["gc_free"] = gc.mem_free()
            info["gc_alloc"] = gc.mem_alloc()
    except ImportError:
        pass
    try:
        import esp32
        info["heap_free_internal"] = esp32.idf_heap_info(esp32.HEAP_DATA)[0][3]
    except Exception:
        pass
    try:
        import network
        sta = network.WLAN(network.STA_IF)
        info["wifi"] = {"connected": sta.isconnected(), "ifconfig": sta.ifconfig()}
    except Exception:
        info["wifi"] = "not available"
    info["screen"] = mcp_screen.describe()
    info["uptime_s"] = time.time()
    return _json_ok(**info)


def tool_logs(clear=False):
    return mcp_logbuf.logs(clear=clear) or "(no log)"


def tool_lvgl_tree(max_nodes=60):
    return mcp_screen.lvgl_tree(max_nodes=max_nodes)


def tool_i2c_scan(sda=21, scl=20, freq=100000):
    try:
        import machine
        bus = machine.I2C(0, sda=machine.Pin(sda), scl=machine.Pin(scl), freq=freq)
        found = ["0x%02x" % a for a in bus.scan()]
        return "I2C sda=%d scl=%d: %s" % (sda, scl, ", ".join(found) or "(nothing)")
    except Exception as exc:  # noqa: BLE001
        return "I2C scan failed: %s" % exc


def tool_reset(delay_ms=300, hard=False):
    def _do():
        time.sleep(delay_ms / 1000.0)
        try:
            import machine
            machine.reset() if not hard else machine.hard_reset()
        except Exception:
            pass
    try:
        import _thread
        _thread.start_new_thread(_do, ())
        return "reset triggered in %d ms" % delay_ms
    except ImportError:
        return "no _thread: reset not triggered"


def tool_wifi(action="status", ssid=None, password=None):
    try:
        import network
    except ImportError:
        return "network not available"
    sta = network.WLAN(network.STA_IF)
    action = (action or "status").lower()
    if action == "status":
        return "connected=%s %s" % (sta.isconnected(), sta.ifconfig())
    if action == "scan":
        nets = sta.scan()
        return "\n".join("%-24s ch=%3d rssi=%4d auth=%d" % (
            n[0].decode() if isinstance(n[0], bytes) else n[0], n[2], n[3], n[4]) for n in nets)
    if action == "connect":
        if not ssid:
            return "ssid missing"
        sta.active(True)
        sta.connect(ssid, password)
        for _ in range(40):
            if sta.isconnected():
                return "connected: %s" % (sta.ifconfig(),)
            time.sleep(0.25)
        return "connection to %s did not come up" % ssid
    if action == "disconnect":
        sta.disconnect()
        return "disconnected"
    return "unknown action: %s" % action


def build_tools():
    return [
        Tool("screenshot",
             "Screenshot of the LVGL display as a PNG image (or as a raw buffer). "
             "scale=2 halves the resolution, scale=4 quarters it.",
             {"type": "object", "properties": {
                 "scale": {"type": "integer", "minimum": 1, "maximum": 8},
                 "format": {"type": "string", "enum": ["png", "raw"]}},
              "additionalProperties": False},
             lambda scale=1, format="png": tool_screenshot(scale, format)),
        Tool("exec_python",
             "Runs Python code on the device and returns stdout (incl. a log excerpt). "
             "Runs in the server thread -- LVGL calls may be unsafe.",
             {"type": "object", "properties": {"code": {"type": "string"}},
              "required": ["code"], "additionalProperties": False},
             lambda code: tool_exec(code)),
        Tool("files",
             "Files on the device: list, read, write, remove, mkdir, stat, df.",
             {"type": "object", "properties": {
                 "action": {"type": "string",
                            "enum": ["list", "read", "write", "remove", "mkdir", "stat", "df"]},
                 "path": {"type": "string"},
                 "data": {"type": "string"},
                 "encoding": {"type": "string"}},
              "required": ["action"], "additionalProperties": False},
             lambda action="list", path="/", data=None, encoding="utf-8":
                 tool_files(action, path, data, encoding)),
        Tool("device_info",
             "Chip, memory, WLAN status, uptime and image source.",
             {"type": "object", "properties": {}, "additionalProperties": False},
             lambda: tool_device_info()),
        Tool("logs", "Last console output of the device.",
             {"type": "object", "properties": {"clear": {"type": "boolean"}},
              "additionalProperties": False},
             lambda clear=False: tool_logs(clear)),
        Tool("lvgl_tree", "Widget tree of the active LVGL screen (classes, position, size, text).",
             {"type": "object", "properties": {"max_nodes": {"type": "integer"}},
              "additionalProperties": False},
             lambda max_nodes=60: tool_lvgl_tree(max_nodes)),
        Tool("i2c_scan", "Scan the I2C bus (board bring-up, find the touch controller).",
             {"type": "object", "properties": {
                 "sda": {"type": "integer"}, "scl": {"type": "integer"},
                 "freq": {"type": "integer"}},
              "additionalProperties": False},
             lambda sda=21, scl=20, freq=100000: tool_i2c_scan(sda, scl, freq)),
        Tool("wifi", "WLAN: status, scan, connect (ssid/password), disconnect.",
             {"type": "object", "properties": {
                 "action": {"type": "string", "enum": ["status", "scan", "connect", "disconnect"]},
                 "ssid": {"type": "string"}, "password": {"type": "string"}},
              "additionalProperties": False},
             lambda action="status", ssid=None, password=None: tool_wifi(action, ssid, password)),
        Tool("reset", "Reboot the device (delayed so the reply still gets out).",
             {"type": "object", "properties": {"delay_ms": {"type": "integer"}},
              "additionalProperties": False},
             lambda delay_ms=300: tool_reset(delay_ms)),
    ]


def build_routes(mcp_handler):
    """Additional plain-text endpoints -- faster than MCP for iteration with curl."""
    from mcp_httpd import text, json_response, Response

    def screenshot_route(req):
        scale = req.arg("scale", "1")
        fmt = req.arg("format", "png")
        data, w, h, swap = mcp_screen.capture(scale=int(scale))
        if fmt == "raw":
            return Response(200, bytes(data), {"Content-Type": "application/octet-stream",
                                               "X-Screen": "%dx%d" % (w, h)})
        blob = mcp_png.encode_rgb565_png(data, w, h, byte_swap=swap)
        return Response(200, blob, {"Content-Type": "image/png", "Cache-Control": "no-store"})

    def screenshot_raw_route(req):
        """Raw buffer without PNG encoding. Encoding in pure Python costs seconds to
        minutes on this board -- for the web UI the buffer is therefore transferred
        raw and converted into an image in the browser."""
        scale = int(req.arg("scale", "2"))
        data, w, h, swap = mcp_screen.capture(scale=scale)
        return Response(200, bytes(data), {"Content-Type": "application/octet-stream",
                                           "X-Screen": "%dx%d" % (w, h),
                                           "X-Byte-Swap": "1" if swap else "0",
                                           "Cache-Control": "no-store"})

    def log_route(req):
        return text(200, mcp_logbuf.logs(clear=req.arg("clear") == "1"))

    def exec_route(req):
        code = req.body.decode() if req.body else req.arg("code", "")
        if not code:
            return text(400, "body or ?code= missing")
        return json_response({"result": tool_exec(code)})

    def info_route(req):
        info = tool_device_info()
        info["screen_status"] = mcp_screen.status()
        return json_response(info)

    def screen_route(req):
        return json_response({"screen": mcp_screen.describe(), "attached": mcp_screen.attached()})

    def reset_route(req):
        return json_response({"result": tool_reset(500)})

    def status_route(req):
        return text(200, "esp32 mcp debug server\n%s\ntools:\n%s" % (
            mcp_screen.describe(),
            "\n".join("  %s" % t.name for t in build_tools())))

    return {
        "POST /mcp": mcp_handler,
        "GET /": status_route,
        "GET /screen.png": screenshot_route,
        "GET /screen.raw": screenshot_raw_route,
        "GET /log": log_route,
        "POST /exec": exec_route,
        "GET /info": info_route,
        "GET /screen": screen_route,
        "POST /reset": reset_route,
    }
