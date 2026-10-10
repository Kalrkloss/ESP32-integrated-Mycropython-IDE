#!/usr/bin/env python3
"""Einzelnen MCP-Tool-Aufruf an das Board schicken.

Aufruf:  python3 tools/mcp_call.py <tool> ['{"json": "args"}']
Umgebung: BOARD_HOST (Standard 192.168.1.168)
"""

import json
import os
import sys
import urllib.error
import urllib.request

HOST = os.environ.get("BOARD_HOST", "192.168.1.168")


def call(tool, arguments=None, timeout=60):
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": tool, "arguments": arguments or {}}}
    request = urllib.request.Request(
        "http://%s/mcp" % HOST,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        return {"http_error": exc.code, "body": exc.read().decode()[:500]}
    except Exception as exc:  # noqa: BLE001
        return {"connection_error": "%s: %s" % (type(exc).__name__, exc)}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    tool = sys.argv[1]
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    reply = call(tool, args)
    if "error" in reply:
        print("MCP-Fehler:", reply["error"])
        return 1
    if "result" in reply:
        result = reply["result"]
        for item in result.get("content", []):
            if item.get("type") == "text":
                print(item["text"])
            else:
                print("[%s, %d Zeichen]" % (item.get("type"), len(item.get("data", ""))))
        if result.get("isError"):
            return 1
        return 0
    print(json.dumps(reply)[:800])
    return 1


if __name__ == "__main__":
    sys.exit(main())
