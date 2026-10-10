# Einstiegspunkt des Debug-MCP-Servers auf dem ESP32.
# Startet einen HTTP-Server (Thread) mit:
#   POST /mcp            -> MCP (JSON-RPC), Tools siehe tools.build_tools()
#   GET  /               -> Status
#   GET  /screen.png     -> Screenshot (auch ?scale=2)
#   GET  /log            -> letzte Konsolenausgaben
#   POST /exec           -> Python auf dem Geraet ausfuehren
#   GET  /info           -> Geraeteinfos
#   POST /reset          -> Neustart
# Die Module dieses Ordners werden flach eingebunden (sys.path enthaelt diesen Ordner
# bzw. sie sind als Module eingefroren).

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
    "Debug-Server auf einem ESP32-S3 (JC3248W535, MicroPython+LVGL). "
    "screenshot liefert den Bildschirm, exec_python fuehrt Code aus, "
    "logs zeigt die Konsole, reset startet das Board neu."
)


def build_server(port=PORT):
    """Baut MCP-Server + Router. Auch hostseitig nutzbar (ohne Hardware)."""
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

    routes = mcp_tools.build_routes(mcp_handler)
    # Die Weboberflaeche uebernimmt "/" (Konsole, Editor, Dateimanager, Konfiguration);
    # der Klartext-Status liegt weiterhin unter "/status".
    routes.update(mcp_webui.build_routes())
    # Fehler in Handlern in den Logring schreiben -- sonst verschwinden sie spurlos.
    return mcp, mcp_httpd.HttpServer(
        routes, port=port,
        on_error=lambda exc: mcp_logbuf.log("HTTP-Fehler: %s: %s" % (type(exc).__name__, exc)))


def _aufsicht(server):
    """Annahmeschleife ueberwachen.

    Stirbt sie -- etwa an einem Speicherfehler beim Ausliefern --, lauscht nichts
    mehr auf dem Port, waehrend die Hauptschleife unveraendert weiterlaeuft. Das
    Board wirkt dann erreichbar (ping), ist aber tot. Deshalb hier neu starten
    statt den Server stillschweigend zu verlieren.
    """
    while True:
        try:
            server.serve_forever()
            return                       # regulaeres Ende (running wurde auf False gesetzt)
        except Exception as exc:  # noqa: BLE001
            mcp_logbuf.log("mcp_serve: Annahmeschleife neu gestartet nach %s: %s"
                           % (type(exc).__name__, exc))
            try:
                if server.sock is not None:
                    server.sock.close()
            except Exception:  # noqa: BLE001
                pass
            server.sock = None
            time.sleep(1)


def start(port=PORT):
    mcp, server = build_server(port=port)
    server._open()
    if not mcp_httpd.start_worker(_aufsicht, (server,)):
        raise RuntimeError("kein _thread-Modul -- Server kann nicht starten")
    print("MCP-Debug-Server laeuft auf Port %d (%d Tools)" % (port, len(mcp.tools)))
    return mcp, server


def main(port=PORT):
    """Als main.py auf dem Geraet: warten, damit der Thread weiterlaeuft."""
    start(port=port)
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
