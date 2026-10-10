"""Host-Tests fuer den Debug-MCP-Server (laeuft ohne ESP32, mit CPython).

Geprueft werden: PNG-Encoder, JSON-RPC/MCP-Kern, HTTP-Layer, Screenshot-Tool.
Aufruf:  python3 tests/test_mcpsrv.py
"""

import json
import os
import socket
import struct
import sys
import threading
import time
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
FIRMWARE = os.path.join(os.path.dirname(HERE), "firmware", "mcpsrv")
sys.path.insert(0, FIRMWARE)

import mcp_png as png  # noqa: E402
import mcp_protocol as protocol  # noqa: E402
import mcp_httpd as httpd  # noqa: E402
import mcp_screen as screen  # noqa: E402
import mcp_serve as serve  # noqa: E402

FAILURES = []
CHECKS = [0]


def check(name, condition, detail=""):
    CHECKS[0] += 1
    if condition:
        print("  ok   %s" % name)
    else:
        print("  FAIL %s %s" % (name, detail))
        FAILURES.append(name)


def rgb565(r, g, b, byte_swap=True):
    v = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    lo, hi = v & 0xFF, v >> 8
    return bytes((lo, hi)) if byte_swap else bytes((hi, lo))


def synthetic_screen(w=8, h=4, byte_swap=True):
    """Zwei Farben in Bloecken -- gut geeignet, um Zeilen-/Byte-Reihenfolge zu pruefen."""
    buf = bytearray()
    for y in range(h):
        for x in range(w):
            if (x + y) % 2 == 0:
                buf += rgb565(0xFF, 0x00, 0x00, byte_swap)
            else:
                buf += rgb565(0x00, 0x00, 0xFF, byte_swap)
    return buf


def parse_png(blob):
    assert blob[:8] == b"\x89PNG\r\n\x1a\n", "PNG-Signatur fehlt"
    pos = 8
    chunks = {}
    while pos < len(blob):
        (length,) = struct.unpack(">I", blob[pos:pos + 4])
        tag = blob[pos + 4:pos + 8]
        data = blob[pos + 8:pos + 8 + length]
        crc = struct.unpack(">I", blob[pos + 8 + length:pos + 12 + length])[0]
        assert crc == zlib.crc32(tag + data) & 0xFFFFFFFF, "CRC falsch fuer %s" % tag
        chunks.setdefault(tag, b"")
        chunks[tag] += data
        pos += 12 + length
    return chunks


def test_png():
    print("PNG-Encoder")
    w, h = 8, 4
    raw = synthetic_screen(w, h)
    blob = png.encode_rgb565_png(raw, w, h)
    chunks = parse_png(blob)
    ihdr = chunks[b"IHDR"]
    width, height, depth, ctype = struct.unpack(">IIBB", ihdr[:10])
    check("IHDR Groesse", (width, height) == (w, h), "%s" % ((width, height),))
    check("IHDR 8bit RGB", (depth, ctype) == (8, 2), "%d/%d" % (depth, ctype))
    scan = zlib.decompress(chunks[b"IDAT"])
    stride = 1 + w * 3
    check("Scanline-Laenge", len(scan) == stride * h, "%d != %d" % (len(scan), stride * h))
    px = []
    for y in range(h):
        row = scan[y * stride:(y + 1) * stride]
        check("Filtertyp Zeile %d" % y, row[0] == 0)
        px.append(row[1:])
    first = px[0][:3]
    check("Pixel(0,0) rot", tuple(first) == (255, 0, 0), "%s" % (tuple(first),))
    second = px[0][3:6]
    check("Pixel(1,0) blau", tuple(second) == (0, 0, 255), "%s" % (tuple(second),))
    # Zeilenreihenfolge: Zeile 1 beginnt mit blau (Muster x+y ungerade)
    check("Zeilenreihenfolge", tuple(px[1][:3]) == (0, 0, 255), "%s" % (tuple(px[1][:3]),))
    # Byte-Swap-Variante
    raw2 = synthetic_screen(w, h, byte_swap=False)
    blob2 = png.encode_rgb565_png(raw2, w, h, byte_swap=False)
    scan2 = zlib.decompress(parse_png(blob2)[b"IDAT"])
    check("byte_swap=False gleichwertig", scan == scan2)


def test_protocol():
    print("MCP/JSON-RPC-Kern")
    from mcp_protocol import Tool
    calls = []

    def echo(value="x"):
        calls.append(value)
        return "echo:%s" % value

    mcp = protocol.McpServer([
        Tool("echo", "Echo", {"type": "object", "properties": {"value": {"type": "string"}},
                              "required": ["value"], "additionalProperties": False}, echo)])

    r = mcp.handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                            "params": {"protocolVersion": "2025-03-26",
                                       "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}})
    check("initialize echo version", r["result"]["protocolVersion"] == "2025-03-26")
    check("initialize serverInfo", r["result"]["serverInfo"]["name"] == "esp32-mcp")
    check("initialize capabilities hat tools", "tools" in r["result"]["capabilities"])

    r = mcp.handle_message({"jsonrpc": "2.0", "id": 2, "method": "initialize",
                            "params": {"protocolVersion": "1999-01-01"}})
    check("unbekannte Version -> Default", r["result"]["protocolVersion"] == protocol.DEFAULT_PROTOCOL)

    check("Notification ohne Antwort", mcp.handle_message(
        {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None)
    check("initialized gesetzt", mcp.initialized)

    r = mcp.handle_message({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
    names = [t["name"] for t in r["result"]["tools"]]
    check("tools/list enthaelt echo", names == ["echo"], "%s" % names)
    check("tools/list hat inputSchema", "inputSchema" in r["result"]["tools"][0])

    r = mcp.handle_message({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                            "params": {"name": "echo", "arguments": {"value": "hallo"}}})
    check("tools/call Ergebnis", r["result"]["content"][0]["text"] == "echo:hallo")
    check("Handler wurde aufgerufen", calls == ["hallo"])

    r = mcp.handle_message({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                            "params": {"name": "gibtsnicht", "arguments": {}}})
    check("unbekanntes Tool -> Fehler", r["error"]["code"] == protocol.INVALID_PARAMS)

    r = mcp.handle_message({"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                            "params": {"name": "echo", "arguments": {}}})
    check("fehlendes Pflichtargument -> Fehler", r["error"]["code"] == protocol.INVALID_PARAMS)

    r = mcp.handle_message({"jsonrpc": "2.0", "id": 7, "method": "gibtsnicht"})
    check("unbekannte Methode -> -32601", r["error"]["code"] == protocol.METHOD_NOT_FOUND)

    r = mcp.handle_message({"jsonrpc": "2.0", "id": 8, "method": "ping"})
    check("ping", r["result"] == {})

    r = mcp.handle_message({"id": 9})
    check("ohne method -> invalid", r["error"]["code"] == protocol.INVALID_REQUEST)


def test_http_layer():
    print("HTTP-Layer")
    check("parse_query", httpd.parse_query("a=1&b=x%20y&c") == {"a": "1", "b": "x y", "c": ""})

    import io
    raw = b"POST /mcp?a=1 HTTP/1.1\r\nHost: x\r\nContent-Length: 5\r\n\r\nhello"
    req = httpd.read_request(io.BytesIO(raw))
    check("Request-Zeile", (req.method, req.path) == ("POST", "/mcp"))
    check("Query", req.query == {"a": "1"})
    check("Body", req.body == b"hello")

    req = httpd.read_request(io.BytesIO(b"GET / HTTP/1.1\r\n\r\n"))
    check("GET ohne Body", req.method == "GET" and req.body == b"")
    check("leere Verbindung -> None", httpd.read_request(io.BytesIO(b"")) is None)

    buf = io.BytesIO()
    httpd.write_response(buf, httpd.json_response({"ok": True}))
    out = buf.getvalue()
    check("Statuszeile", out.startswith(b"HTTP/1.1 200 OK\r\n"))
    check("Content-Length korrekt", b"Content-Length: 12\r\n" in out, out[:120])
    check("JSON-Body", out.endswith(b'{"ok": true}'))


def http_request(port, method, path, body=None, headers=None, timeout=5):
    s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    head = ["%s %s HTTP/1.1" % (method, path), "Host: 127.0.0.1", "Connection: close"]
    for k, v in (headers or {}).items():
        head.append("%s: %s" % (k, v))
    payload = body.encode() if isinstance(body, str) else (body or b"")
    if payload:
        head.append("Content-Length: %d" % len(payload))
    s.sendall(("\r\n".join(head) + "\r\n\r\n").encode() + payload)
    chunks = []
    while True:
        block = s.recv(65536)
        if not block:
            break
        chunks.append(block)
    s.close()
    raw = b"".join(chunks)
    head_raw, _, body_raw = raw.partition(b"\r\n\r\n")
    lines = head_raw.decode(errors="replace").split("\r\n")
    status = int(lines[0].split()[1])
    resp_headers = {}
    for line in lines[1:]:
        k, _, v = line.partition(":")
        resp_headers[k.strip().lower()] = v.strip()
    return status, resp_headers, body_raw


def test_end_to_end():
    print("Ende-zu-Ende ueber HTTP (echter Socket)")
    port = 8098
    screen.attach(synthetic_screen(64, 32), 64, 32, byte_swap=True, label="test")
    mcp, server = serve.build_server(port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    server._open()
    thread.start()
    time.sleep(0.2)
    try:
        status, headers, body = http_request(port, "GET", "/")
        check("GET / -> 200", status == 200, "%s" % status)
        check("Status nennt Tools", b"screenshot" in body)

        status, headers, body = http_request(port, "GET", "/info")
        info = json.loads(body)
        check("GET /info JSON", status == 200 and "screen" in info)

        # MCP: initialize
        req = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
               "params": {"protocolVersion": "2025-06-18", "capabilities": {}}}
        status, headers, body = http_request(
            port, "POST", "/mcp", json.dumps(req),
            {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
        reply = json.loads(body)
        check("MCP initialize via HTTP", status == 200 and reply["result"]["serverInfo"]["name"] == "esp32-debug",
              "%s %s" % (status, body[:120]))
        check("Mcp-Session-Id gesetzt", headers.get("mcp-session-id") == "esp32-debug")

        # MCP: tools/list
        status, _, body = http_request(port, "POST", "/mcp",
                                       json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
                                       {"Accept": "application/json"})
        names = [t["name"] for t in json.loads(body)["result"]["tools"]]
        check("MCP tools/list enthaelt screenshot", "screenshot" in names, "%s" % names)

        # MCP: tools/call screenshot -> echtes PNG in base64
        status, _, body = http_request(
            port, "POST", "/mcp",
            json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                        "params": {"name": "screenshot", "arguments": {"scale": 2}}}),
            {"Accept": "application/json"})
        content = json.loads(body)["result"]["content"]
        import base64
        image = [c for c in content if c["type"] == "image"][0]
        blob = base64.b64decode(image["data"])
        chunks = parse_png(blob)
        width, height = struct.unpack(">II", chunks[b"IHDR"][:8])
        check("Screenshot-Tool liefert PNG 32x16 (scale=2)", (width, height) == (32, 16),
              "%s" % ((width, height),))
        check("Screenshot-Begleittext", any("scale=2" in c.get("text", "") for c in content))

        # Klartext-Endpunkt
        status, headers, body = http_request(port, "GET", "/screen.png")
        check("GET /screen.png -> PNG", status == 200 and headers["content-type"] == "image/png")
        check("PNG-Gueltig", parse_png(body)[b"IHDR"][:8] == struct.pack(">II", 64, 32))

        # exec + logs
        status, _, body = http_request(port, "POST", "/exec", "print('hallo aus exec')")
        check("POST /exec", status == 200 and b"hallo aus exec" in body, body[:200])

        # Notification -> 202 ohne Body
        status, _, body = http_request(port, "POST", "/mcp",
                                       json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
                                       {"Accept": "application/json"})
        check("Notification -> 202", status == 202 and body == b"", "%s %r" % (status, body[:40]))

        # SSE-Variante
        status, headers, body = http_request(port, "POST", "/mcp",
                                             json.dumps({"jsonrpc": "2.0", "id": 9, "method": "ping"}),
                                             {"Accept": "text/event-stream"})
        check("SSE-Antwort", status == 200 and body.startswith(b"event: message\ndata: "), body[:60])

        # unbekannte Route
        status, _, _ = http_request(port, "GET", "/nichts")
        check("unbekannte Route -> 404", status == 404)
    finally:
        server.running = False
        screen.detach()


def main():
    test_png()
    test_protocol()
    test_http_layer()
    test_end_to_end()
    print()
    if FAILURES:
        print("%d von %d Checks FEHLGESCHLAGEN: %s" % (len(FAILURES), CHECKS[0], ", ".join(FAILURES)))
        return 1
    print("alle %d Checks ok" % CHECKS[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
