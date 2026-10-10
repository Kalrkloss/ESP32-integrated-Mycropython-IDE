# Minimaler HTTP/1.1-Server in reinem MicroPython-Socket-Code.
# Absichtlich klein und hostseitig testbar: Request-Parsing ist eine freie Funktion,
# der Server nimmt eine Routing-Tabelle (METHOD + Pfad) -> Handler(Request) -> Response.

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
    __slots__ = ("status", "headers", "body")

    def __init__(self, status=200, body=b"", headers=None):
        self.status = status
        if isinstance(body, str):
            body = body.encode()
        self.body = body
        self.headers = headers or {}

    def __repr__(self):  # pragma: no cover
        return "<Response %s %dB>" % (self.status, len(self.body))


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
    """Liest eine HTTP-Anfrage. Rueckgabe: Request oder None (Verbindung leer)."""
    line = stream.readline()
    if not line:
        return None
    if hasattr(line, "decode"):
        line = line.decode()
    parts = line.strip().split()
    if len(parts) < 2:
        raise BadRequest("ungueltige Request-Zeile: %r" % line)
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
            raise BadRequest("body zu gross")
        body = stream.read(clen)
    return Request(method.upper(), path, parse_query(qs), headers, body)


def write_response(stream, resp):
    reason = REASONS.get(resp.status, "OK")
    head = ["HTTP/1.1 %d %s" % (resp.status, reason)]
    headers = dict(resp.headers)
    headers.setdefault("Content-Type", "application/octet-stream")
    headers["Content-Length"] = str(len(resp.body))
    headers.setdefault("Connection", "close")
    headers.setdefault("Access-Control-Allow-Origin", "*")
    for k, v in headers.items():
        head.append("%s: %s" % (k, v))
    stream.write(("\r\n".join(head) + "\r\n\r\n").encode())
    if resp.body:
        stream.write(resp.body)
    stream.flush()


def write_sse(stream, payload, event="message"):
    """Antwort im Streamable-HTTP-SSE-Format (fuer MCP-Clients, die SSE verlangen)."""
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
    """CPython-Sockets haben kein readline() -- dort eine Datei-Sicht erzeugen.
    MicroPython-Sockets koennen readline/read/write direkt."""
    if hasattr(conn, "readline"):
        return conn
    return conn.makefile("rwb")


class HttpServer:
    """Blockierender Server. `start_in_thread()` fuer den Betrieb neben LVGL."""

    def __init__(self, routes, port=80, host="0.0.0.0", on_error=None):
        self.routes = routes
        self.port = port
        self.host = host
        self.on_error = on_error
        self.sock = None
        self.running = False

    def _open(self):
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((self.host, self.port))
        s.listen(4)
        self.sock = s
        return s

    def serve_forever(self):
        s = self.sock or self._open()
        self.running = True
        while self.running:
            try:
                conn, addr = s.accept()
            except OSError:
                continue
            try:
                self._handle(conn, addr)
            except Exception as exc:  # noqa: BLE001 - eine kaputte Verbindung darf den Server nicht killen
                if self.on_error:
                    self.on_error(exc)
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def start_in_thread(self):
        if _thread is None:
            raise RuntimeError("kein _thread-Modul vorhanden")
        self._open()
        _thread.start_new_thread(self.serve_forever, ())

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
        handler = self.routes.get(req.method + " " + req.path)
        if handler is None:
            write_response(stream, text(404, "kein Handler fuer %s %s" % (req.method, req.path)))
            return
        try:
            resp = handler(req)
        except Exception as exc:  # noqa: BLE001 - Fehler im Handler -> 500 statt stummer Trennung
            if self.on_error:
                self.on_error(exc)
            write_response(stream, text(500, "%s: %s" % (type(exc).__name__, exc)))
            return
        if resp is not None:
            write_response(stream, resp)