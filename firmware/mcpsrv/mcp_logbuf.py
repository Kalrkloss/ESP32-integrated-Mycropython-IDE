# Capture stdout into a ring buffer so that the debug server can "show logs".
# On the device a Tee object replaces sys.stdout; without a Tee (host test) it stays empty.

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
        # MicroPython: bytes.decode() only accepts 'errors' positionally
        out = self.buf.decode("utf-8", "replace")
        prefix = ""
        if self.dropped:
            prefix = "[%d bytes discarded]\n" % self.dropped
        if clear:
            self.clear()
        return prefix + out

    def clear(self):
        del self.buf[:]
        self.dropped = 0


class Tee:
    """Writes to the original stdout and additionally into the ring buffer."""

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
    """Puts the capture in front of sys.stdout (idempotent, robust if stdout is missing)."""
    ring = ring or RING
    out = getattr(sys, "stdout", None)
    if out is None or isinstance(out, Tee):
        return ring
    try:
        sys.stdout = Tee(out, ring)
    except Exception:  # noqa: BLE001 - the capture is optional, never prevent startup
        pass
    return ring


def logs(clear=False):
    return RING.text(clear=clear)


def log(*args, **kwargs):
    """For application code: write into the ring buffer AND to the console.

    Needed because MicroPython `print` writes directly to the C stdout -- the ring
    buffer (and thus the MCP tool `logs`) sees nothing of it.
    """
    text = kwargs.get("sep", " ").join(str(a) for a in args)
    if kwargs.get("end", "\n") == "\n":
        text += "\n"
    RING.write(text)
    print(text, end="")
