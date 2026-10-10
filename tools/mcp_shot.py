#!/usr/bin/env python3
"""Screenshot ueber den MCP-Server des Boards holen und als PNG ablegen.

Aufruf:  python3 tools/mcp_shot.py [ausgabe.png] [scale]
Umgebung: BOARD_HOST (Standard 192.168.1.168)
"""

import base64
import json
import os
import sys
import urllib.request

HOST = os.environ.get("BOARD_HOST", "192.168.1.168")
DEFAULT_OUT = "/root/.hermes/cache/scratch/board_snapshot.png"


def call(method, params=None, req_id=1, timeout=30):
    payload = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        payload["params"] = params
    request = urllib.request.Request(
        "http://%s/mcp" % HOST,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode()
    return json.loads(body)


def call_tool(name, arguments=None, req_id=1, timeout=30):
    reply = call("tools/call", {"name": name, "arguments": arguments or {}}, req_id, timeout)
    if "error" in reply:
        raise SystemExit("MCP-Fehler: %s" % reply["error"])
    result = reply["result"]
    if result.get("isError"):
        raise SystemExit("Tool-Fehler: %s" % result["content"][0].get("text"))
    return result["content"]


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    scale = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    content = call_tool("screenshot", {"scale": scale})
    images = [c for c in content if c.get("type") == "image"]
    texts = [c.get("text", "") for c in content if c.get("type") == "text"]
    for line in texts:
        print("board>", line)
    if not images:
        print("kein Bild in der Antwort")
        return 1
    blob = base64.b64decode(images[0]["data"])
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as fh:
        fh.write(blob)
    print("PNG gespeichert:", out_path, "(%d Bytes)" % len(blob))
    return 0


if __name__ == "__main__":
    sys.exit(main())
