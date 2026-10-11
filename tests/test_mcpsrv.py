"""Host tests for the debug MCP server (runs without an ESP32, under CPython).

Checked here: PNG encoder, JSON-RPC/MCP core, HTTP layer, screenshot tool.
Run:  python3 tests/test_mcpsrv.py
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
DEVICE = os.path.join(os.path.dirname(HERE), "firmware", "device")
sys.path.insert(0, FIRMWARE)
sys.path.insert(0, DEVICE)          # display_config, portal: device modules

import mcp_png as png  # noqa: E402
import mcp_protocol as protocol  # noqa: E402
import mcp_httpd as httpd  # noqa: E402
import mcp_screen as screen  # noqa: E402
import mcp_serve as serve  # noqa: E402
import mcp_webui as webui  # noqa: E402

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
    """Two colors in blocks -- well suited to checking row/byte order."""
    buf = bytearray()
    for y in range(h):
        for x in range(w):
            if (x + y) % 2 == 0:
                buf += rgb565(0xFF, 0x00, 0x00, byte_swap)
            else:
                buf += rgb565(0x00, 0x00, 0xFF, byte_swap)
    return buf


def parse_png(blob):
    assert blob[:8] == b"\x89PNG\r\n\x1a\n", "PNG signature missing"
    pos = 8
    chunks = {}
    while pos < len(blob):
        (length,) = struct.unpack(">I", blob[pos:pos + 4])
        tag = blob[pos + 4:pos + 8]
        data = blob[pos + 8:pos + 8 + length]
        crc = struct.unpack(">I", blob[pos + 8 + length:pos + 12 + length])[0]
        assert crc == zlib.crc32(tag + data) & 0xFFFFFFFF, "CRC wrong for %s" % tag
        chunks.setdefault(tag, b"")
        chunks[tag] += data
        pos += 12 + length
    return chunks


def test_png():
    print("PNG encoder")
    w, h = 8, 4
    raw = synthetic_screen(w, h)
    blob = png.encode_rgb565_png(raw, w, h)
    chunks = parse_png(blob)
    ihdr = chunks[b"IHDR"]
    width, height, depth, ctype = struct.unpack(">IIBB", ihdr[:10])
    check("IHDR size", (width, height) == (w, h), "%s" % ((width, height),))
    check("IHDR 8bit RGB", (depth, ctype) == (8, 2), "%d/%d" % (depth, ctype))
    scan = zlib.decompress(chunks[b"IDAT"])
    stride = 1 + w * 3
    check("scanline length", len(scan) == stride * h, "%d != %d" % (len(scan), stride * h))
    px = []
    for y in range(h):
        row = scan[y * stride:(y + 1) * stride]
        check("filter type row %d" % y, row[0] == 0)
        px.append(row[1:])
    first = px[0][:3]
    check("pixel(0,0) red", tuple(first) == (255, 0, 0), "%s" % (tuple(first),))
    second = px[0][3:6]
    check("pixel(1,0) blue", tuple(second) == (0, 0, 255), "%s" % (tuple(second),))
    # Row order: row 1 starts with blue (pattern x+y odd)
    check("row order", tuple(px[1][:3]) == (0, 0, 255), "%s" % (tuple(px[1][:3]),))
    # byte-swap variant
    raw2 = synthetic_screen(w, h, byte_swap=False)
    blob2 = png.encode_rgb565_png(raw2, w, h, byte_swap=False)
    scan2 = zlib.decompress(parse_png(blob2)[b"IDAT"])
    check("byte_swap=False equivalent", scan == scan2)


def test_protocol():
    print("MCP/JSON-RPC core")
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
    check("initialize capabilities has tools", "tools" in r["result"]["capabilities"])

    r = mcp.handle_message({"jsonrpc": "2.0", "id": 2, "method": "initialize",
                            "params": {"protocolVersion": "1999-01-01"}})
    check("unknown version -> default", r["result"]["protocolVersion"] == protocol.DEFAULT_PROTOCOL)

    check("notification without a reply", mcp.handle_message(
        {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None)
    check("initialized set", mcp.initialized)

    r = mcp.handle_message({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
    names = [t["name"] for t in r["result"]["tools"]]
    check("tools/list contains echo", names == ["echo"], "%s" % names)
    check("tools/list has inputSchema", "inputSchema" in r["result"]["tools"][0])

    r = mcp.handle_message({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                            "params": {"name": "echo", "arguments": {"value": "hello"}}})
    check("tools/call result", r["result"]["content"][0]["text"] == "echo:hello")
    check("handler was called", calls == ["hello"])

    r = mcp.handle_message({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                            "params": {"name": "doesnotexist", "arguments": {}}})
    check("unknown tool -> error", r["error"]["code"] == protocol.INVALID_PARAMS)

    r = mcp.handle_message({"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                            "params": {"name": "echo", "arguments": {}}})
    check("missing required argument -> error", r["error"]["code"] == protocol.INVALID_PARAMS)

    r = mcp.handle_message({"jsonrpc": "2.0", "id": 7, "method": "doesnotexist"})
    check("unknown method -> -32601", r["error"]["code"] == protocol.METHOD_NOT_FOUND)

    r = mcp.handle_message({"jsonrpc": "2.0", "id": 8, "method": "ping"})
    check("ping", r["result"] == {})

    r = mcp.handle_message({"id": 9})
    check("without method -> invalid", r["error"]["code"] == protocol.INVALID_REQUEST)


def test_http_layer():
    print("HTTP layer")
    check("parse_query", httpd.parse_query("a=1&b=x%20y&c") == {"a": "1", "b": "x y", "c": ""})

    import io
    raw = b"POST /mcp?a=1 HTTP/1.1\r\nHost: x\r\nContent-Length: 5\r\n\r\nhello"
    req = httpd.read_request(io.BytesIO(raw))
    check("request line", (req.method, req.path) == ("POST", "/mcp"))
    check("query", req.query == {"a": "1"})
    check("body", req.body == b"hello")

    req = httpd.read_request(io.BytesIO(b"GET / HTTP/1.1\r\n\r\n"))
    check("GET without body", req.method == "GET" and req.body == b"")
    check("empty connection -> None", httpd.read_request(io.BytesIO(b"")) is None)

    buf = io.BytesIO()
    httpd.write_response(buf, httpd.json_response({"ok": True}))
    out = buf.getvalue()
    check("status line", out.startswith(b"HTTP/1.1 200 OK\r\n"))
    check("Content-Length correct", b"Content-Length: 12\r\n" in out, out[:120])
    check("JSON body", out.endswith(b'{"ok": true}'))


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
    print("End to end over HTTP (real socket)")
    port = 8098
    # The web UI lives as files in the repo -- in the test ROOT points there,
    # on the device to the directory /web.
    webui.ROOT = os.path.join(os.path.dirname(HERE), "firmware")
    webui.WEB_DIR = "webfiles"
    screen.attach(synthetic_screen(64, 32), 64, 32, byte_swap=True, label="test")
    mcp, server = serve.build_server(port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    server._open()
    thread.start()
    time.sleep(0.2)
    try:
        status, headers, body = http_request(port, "GET", "/")
        check("GET / -> 200", status == 200, "%s" % status)
        check("GET / serves the web UI", b"<!DOCTYPE html>" in body)

        status, headers, body = http_request(port, "GET", "/status")
        check("GET /status -> 200", status == 200, "%s" % status)
        check("status names tools", b"screenshot" in body)

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
        check("Mcp-Session-Id set", headers.get("mcp-session-id") == "esp32-debug")

        # MCP: tools/list
        status, _, body = http_request(port, "POST", "/mcp",
                                       json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
                                       {"Accept": "application/json"})
        names = [t["name"] for t in json.loads(body)["result"]["tools"]]
        check("MCP tools/list contains screenshot", "screenshot" in names, "%s" % names)

        # MCP: tools/call screenshot -> real PNG in base64
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
        check("screenshot tool returns PNG 32x16 (scale=2)", (width, height) == (32, 16),
              "%s" % ((width, height),))
        check("screenshot accompanying text", any("scale=2" in c.get("text", "") for c in content))

        # plain-text endpoint
        status, headers, body = http_request(port, "GET", "/screen.png")
        check("GET /screen.png -> PNG", status == 200 and headers["content-type"] == "image/png")
        check("PNG valid", parse_png(body)[b"IHDR"][:8] == struct.pack(">II", 64, 32))

        # exec + logs
        status, _, body = http_request(port, "POST", "/exec", "print('hello from exec')")
        check("POST /exec", status == 200 and b"hello from exec" in body, body[:200])

        # notification -> 202 without body
        status, _, body = http_request(port, "POST", "/mcp",
                                       json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
                                       {"Accept": "application/json"})
        check("notification -> 202", status == 202 and body == b"", "%s %r" % (status, body[:40]))

        # SSE variant
        status, headers, body = http_request(port, "POST", "/mcp",
                                             json.dumps({"jsonrpc": "2.0", "id": 9, "method": "ping"}),
                                             {"Accept": "text/event-stream"})
        check("SSE response", status == 200 and body.startswith(b"event: message\ndata: "), body[:60])

        # unknown route
        status, _, _ = http_request(port, "GET", "/nothing")
        check("unknown route -> 404", status == 404)
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
        print("%d of %d checks FAILED: %s" % (len(FAILURES), CHECKS[0], ", ".join(FAILURES)))
        return 1
    print("all %d checks ok" % CHECKS[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
