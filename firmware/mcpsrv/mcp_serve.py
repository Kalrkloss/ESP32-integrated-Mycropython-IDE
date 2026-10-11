# Entry point of the debug MCP server on the ESP32.
# Starts an HTTP server (thread) with:
#   POST /mcp            -> MCP (JSON-RPC), tools see tools.build_tools()
#   GET  /               -> status
#   GET  /screen.png     -> screenshot (also ?scale=2)
#   GET  /log            -> last console output
#   POST /exec           -> run Python on the device
#   GET  /info           -> device info
#   POST /reset          -> reboot
# The modules of this folder are included flat (sys.path contains this folder
# or they are frozen as modules).

import json
import time

import mcp_httpd
import mcp_logbuf
import mcp_protocol
import mcp_screen
import mcp_tools
import mcp_webui

PORT = 80
SERVER_NAME = "esp32-debug"
SERVER_VERSION = "0.1.0"
INSTRUCTIONS = (
    "Debug server on an ESP32-S3 (JC3248W535, MicroPython+LVGL). "
    "screenshot returns the screen, exec_python runs code, "
    "logs shows the console, reset reboots the board."
)


def build_server(port=PORT, setup_only=False):
    """Builds the MCP server + router. Also usable on a host (without hardware).

    setup_only: serve the setup page only (open access point!).
    Then there are neither MCP tools nor code execution nor file access -- whoever
    sits on the open WLAN should only be able to change the configuration.
    """
    mcp_logbuf.install()
    mcp = mcp_protocol.McpServer(mcp_tools.build_tools(), server_name=SERVER_NAME,
                                 server_version=SERVER_VERSION, instructions=INSTRUCTIONS)

    def mcp_handler(req):
        try:
            msg = json.loads(req.body or b"{}")
        except (ValueError, TypeError):
            return mcp_httpd.json_response(
                {"jsonrpc": "2.0", "id": None,
                 "error": {"code": mcp_protocol.PARSE_ERROR, "message": "Parse error"}}, 400)
        if isinstance(msg, list):
            replies = [r for r in (mcp.handle_message(m) for m in msg) if r]
            payload = json.dumps(replies)
        else:
            reply = mcp.handle_message(msg)
            if reply is None:
                return mcp_httpd.Response(202, b"", {"Content-Type": "application/json",
                                                     "Mcp-Session-Id": SERVER_NAME})
            payload = json.dumps(reply)
        headers = {"Mcp-Session-Id": SERVER_NAME, "Cache-Control": "no-store"}
        accept = req.headers.get("accept", "")
        if "text/event-stream" in accept and "application/json" not in accept:
            resp = mcp_httpd.Response(200, b"", dict(headers, **{"Content-Type": "text/event-stream"}))
            resp.body = ("event: message\ndata: %s\n\n" % payload).encode()
            return resp
        return mcp_httpd.text(200, payload, "application/json", headers)

    if setup_only:
        routes = mcp_webui.setup_routes()
    else:
        routes = mcp_tools.build_routes(mcp_handler)
        # The web UI takes over "/" (console, editor, file manager,
        # configuration); the plain-text status stays available under "/status".
        routes.update(mcp_webui.build_routes())
    # Write errors in handlers into the log ring -- otherwise they vanish without a trace.
    return mcp, mcp_httpd.HttpServer(
        routes, port=port,
        on_error=lambda exc: mcp_logbuf.log("HTTP error: %s: %s" % (type(exc).__name__, exc)))


def _aufsicht(server):
    """Supervise the accept loop.

    If it dies -- for example from a memory error while serving -- nothing listens
    on the port anymore, while the main loop keeps running unchanged. The board then
    looks reachable (ping) but is dead. So restart here instead of silently losing
    the server.
    """
    while True:
        try:
            server.serve_forever()
            return                       # regular end (running was set to False)
        except Exception as exc:  # noqa: BLE001
            mcp_logbuf.log("mcp_serve: accept loop restarted after %s: %s"
                           % (type(exc).__name__, exc))
            try:
                if server.sock is not None:
                    server.sock.close()
            except Exception:  # noqa: BLE001
                pass
            server.sock = None
            time.sleep(1)


def start(port=PORT, setup_only=False):
    mcp, server = build_server(port=port, setup_only=setup_only)
    server._open()
    if not mcp_httpd.start_worker(_aufsicht, (server,)):
        raise RuntimeError("no _thread module -- server cannot start")
    print("debug server on port %d (%d tools%s)"
          % (port, len(mcp.tools), ", setup mode" if setup_only else ""))
    return mcp, server


def main(port=PORT):
    """As main.py on the device: keep waiting so the thread keeps running."""
    start(port=port)
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
