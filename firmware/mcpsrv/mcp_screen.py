# Bildquelle fuer den Debug-MCP-Server.
#
# Wichtige Randbedingung: LVGL ist NICHT thread-sicher. Der MCP-Server laeuft in
# einem eigenen Thread, LVGL aber in der Hauptschleife. Deshalb laufen alle
# LVGL-Zugaenge (Snapshot, Widget-Baum) als Auftrag ueber `request(...)`:
# Der Server-Thread legt den Auftrag ab und wartet (mit Timeout), die Hauptschleife
# fuehrt ihn aus und legt das Ergebnis ab. Ohne Timeout wuerde ein haengender
# Auftrag die gesamte Server-Schleife blockieren.
#
# Zusaetzlich kann die App einen Framebuffer anmelden (attach); dann wird direkt
# daraus gelesen, ohne LVGL anzufassen.

import time

_STATE = {
    "buffer": None,
    "width": 0,
    "height": 0,
    "byte_swap": True,
    "label": None,
}

# Auftragsspeicher zwischen Server-Thread und LVGL-Thread.
# Ergebnisse liegen pro Auftragsnummer in _RESULTS -- ein verzoegert fertig werdender
# Auftrag kann so nicht das Ergebnis des naechsten Auftrags verfaelschen.
_REQ = {
    "seq": 0,        # Nummer des letzten Auftrags
    "done": 0,       # Nummer des zuletzt erledigten Auftrags
    "kind": None,
    "scale": 1,
    "max_nodes": 60,
}
_RESULTS = {}


# --------------------------------------------------------------------------
# Framebuffer-Anmeldung (optional)
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
            _STATE["label"] or "unbenannt")
    return "Snapshot ueber LVGL (kein Framebuffer angehaengt)"


# --------------------------------------------------------------------------
# Auftraege an den LVGL-Thread
# --------------------------------------------------------------------------

def request(kind, timeout_ms=20000, **kwargs):
    """Auftrag an den LVGL-Thread. Wirft RuntimeError bei Timeout oder Fehler.

    Standardtimeout 20 s: ein Snapshot in voller Aufloesung dauert auf dem ESP32
    mehrere Sekunden -- der Server-Thread darf so lange warten, weil jede Verbindung
    ihren eigenen Thread hat."""
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
                "Timeout nach %d ms: LVGL-Thread hat '%s' nicht ausgefuehrt "
                "(laeuft die Hauptschleife mit service_requests()?)" % (timeout_ms, kind))
    entry = _RESULTS.pop(target, None)
    if entry is None:
        raise RuntimeError("Auftrag %d hat kein Ergebnis hinterlassen" % target)
    error, result = entry
    if error:
        raise RuntimeError(error)
    return result


def service_requests():
    """Muss in der LVGL-Schleife (Hauptthread) aufgerufen werden. Gibt True zurueck,
    wenn ein Auftrag ausgefuehrt wurde."""
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
            raise RuntimeError("unbekannter Auftrag: %s" % kind)
        _RESULTS[target] = (None, result)
    except Exception as exc:  # noqa: BLE001
        _RESULTS[target] = ("%s: %s" % (type(exc).__name__, exc), None)
    _REQ["done"] = target
    _REQ["kind"] = None
    return True


# --------------------------------------------------------------------------
# Bilder
# --------------------------------------------------------------------------

def _downscale(data, width, height, factor):
    """Pixel-Sampling (jeder factor-te Pixel) -- fuer Debug-Ansichten ausreichend."""
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
    """LVGL-Snapshot der aktiven Screen. Rueckgabe: (bytes, w, h, byte_swap).

    Verifizierte API (lvgl_micropython, LVGL 9.4):
      lv.snapshot_take(obj, lv.COLOR_FORMAT.RGB565) -> lv_draw_buf_t
      header: .w .h .stride .cf      Daten: .data (C_Array, ueber __dereference__)
    Kein Zwischenkopieren: es wird direkt aus der Sicht (memoryview) verkleinert,
    bevor der Snapshot freigegeben wird.
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
    """Zeilen aus einem gepolsterten Puffer eng packen (stride != Zeilenbreite)."""
    row_bytes = width * 2
    packed = bytearray(row_bytes * height)
    offset = 0
    for row in range(height):
        start = row * stride
        packed[offset:offset + row_bytes] = view[start:start + row_bytes]
        offset += row_bytes
    return packed


def capture(scale=1):
    """Rueckgabe: (data, width, height, byte_swap). Wirft RuntimeError mit Begruendung."""
    if attached():
        width, height = _STATE["width"], _STATE["height"]
        data = bytearray(_STATE["buffer"])
        swap = _STATE["byte_swap"]
        data, width, height = _downscale(data, width, height, int(scale))
        return data, width, height, swap

    data, width, height, swap = request("snapshot", scale=int(scale))
    if data is None:
        raise RuntimeError("Snapshot lieferte keine Daten")
    return data, width, height, swap


# --------------------------------------------------------------------------
# Widget-Baum
# --------------------------------------------------------------------------

def lvgl_tree(max_nodes=60):
    """Widget-Baum der aktiven Screen (laeuft im LVGL-Thread)."""
    return request("lvgl_tree", max_nodes=int(max_nodes))


def _lvgl_tree(max_nodes=60):
    try:
        import lvgl as lv
    except ImportError:
        return "lvgl nicht verfuegbar"
    lines = []
    try:
        root = lv.screen_active()
    except Exception as exc:  # noqa: BLE001
        return "screen_active() fehlgeschlagen: %s" % exc
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
            geom = "geom unbekannt"
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
        lines.append("... (%d weitere Knoten)" % len(stack))
    return "\n".join(lines) if lines else "(leer)"


def status():
    """Kurzbericht fuer /info und /screen."""
    return {
        "source": "framebuffer" if attached() else "lvgl-snapshot",
        "detail": describe(),
        "pending": _REQ["seq"] - _REQ["done"],
        "results_open": len(_RESULTS),
    }
