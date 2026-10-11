# Minimal HTTP/1.1 server in pure MicroPython socket code.
# Intentionally small and testable on a host: request parsing is a free function,
# the server takes a routing table (METHOD + path) -> handler(Request) -> Response.

try:
    import usocket as socket
except ImportError:
    import socket

try:
    import _thread
except ImportError:  # pragma: no cover
    _thread = None

import json as _json


class Request:
    __slots__ = ("method", "path", "query", "headers", "body", "client")

    def __init__(self, method, path, query, headers, body, client=None):
        self.method = method
        self.path = path
        self.query = query
        self.headers = headers
        self.body = body
        self.client = client

    def arg(self, name, default=None):
        v = self.query.get(name)
        if v is None or v == "":
            return default
        return v

    def json(self):
        if not self.body:
            return {}
        return _json.loads(self.body)


class Response:
    __slots__ = ("status", "headers", "body", "datei")

    def __init__(self, status=200, body=b"", headers=None, datei=None):
        self.status = status
        if isinstance(body, str):
            body = body.encode()
        self.body = body
        self.headers = headers or {}
        # datei: path whose content is sent in chunks. Important on the device --
        # pulling 174 KB into memory in one go wastes space unnecessarily and can
        # fail, while the file goes out fine piece by piece.
        self.datei = datei

    def __repr__(self):  # pragma: no cover
        return "<Response %s %s>" % (self.status, self.datei or ("%dB" % len(self.body)))


REASONS = {
    200: "OK", 202: "Accepted", 204: "No Content", 400: "Bad Request",
    404: "Not Found", 405: "Method Not Allowed", 411: "Length Required",
    413: "Payload Too Large", 500: "Internal Server Error",
}


def text(status, body, ctype="text/plain; charset=utf-8", headers=None):
    h = {"Content-Type": ctype}
    if headers:
        h.update(headers)
    return Response(status, body, h)


def json_response(obj, status=200):
    return text(status, _json.dumps(obj), "application/json")


def parse_query(qs):
    out = {}
    for part in qs.split("&"):
        if not part:
            continue
        k, _, v = part.partition("=")
        out[_unquote(k)] = _unquote(v)
    return out


def _unquote(s):
    if "%" not in s and "+" not in s:
        return s
    s = s.replace("+", " ")
    out = bytearray()
    i = 0
    while i < len(s):
        if s[i] == "%" and i + 2 < len(s) + 1:
            try:
                out.append(int(s[i + 1:i + 3], 16))
                i += 3
                continue
            except ValueError:
                pass
        out.append(ord(s[i]))
        i += 1
    return out.decode()


class BadRequest(Exception):
    pass


def read_request(stream, max_body=262144):
    """Reads an HTTP request. Returns: Request or None (empty connection)."""
    line = stream.readline()
    if not line:
        return None
    if hasattr(line, "decode"):
        line = line.decode()
    parts = line.strip().split()
    if len(parts) < 2:
        raise BadRequest("invalid request line: %r" % line)
    method, target = parts[0], parts[1]
    path, _, qs = target.partition("?")
    headers = {}
    while True:
        hline = stream.readline()
        if not hline:
            break
        if hasattr(hline, "decode"):
            hline = hline.decode()
        hline = hline.strip()
        if not hline:
            break
        k, _, v = hline.partition(":")
        headers[k.strip().lower()] = v.strip()
    body = b""
    clen = headers.get("content-length")
    if clen:
        clen = int(clen)
        if clen > max_body:
            raise BadRequest("body too large")
        body = stream.read(clen)
    return Request(method.upper(), path, parse_query(qs), headers, body)


def write_response(stream, resp):
    reason = REASONS.get(resp.status, "OK")
    head = ["HTTP/1.1 %d %s" % (resp.status, reason)]
    headers = dict(resp.headers)
    headers.setdefault("Content-Type", "application/octet-stream")
    size = len(resp.body)
    if resp.datei is not None:
        try:
            import os
            size = os.stat(resp.datei)[6]
        except OSError:
            size = 0
    headers["Content-Length"] = str(size)
    headers.setdefault("Connection", "close")
    headers.setdefault("Access-Control-Allow-Origin", "*")
    for k, v in headers.items():
        head.append("%s: %s" % (k, v))
    stream.write(("\r\n".join(head) + "\r\n\r\n").encode())
    if resp.datei is not None:
        with open(resp.datei, "rb") as fh:
            while True:
                piece = fh.read(2048)
                if not piece:
                    break
                stream.write(piece)
    elif resp.body:
        stream.write(resp.body)
    # MicroPython sockets have no flush() -- CPython file objects do.
    flush = getattr(stream, "flush", None)
    if flush is not None:
        flush()


def write_sse(stream, payload, event="message"):
    """Response in streamable-HTTP SSE format (for MCP clients that require SSE)."""
    body = ("event: %s\ndata: %s\n\n" % (event, payload)).encode()
    head = ("HTTP/1.1 200 OK\r\n"
            "Content-Type: text/event-stream\r\n"
            "Cache-Control: no-cache\r\n"
            "Connection: close\r\n"
            "Content-Length: %d\r\n\r\n" % len(body))
    stream.write(head.encode())
    stream.write(body)
    stream.flush()


def stream_for(conn):
    """CPython sockets have no readline() -- create a file view there.
    MicroPython sockets can readline/read/write directly."""
    if hasattr(conn, "readline"):
        return conn
    return conn.makefile("rwb")


MAX_WORKERS = 4        # concurrent connections; the web UI fetches several
                       # endpoints in parallel (status, files, configuration, image),
                       # so do not limit it more tightly than necessary
WORKER_STACK = 16384   # bytes of stack per connection (JSON + PNG need some room)


def start_worker(fn, args):
    """Starts a thread. Note: the third parameter of start_new_thread is kwargs in
    MicroPython (not a stack value!) -- the stack size is set globally via
    _thread.stack_size()."""
    if _thread is None:
        return False
    try:
        setter = getattr(_thread, "stack_size", None)
        if setter is not None:
            setter(WORKER_STACK)
    except Exception:  # noqa: BLE001
        pass
    try:
        _thread.start_new_thread(fn, args)
        return True
    except Exception:  # noqa: BLE001
        return False


class HttpServer:
    """Blocking server. Use `start_in_thread()` for operation alongside LVGL."""

    def __init__(self, routes, port=80, host="0.0.0.0", on_error=None):
        self.routes = routes
        self.port = port
        self.host = host
        self.on_error = on_error
        self.sock = None
        self.running = False
        self._workers = 0

    def _open(self):
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((self.host, self.port))
        s.listen(4)
        self.sock = s
        return s

    def serve_forever(self):
        """Accepts connections. Every connection gets its own thread --
        otherwise a single stuck handler (e.g. a waiting LVGL request) blocks the
        entire accept loop."""
        s = self.sock or self._open()
        self.running = True
        while self.running:
            try:
                conn, addr = s.accept()
            except OSError:
                continue
            if _thread is not None and self._workers < MAX_WORKERS:
                self._workers += 1
                if start_worker(self._worker, (conn, addr)):
                    continue
                self._workers -= 1
            try:
                self._handle(conn, addr)
            except Exception as exc:  # noqa: BLE001 - the accept loop must never die
                if self.on_error:
                    self.on_error(exc)
            finally:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass

    def _worker(self, conn, addr):
        try:
            self._handle(conn, addr)
        except Exception as exc:  # noqa: BLE001
            if self.on_error:
                self.on_error(exc)
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
            self._workers -= 1

    def start_in_thread(self):
        if _thread is None:
            raise RuntimeError("no _thread module available")
        self._open()
        start_worker(self.serve_forever, ())

    def _find_handler(self, method, path):
        """Exact match, otherwise a prefix route (key ends with '*').

        Prefix routes are needed for file trees (e.g. the bundled code editor),
        so that not every single file has to be registered.
        """
        handler = self.routes.get(method + " " + path)
        if handler is not None:
            return handler
        for key, candidate in self.routes.items():
            if not key.endswith("*"):
                continue
            k_method, _, k_prefix = key.partition(" ")
            k_prefix = k_prefix[:-1]          # the "*" is not part of the comparison
            if k_method == method and path.startswith(k_prefix):
                return candidate
        return None

    def _handle(self, conn, addr):
        stream = stream_for(conn)
        try:
            req = read_request(stream)
        except BadRequest as exc:
            write_response(stream, text(400, str(exc)))
            return
        if req is None:
            return
        req.client = addr
        handler = self._find_handler(req.method, req.path)
        if handler is None:
            write_response(stream, text(404, "no handler for %s %s" % (req.method, req.path)))
            return
        try:
            resp = handler(req)
        except Exception as exc:  # noqa: BLE001 - error in handler -> 500 instead of a silent disconnect
            if self.on_error:
                self.on_error(exc)
            write_response(stream, text(500, "%s: %s" % (type(exc).__name__, exc)))
            return
        if resp is not None:
            write_response(stream, resp)
