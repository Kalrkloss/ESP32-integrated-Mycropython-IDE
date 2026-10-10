# MCP-Debug-Server auf dem ESP32

Ziel: Der Agent soll das Board **selbst** debuggen und testen können — Screenshots sehen,
Code ausführen, Logs lesen, Dateien schreiben, Board neu starten — ohne dass jemand
daneben sitzt und ein Terminal hält.

## Aufbau

`firmware/mcpsrv/` (flache Module, damit sie sich auf dem Gerät einfach einfrieren lassen):

| Datei | Aufgabe |
|---|---|
| `mcp_serve.py` | Einstieg: baut MCP-Server + Router, startet den HTTP-Server in einem `_thread` |
| `mcp_protocol.py` | MCP/JSON-RPC-Kern: `initialize`, `notifications/initialized`, `tools/list`, `tools/call`, `ping`; Text-/Bild-Ergebnisse; Base64 |
| `mcp_httpd.py` | Minimal-HTTP/1.1-Server (Sockets, keine Fremdbibliothek), Request-Parser, Antwort-Writer, SSE-Writer |
| `mcp_tools.py` | Tool-Definitionen + Klartext-Endpunkte |
| `mcp_screen.py` | Bildquelle: angehängter Framebuffer (primär) oder LVGL-Snapshot (Fallback), Downscaling, Widget-Baum |
| `mcp_png.py` | RGB565 → PNG, ohne Fremdbibliothek (echtes Deflate wenn `deflate` da ist, sonst gültige Stored-Blöcke) |
| `mcp_logbuf.py` | stdout-Mitschnitt in einen Ringpuffer (Tee) |

## Endpunkte

MCP (Streamable HTTP, ein Endpunkt):

```
POST /mcp        JSON-RPC 2.0; Antwort als application/json,
                 auf Wunsch (Accept: text/event-stream) als SSE
```

Klartext zusätzlich — schneller als MCP für die Iteration per `curl`:

```
GET  /               Status + Tool-Liste
GET  /screen.png     Screenshot (?scale=2 verkleinert, ?format=raw = RGB565)
GET  /log            letzte Konsolenausgaben (?clear=1 leert den Puffer)
POST /exec           Python-Body auf dem Gerät ausführen
GET  /info           Geraeteinfos (JSON)
POST /reset          Neustart (verzögert)
```

## Tools

| Tool | Zweck |
|---|---|
| `screenshot(scale, format)` | **Bildschirm als PNG** — das wichtigste Werkzeug für UI-Arbeit |
| `exec_python(code)` | Code auf dem Gerät ausführen, stdout + Log-Auszug zurück |
| `files(action, path, data)` | `list`, `read`, `write`, `remove`, `mkdir`, `stat`, `df` |
| `device_info()` | Chip, Frequenz, Speicher, WLAN-Status, Laufzeit, Bildquelle |
| `logs(clear)` | Konsolenausgabe |
| `lvgl_tree(max_nodes)` | Widget-Baum der aktiven Screen (Klassen, Geometrie, Text) |
| `i2c_scan(sda, scl, freq)` | Board-Bring-up, Touch-Controller finden |
| `wifi(action, ssid, password)` | `status`, `scan`, `connect`, `disconnect` |
| `reset(delay_ms)` | Neustart |

## Host-Tests (ohne Hardware)

```bash
python3 tests/test_mcpsrv.py
```

49 Checks: PNG-Kodierung (Chunk-CRC, Scanlines, Byte-Reihenfolge), MCP/JSON-RPC
(Version-Aushandlung, Notifications, Fehlerpfade), HTTP-Layer (Parsing, `Content-Length`),
und ein Ende-zu-Ende-Durchlauf über echte Sockets (initialize → tools/list →
tools/call screenshot → PNG dekodiert und geprüft, `/screen.png`, `/exec`, 202 für
Notifications, SSE-Antwort, 404).

## Auf dem Gerät verifiziert (MicroPython)

Am Board nachgemessen und deshalb so implementiert:

- **LVGL ist nicht thread-sicher.** Snapshots und Widget-Baum laufen als Auftrag über
  `mcp_screen.request(...)`; die Hauptschleife führt sie mit
  `mcp_screen.service_requests()` aus. Ergebnisse liegen **pro Auftragsnummer** in
  `_RESULTS` — ein verspätetes Ergebnis hat sonst den nächsten Auftrag verfälscht
  (genau das war zu beobachten). Timeout 20 s, weil ein Snapshot 1,6 s (scale=4) bis
  mehrere Sekunden (scale=1) braucht.
- **Eine Verbindung darf die Annahmeschleife nicht blockieren.** `HttpServer` bedient
  jede Verbindung in einem eigenen Thread (max. 3). Vorher hat ein einziger hängender
  Handler den ganzen Server lahmgelegt (Antworten kamen nie an).
- **`_thread.start_new_thread(fn, args)`** — der dritte Parameter ist in MicroPython
  *kwargs*, nicht die Stackgröße. Stackgröße global über `_thread.stack_size(n)`;
  ein Zahlenwert als drittes Argument lässt den Thread stumm scheitern.
- **`socket` hat kein `flush()`** — `write_response` prüft es jetzt.
- **`sys.stdout` kann fehlen** (`mcp_logbuf.install()` bricht nicht mehr ab) und
  **`bytes.decode()` nimmt `errors` nur positional**
  (`bytes.decode()` → `TypeError: function doesn't take keyword arguments`).
- **Snapshot-API** (LVGL 9.4 im Binding): `lv.snapshot_take(obj, lv.COLOR_FORMAT.RGB565)`
  liefert `lv_draw_buf_t`; Maße über `.header.w/.h/.stride` (`.cf = 18` = RGB565),
  Daten über `.data` als `C_Array` → mit `__dereference__(size)` in eine `memoryview`,
  daraus direkt verkleinern und erst dann `snap.destroy()`.
- **`deflate` ist vorhanden** (echte PNG-Kompression nutzbar), `zlib` fehlt; der
  PNG-Encoder hat dafür einen Stored-Block-Rückfall.
- **KeyboardInterrupt durchreichen**: In MicroPython erbt es von `Exception`; ein
  blanket `except Exception` in der Hauptschleife macht das Board für Ctrl-C und damit
  für `mpremote` unerreichbar.
- **scale=2 ist der Standard für Screenshots** (160×240): full-res dauert auf dem ESP32
  so lange, dass der HTTP-Client timeoutet.

## Betrieb auf dem Gerät (geplant)

1. `mcp_serve.start()` nach dem WLAN-Connect aufrufen (aus `main.py`).
2. Die LVGL-App hängt ihren Framebuffer an: `mcp_screen.attach(buf, w, h, byte_swap=True)`.
   Ohne `attach` versucht der Server einen LVGL-Snapshot — dessen API ist je Binding-Version
   unterschiedlich, deshalb der defensive Pfad.
3. Auf dem Server: `hermes mcp add esp32 --url http://<ip>/mcp`.
4. Erreichbarkeit prüfen: `curl -s http://<ip>/`, dann `curl -s -X POST http://<ip>/mcp -d ...`.

## Offene Punkte (auf Hardware zu verifizieren)

- Ob Hermes' MCP-Client den `application/json`-Antwortmodus akzeptiert oder SSE verlangt
  (beide Antwortarten sind implementiert).
- LVGL-`snapshot_take`-API des gebauten Bindings (Fallback-Pfad).
- Ob LVGL-Aufrufe aus dem Server-Thread erlaubt sind; wenn nicht, laufen LVGL-Aktionen
  über eine Queue, die im Main-Thread (LVGL-Task) abgearbeitet wird.
- Stromversorgung/Takt des QSPI-Panels beim Full-Refresh.
