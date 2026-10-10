# stdout-Mitschnitt in einen Ringpuffer, damit der Debug-Server "Logs zeigen" kann.
# Auf dem Geraet ersetzt ein Tee-Objekt sys.stdout; ohne Tee (Host-Test) bleibt es leer.

try:
    import sys
except ImportError:  # pragma: no cover
    import usys as sys


class RingBuffer:
    def __init__(self, capacity=16384):
        self.capacity = capacity
        self.buf = bytearray()
        self.dropped = 0

    def write(self, data):
        if isinstance(data, str):
            data = data.encode()
        self.buf += data
        overflow = len(self.buf) - self.capacity
        if overflow > 0:
            del self.buf[:overflow]
            self.dropped += overflow
        return len(data)

    def get(self):
        return bytes(self.buf)

    def text(self, clear=False):
        # MicroPython: bytes.decode() nimmt 'errors' nur positional
        out = self.buf.decode("utf-8", "replace")
        prefix = ""
        if self.dropped:
            prefix = "[%d Bytes verworfen]\n" % self.dropped
        if clear:
            self.clear()
        return prefix + out

    def clear(self):
        del self.buf[:]
        self.dropped = 0


class Tee:
    """Schreibt in das Original-stdout und zusaetzlich in den Ringpuffer."""

    def __init__(self, original, ring):
        self.original = original
        self.ring = ring

    def write(self, data):
        self.ring.write(data)
        try:
            return self.original.write(data)
        except Exception:
            return len(data)

    def read(self, *args):
        return self.original.read(*args)

    def readline(self, *args):
        return self.original.readline(*args)

    def flush(self):
        try:
            self.original.flush()
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self.original, name)


RING = RingBuffer()


def install(ring=None):
    """Haengt den Mitschnitt vor sys.stdout (idempotent, robust wenn stdout fehlt)."""
    ring = ring or RING
    out = getattr(sys, "stdout", None)
    if out is None or isinstance(out, Tee):
        return ring
    try:
        sys.stdout = Tee(out, ring)
    except Exception:  # noqa: BLE001 - Mitschnitt ist optional, nie den Start verhindern
        pass
    return ring


def logs(clear=False):
    return RING.text(clear=clear)
