# Image source for the debug MCP server.
#
# Important constraint: LVGL is NOT thread-safe. The MCP server runs in its own
# thread, but LVGL in the main loop. That is why all LVGL accesses (snapshot,
# widget tree) run as a job via `request(...)`:
# The server thread posts the job and waits (with a timeout), the main loop
# executes it and stores the result. Without a timeout a stuck job would block the
# entire server loop.
#
# In addition the app can register a framebuffer (attach); then it is read directly
# from there, without touching LVGL.

import time

_STATE = {
    "buffer": None,
    "width": 0,
    "height": 0,
    "byte_swap": True,
    "label": None,
}

# Job storage between the server thread and the LVGL thread.
# Results are kept per job number in _RESULTS -- a job that finishes late cannot
# thus falsify the result of the next job.
_REQ = {
    "seq": 0,        # number of the last job
    "done": 0,       # number of the last completed job
    "kind": None,
    "scale": 1,
    "max_nodes": 60,
}
_RESULTS = {}


# --------------------------------------------------------------------------
# Framebuffer registration (optional)
# --------------------------------------------------------------------------

def attach(buffer, width, height, byte_swap=True, label=None):
    _STATE["buffer"] = buffer
    _STATE["width"] = int(width)
    _STATE["height"] = int(height)
    _STATE["byte_swap"] = bool(byte_swap)
    _STATE["label"] = label
    return _STATE


def detach():
    attach(None, 0, 0)


def attached():
    return _STATE["buffer"] is not None


def describe():
    if attached():
        return "%dx%d RGB565 byte_swap=%s (%s)" % (
            _STATE["width"], _STATE["height"], _STATE["byte_swap"],
            _STATE["label"] or "unnamed")
    return "snapshot via LVGL (no framebuffer attached)"


# --------------------------------------------------------------------------
# Jobs to the LVGL thread
# --------------------------------------------------------------------------

def request(kind, timeout_ms=20000, **kwargs):
    """Job to the LVGL thread. Raises RuntimeError on timeout or error.

    Default timeout 20 s: a full-resolution snapshot takes several seconds on the
    ESP32 -- the server thread may wait that long because each connection has its
    own thread."""
    _REQ["kind"] = kind
    for key, value in kwargs.items():
        _REQ[key] = value
    _REQ["seq"] += 1
    target = _REQ["seq"]
    waited = 0
    while _REQ["done"] < target:
        time.sleep_ms(10)
        waited += 10
        if waited >= timeout_ms:
            raise RuntimeError(
                "timeout after %d ms: LVGL thread did not execute '%s' "
                "(is the main loop running service_requests()?)" % (timeout_ms, kind))
    entry = _RESULTS.pop(target, None)
    if entry is None:
        raise RuntimeError("job %d left no result" % target)
    error, result = entry
    if error:
        raise RuntimeError(error)
    return result


def service_requests():
    """Must be called in the LVGL loop (main thread). Returns True
    if a job was executed."""
    if _REQ["kind"] is None or _REQ["done"] >= _REQ["seq"]:
        return False
    target = _REQ["seq"]
    kind = _REQ["kind"]
    try:
        if kind == "snapshot":
            result = _snapshot(_REQ["scale"])
        elif kind == "lvgl_tree":
            result = _lvgl_tree(_REQ["max_nodes"])
        else:
            raise RuntimeError("unknown job: %s" % kind)
        _RESULTS[target] = (None, result)
    except Exception as exc:  # noqa: BLE001
        _RESULTS[target] = ("%s: %s" % (type(exc).__name__, exc), None)
    _REQ["done"] = target
    _REQ["kind"] = None
    return True


# --------------------------------------------------------------------------
# Images
# --------------------------------------------------------------------------

def _downscale(data, width, height, factor):
    """Pixel sampling (every factor-th pixel) -- sufficient for debug views."""
    if factor <= 1:
        return data, width, height
    nw, nh = width // factor, height // factor
    out = bytearray(nw * nh * 2)
    o = 0
    for y in range(nh):
        base = (y * factor) * width * 2
        for x in range(nw):
            src = base + (x * factor) * 2
            out[o] = data[src]
            out[o + 1] = data[src + 1]
            o += 2
    return out, nw, nh


def _snapshot(scale=1):
    """LVGL snapshot of the active screen. Returns: (bytes, w, h, byte_swap).

    Verified API (lvgl_micropython, LVGL 9.4):
      lv.snapshot_take(obj, lv.COLOR_FORMAT.RGB565) -> lv_draw_buf_t
      header: .w .h .stride .cf     data: .data (C_Array, via __dereference__)
    No intermediate copying: the downscale happens directly on the view (memoryview)
    before the snapshot is released.
    """
    import lvgl as lv

    snap = lv.snapshot_take(lv.screen_active(), lv.COLOR_FORMAT.RGB565)
    try:
        header = snap.header
        width = int(header.w)
        height = int(header.h)
        stride = int(header.stride)
        row_bytes = width * 2
        size = row_bytes * height

        view = snap.data
        deref = getattr(view, "__dereference__", None)
        if deref is not None:
            view = deref(size if stride == row_bytes else stride * height)

        factor = int(scale)
        if stride != row_bytes:
            view = _pack_rows(view, width, height, stride)
        data, width, height = _downscale(view, width, height, factor)
    finally:
        try:
            snap.destroy()
        except Exception:  # noqa: BLE001
            pass

    return bytes(data), width, height, True


def _pack_rows(view, width, height, stride):
    """Tightly pack rows from a padded buffer (stride != row width)."""
    row_bytes = width * 2
    packed = bytearray(row_bytes * height)
    offset = 0
    for row in range(height):
        start = row * stride
        packed[offset:offset + row_bytes] = view[start:start + row_bytes]
        offset += row_bytes
    return packed


def capture(scale=1):
    """Returns: (data, width, height, byte_swap). Raises RuntimeError with a reason."""
    if attached():
        width, height = _STATE["width"], _STATE["height"]
        data = bytearray(_STATE["buffer"])
        swap = _STATE["byte_swap"]
        data, width, height = _downscale(data, width, height, int(scale))
        return data, width, height, swap

    data, width, height, swap = request("snapshot", scale=int(scale))
    if data is None:
        raise RuntimeError("snapshot returned no data")
    return data, width, height, swap


def attach_framebuffer(which=1):
    """Register the display's framebuffer -- capture without an LVGL snapshot.

    A snapshot costs 3 to 20 s on this board depending on the scale (LVGL snapshot
    plus PNG encoding in pure Python; at scale 2 it even runs into the timeout).
    With a registered framebuffer, `capture` reads directly from it.
    Tearing is possible because LVGL writes in parallel -- irrelevant for previews.
    """
    try:
        import display_config
    except ImportError as exc:
        return "display_config not available (%s)" % exc
    display = getattr(display_config, "LAST_DISPLAY", None)
    if display is None:
        return "no display registered -- framebuffer not available"
    buffer = getattr(display, "_frame_buffer2" if int(which) == 2 else "_frame_buffer1", None)
    if buffer is None:
        return "display has no framebuffer %s" % which
    return describe_after_attach(buffer, which)


def describe_after_attach(buffer, which):
    import display_config
    attach(buffer, display_config.WIDTH, display_config.HEIGHT, byte_swap=True,
           label="display framebuffer %s" % which)
    return describe()


# --------------------------------------------------------------------------
# Widget tree
# --------------------------------------------------------------------------

def lvgl_tree(max_nodes=60):
    """Widget tree of the active screen (runs in the LVGL thread)."""
    return request("lvgl_tree", max_nodes=int(max_nodes))


def _lvgl_tree(max_nodes=60):
    try:
        import lvgl as lv
    except ImportError:
        return "lvgl not available"
    lines = []
    try:
        root = lv.screen_active()
    except Exception as exc:  # noqa: BLE001
        return "screen_active() failed: %s" % exc
    stack = [(root, 0)]
    while stack and len(lines) < max_nodes:
        obj, depth = stack.pop()
        try:
            name = type(obj).__name__
        except Exception:  # noqa: BLE001
            name = "?"
        try:
            geom = "x=%d y=%d w=%d h=%d" % (obj.get_x(), obj.get_y(),
                                            obj.get_width(), obj.get_height())
        except Exception:  # noqa: BLE001
            geom = "geom unknown"
        extra = ""
        try:
            extra = " text=%r" % obj.get_text()
        except Exception:  # noqa: BLE001
            pass
        lines.append("%s%s [%s] %s%s" % ("  " * depth, name, hex(id(obj) & 0xFFFFFF),
                                         geom, extra))
        try:
            for idx in range(obj.get_child_count() - 1, -1, -1):
                stack.append((obj.get_child(idx), depth + 1))
        except Exception:  # noqa: BLE001
            pass
    if stack:
        lines.append("... (%d more nodes)" % len(stack))
    return "\n".join(lines) if lines else "(empty)"


def status():
    """Short report for /info and /screen."""
    return {
        "source": "framebuffer" if attached() else "lvgl-snapshot",
        "detail": describe(),
        "pending": _REQ["seq"] - _REQ["done"],
        "results_open": len(_RESULTS),
    }
