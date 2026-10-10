# Bildschirm-Capture fuer den Debug-MCP-Server.
# Primaerer Weg: die App haengt ihren Framebuffer an (attach) -- dann lesen wir ihn direkt.
# Fallback: LVGL-Snapshot, falls vorhanden. Alle LVGL-Zugriffe sind defensiv, weil die
# Binding-API je Version abweicht; Fehler werden als Text zurueckgegeben, nicht als Absturz.

_STATE = {
    "buffer": None,
    "width": 0,
    "height": 0,
    "byte_swap": True,
    "label": None,
}


def attach(buffer, width, height, byte_swap=True, label=None):
    """Framebuffer der Anzeige bekanntmachen (memoryview/bytearray in PSRAM)."""
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
    if not attached():
        return "kein Framebuffer angehaengt"
    return "%dx%d RGB565 byte_swap=%s (%s)" % (
        _STATE["width"], _STATE["height"], _STATE["byte_swap"],
        _STATE["label"] or "unbenannt")


def _region(buffer, width, height, x, y, w, h, bpp=2):
    """Rechteck aus dem Framebuffer schneiden (Zeilenweise kopieren)."""
    out = bytearray(w * h * bpp)
    stride = width * bpp
    o = 0
    for row in range(h):
        src = (y + row) * stride + x * bpp
        out[o:o + w * bpp] = bytes(buffer[src:src + w * bpp])
        o += w * bpp
    return out


def _downscale(data, width, height, factor):
    """Einfaches Pixel-Sampling (jeder factor-te Pixel). Fuer Debug-Ansichten ausreichend."""
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


def capture(scale=1):
    """Rueckgabe: (data, width, height, byte_swap). Wirft RuntimeError mit Begruendung."""
    if not attached():
        data, w, h, swap = _capture_snapshot()
    else:
        w, h = _STATE["width"], _STATE["height"]
        data = _STATE["buffer"]
        swap = _STATE["byte_swap"]
    if data is None:
        raise RuntimeError("keine Bildquelle: Framebuffer nicht angehaengt und "
                           "kein LVGL-Snapshot verfuegbar")
    try:
        factor = int(scale)
    except (TypeError, ValueError):
        factor = 1
    if factor > 1:
        data, w, h = _downscale(data, w, h, factor)
    return data, w, h, swap


def _capture_snapshot():
    """LVGL-Snapshot als Fallback. Gibt (data, w, h, swap) oder (None, 0, 0, True)."""
    try:
        import lvgl as lv
    except ImportError:
        return None, 0, 0, True
    take = getattr(lv, "snapshot_take", None)
    if take is None:
        return None, 0, 0, True
    try:
        scr = lv.screen_active()
        snap = take(scr, lv.COLOR_FORMAT.RGB565)
        data = None
        for attr in ("buf", "data", "buffer"):
            data = getattr(snap, attr, None)
            if data is not None:
                break
        if data is None:
            try:
                data = snap
            except Exception:
                data = None
        w = h = 0
        for attr in ("width", "w"):
            w = getattr(snap, attr, None) or w
        for attr in ("height", "h"):
            h = getattr(snap, attr, None) or h
        if not w or not h:
            try:
                area = snap.dsc.header
                w, h = area.w, area.h
            except Exception:
                return None, 0, 0, True
        return data, int(w), int(h), True
    except Exception:
        return None, 0, 0, True


def lvgl_tree(max_nodes=60):
    """Widget-Baum der aktiven Screen als Text -- zum Debuggen des Layouts."""
    try:
        import lvgl as lv
    except ImportError:
        return "lvgl nicht verfuegbar"
    lines = []
    try:
        root = lv.screen_active()
    except Exception as exc:
        return "screen_active() fehlgeschlagen: %s" % exc
    stack = [(root, 0)]
    while stack and len(lines) < max_nodes:
        obj, depth = stack.pop()
        try:
            name = type(obj).__name__
        except Exception:
            name = "?"
        try:
            x, y, w, h = obj.get_x(), obj.get_y(), obj.get_width(), obj.get_height()
            geom = "x=%d y=%d w=%d h=%d" % (x, y, w, h)
        except Exception:
            geom = "geom unbekannt"
        extra = ""
        try:
            extra = " text=%r" % obj.get_text()
        except Exception:
            pass
        lines.append("%s%s [%s] %s%s" % ("  " * depth, name, hex(id(obj) & 0xFFFFFF), geom, extra))
        try:
            count = obj.get_child_count()
            for idx in range(count - 1, -1, -1):
                stack.append((obj.get_child(idx), depth + 1))
        except Exception:
            pass
    if stack:
        lines.append("... (%d weitere Knoten)" % len(stack))
    return "\n".join(lines) if lines else "(leer)"
