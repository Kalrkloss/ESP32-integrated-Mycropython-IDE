# Minimal PNG encoder (RGB565 -> PNG, without third-party libraries).
# Runs in MicroPython AND CPython: no compiler/library dependency.
# Compression: real deflate compression only if the `deflate` module is present,
# otherwise valid "stored" deflate blocks (larger, but correct and fast).

try:
    import binascii
    _crc32 = binascii.crc32
except ImportError:  # pragma: no cover - fallback for ports without binascii
    _tbl = []
    for _i in range(256):
        _c = _i
        for _ in range(8):
            _c = (0xEDB88320 ^ (_c >> 1)) if (_c & 1) else (_c >> 1)
        _tbl.append(_c)

    def _crc32(data, crc=0):
        crc ^= 0xFFFFFFFF
        for b in data:
            crc = _tbl[(crc ^ b) & 0xFF] ^ (crc >> 8)
        return crc ^ 0xFFFFFFFF

try:
    import zlib
except ImportError:  # pragma: no cover
    zlib = None

try:
    import deflate
except ImportError:
    deflate = None

try:
    from io import BytesIO
except ImportError:  # pragma: no cover
    from uio import BytesIO


def _adler32(data):
    a = 1
    b = 0
    for byte in data:
        a = (a + byte) % 65521
        b = (b + a) % 65521
    return (b << 16) | a


def _stored_zlib(data):
    """Zlib stream with uncompressed deflate blocks (BTYPE=00)."""
    out = bytearray(b"\x78\x01")
    pos = 0
    n = len(data)
    if n == 0:
        out += b"\x01\x00\x00\xff\xff"
    while pos < n:
        chunk = data[pos:pos + 65535]
        pos += len(chunk)
        final = 1 if pos >= n else 0
        out.append(final)
        out += len(chunk).to_bytes(2, "little")
        out += (0xFFFF - len(chunk)).to_bytes(2, "little")
        out += chunk
    out += _adler32(data).to_bytes(4, "big")
    return bytes(out)


def _deflate_zlib(data):
    """Real compression if the deflate module is present; otherwise None."""
    if deflate is None:
        return None
    buf = BytesIO()
    try:
        comp = deflate.DeflateIO(buf, deflate.ZLIB)
        comp.write(data)
        comp.close()
        return buf.getvalue()
    except Exception:
        return None


def _chunk(tag, payload):
    return (len(payload).to_bytes(4, "big") + tag + payload +
            _crc32(tag + payload).to_bytes(4, "big"))


def rgb565_to_rgb888(data, byte_swap=True):
    """RGB565 buffer -> RGB888 bytes. `byte_swap` = little-endian pairs in the buffer."""
    out = bytearray(len(data) // 2 * 3)
    o = 0
    for i in range(0, len(data) - 1, 2):
        lo = data[i]
        hi = data[i + 1]
        if byte_swap:
            v = lo | (hi << 8)
        else:
            v = (lo << 8) | hi
        r = (v >> 11) & 0x1F
        g = (v >> 5) & 0x3F
        b = v & 0x1F
        out[o] = (r << 3) | (r >> 2)
        out[o + 1] = (g << 2) | (g >> 4)
        out[o + 2] = (b << 3) | (b >> 2)
        o += 3
    return out


def encode_rgb565_png(data, width, height, byte_swap=True, compress=True):
    """RGB565 buffer -> PNG bytes (24-bit RGB, filter 0 per row)."""
    stride = width * 2
    if len(data) < stride * height:
        raise ValueError("buffer too small: %d < %d" % (len(data), stride * height))
    raw = bytearray()
    rowbytes = width * 3
    for y in range(height):
        raw.append(0)  # filter type None
        raw += rgb565_to_rgb888(data[y * stride:(y + 1) * stride], byte_swap)

    body = _deflate_zlib(bytes(raw)) if compress else None
    if body is None:
        body = _stored_zlib(bytes(raw))

    ihdr = (width.to_bytes(4, "big") + height.to_bytes(4, "big") +
            bytes((8, 2, 0, 0, 0)))  # 8 bit, RGB (no alpha), no interlace
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) +
            _chunk(b"IDAT", body) + _chunk(b"IEND", b""))
