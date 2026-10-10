# 12 -- LVGL-Fernbedienung: die Board-Oberflaeche live im Browser anzeigen und bedienen

Ziel: die LVGL-Oberflaeche des JC3248W535 (ESP32-S3, MicroPython + LVGL 9) im
eigenen Browser sehen **und** per Maus/Touch bedienen -- ein "Fernseh-Fernbedienungs"-
Modus, aber ausschliesslich ueber den **vorhandenen eigenen HTTP-Server**
(`mcp_httpd.py`), ohne neue Abhaengigkeiten und ohne LVGL aus einem Fremd-Thread
anzufassen.

Alle Zahlen in diesem Dokument sind am echten Board (192.168.1.168) gemessen,
nur lesend. Messskript: `tools/bench_vorschau.py`. Reproduzierbar mit
`python3 tools/bench_vorschau.py 3`.

---

## 1. Einordnung: was andere machen

### 1.1 LVGLRemoteServer (CubeCoders)

Referenz fuer "LVGL-Fenster auf den Desktop spiegeln". Wichtige Eigenschaften:

* **C++-Bibliothek** fuer ESP32/Arduino. Einbau in `disp_flush(disp, area, pixelmap)`
  (`remoteDisplay.sendRLE(area, pixelmap)`), danach wie gewohnt `lv_disp_flush_ready()`.
* **RLE-komprimierte Pakete**, **ein UDP-Paket pro Update** -- bewusst kein TCP, damit
  jedes Paket fuer sich steht (kein Verlust-Folgezustand).
* Uebertraegt nur den **Bounding-Rechteck-`area`** des Flushes, nicht den ganzen Schirm;
  der Empfaenger kennt Bildgroesse und Farbformat und rendert das Rechteck.
* **Zero allocation**: keine dynamische Speicherverwaltung, konstanter Fussabdruck.
* **Eingabe** kommt als simulierte Touch-Events zurueck (Maus -> Zeiger).
* Desktop-Client (Flutter/Windows) -- kein Browser.

Kernidee, die sich uebertragen laesst: **an den Flush anhaengen, nur das geaenderte
Rechteck senden, ein selbststehendes Paket pro Update.** Diese Idee ist auf unserem
Board goldwert (siehe Abschnitt 4.3) -- weil LVGL uns das Rechteck bereits liefert.

### 1.2 lv_port_esp32_web (danjulio)

Websocket-Treiber: LVGL schickt **Regions-Refresh** ueber eine WebSocket an eine
mitgelieferte HTML-Seite mit `<canvas>`; Maus-/Touch-Ereignisse gehen **ueber dieselbe
WebSocket** zurueck. Payload-Kopf: Pixeltiefe, Canvas-Breite/‑hoehe, Redraw-Region
(X1,Y1,X2,Y2), dann Pixeldaten. Rueckrichtung: Flag (Touch/Release) + X + Y. Mehrere
Browser gleichzeitig moeglich; beim Verbinden wird der Schirm einmal komplett
neugezeichnet. Genau dieses Modell passt am besten zu unserem Vorhaben.

### 1.3 WebAssembly-Loesungen (lv_web_emscripten, lvgl-wasm)

LVGL wird mit Emscripten nach **WebAssembly** uebersetzt und laeuft **komplett im
Browser**. Kein Geraet, keine Uebertragung -- aber es ist eine **zweite, unabhaengige
UI-Instanz**: sie zeigt nicht, was auf dem echten Panel passiert, und kann die echte
Hardware (GPIO, WLAN) nicht steuern. Fuer "Debug und Fernbedienung des laufenden
Geraets" unbrauchbar. (Anders waere es, wenn man die UI selbst browser-zuerst
entwickelt.)

### 1.4 MJPEG-/Multipart-Streaming und Canvas-Delta

* **MJPEG/`multipart/x-mixed-replace`:** eine dauerhafte HTTP-Antwort, die fortlaufend
  fertige Bilder (`JPEG`/`PNG`) schreibt; der Browser zeigt sie mit
  `<img src="/stream">` von allein an. Problem auf unserem Board: **jede** Bilddatei
  muesste auf dem Geraet kodiert werden -- und PNG in reinem Python kostet hier
  **3-22 s** (siehe `docs/11`). JPEG gibt es in diesem MicroPython-Bau nicht. Ohne
  fertiges Bildformat kann der Browser `<img>` nicht nutzen; man braucht dann doch
  eigenes JS, das die Rohbytes liest -- dann ist es faktisch ein eigener Push-Stream.
* **Canvas-Delta-Updates:** der Browser zeichnet nur geaenderte Rechtecke in ein
  Canvas -- das ist die Browserseite der ohnehin empfohlenen Delta-Uebertragung
  (Abschnitt 2/4).

### 1.5 Fazit der Einordnung

Fuer **unser** Board ist die tragfaehige Linie: **Rohpuffer RGB565 ueber den eigenen
HTTP-Server, nur geaenderte Rechtecke, Eingabe zurueck in einen zweiten LVGL-Indev.**
Ob dazwischen Polling, ein langlebiger Push-Stream oder eine WebSocket liegt, ist
eine Detailfrage -- alle drei sind mit dem vorhandenen Server machbar (Abschnitt 2).

---

## 2. Konkreter Entwurf fuer unser Board

### 2.1 Uebertragungsweg: Polling vs. Multipart-Push vs. WebSocket

Ausgangslage des Servers (`mcp_httpd.py`): HTTP/1.1, Routentabelle
`"METHOD /pfad" -> handler(Request) -> Response`, **kein WebSocket, kein
Chunked-Transfer, jede Antwort schliesst die Verbindung**, bis zu 4 Arbeitsthreads.

Gemessenes Nadeloehr ist **nicht die Rechenzeit, sondern der WLAN-Durchsatz**:
durchgehend **~660-830 KB/s** beim Senden eines 307200-Byte-Frames. Zusaetzlich
kostet **jeder neue Verbindungsaufbau ~67 ms** (gemessen: `GET /screen`, kleine
Antwort). Daraus die drei Wege:

| Weg | Prinzip | Vorteil | Nachteil | Bewertung |
|---|---|---|---|---|
| **Polling** (wie heute) | `fetch("/screen.raw?scale=1")` im Takt | nutzt den Server **unveraendert**; robust gegen Abbruch; kein neuer Servercode | 67 ms Aufschlag **pro** Frame; feste Rate auch ohne Aenderung | **P0** |
| **Multipart-/Laengen-Push** | **eine** langlebige `GET`-Antwort, in die der Handler fortlaufend `[4 Byte Laenge][RGB565]`-Frames schreibt | kein Verbindungsaufschlag (2,2 statt 1,9 fps bei Vollbild); Aenderungs-Push moeglich | Handler muss die Verbindung "besitzen"; Browser liest per `ReadableStream`; ein Worker-Thread je Betrachter dauerhaft belegt | **P2-Alternative** |
| **WebSocket** (binaer) | echte bidirektionale Sitzung; Bild hin, Zeiger zurueck | niedrigster Overhead; Eingabe auf **derselben** Leitung; nah an `lv_port_esp32_web` | Handshake muss **selbst** gerechnet werden; `mcp_httpd` muss den Socket an den Handler durchreichen; ein Thread je Sitzung | **Empfohlenes Ziel** |

**Wichtiger Befund zur Machbarkeit der WebSocket:** Dieser MicroPython-Bau bringt sie
fast mit. Am Board geprueft (lesend):

* `import websocket` liefert ein **C-Modul** (`extmod/modwebsocket.c`,
  Objekt `websocket.websocket(sock)`) mit `read`, `readinto`, `readline`, `write`,
  `close`, `ioctl` -- es erledigt **das gesamte Frame-Parsing/Masking**.
* `import asyncio` vorhanden (`start_server`).
* `hashlib.sha1(b"...").digest()` **funktioniert** (nur `hexdigest()` fehlt) und
  `ubinascii.b2a_base64()` liefert die Base64-Form -- damit ist
  `Sec-WebSocket-Accept = base64(sha1(key + GUID))` berechenbar.
* `_thread.allocate_lock()` vorhanden.

Es fehlt also nur der **HTTP-Upgrade-Handshake** (ca. 30 Zeilen Python) und ein
**Weg, den angenommenen Socket an einen Handler zu geben**. Letzteres ist die einzige
echte Aenderung am Server: entweder ein zweiter Listener auf eigenem Port (z. B. 81)
mit eigener Accept-Schleife -- **additiv, ohne `mcp_httpd` anzufassen** -- oder eine
kleine `Response`-Spielart "Verbindung bleibt offen", die den `stream` an den Handler
uebergibt.

**Empfehlung:**

* **P0/P1 (jetzt):** Polling. Kein Umbau, sofort sichtbar. Vollbild bei ~2 fps.
* **P2 (Ziel):** **WebSocket** auf eigenem Port (Route `/ws`), binaere Frames,
  dieselbe Sitzung traegt Bild **und** Zeiger. Der `websocket`-Extmod nimmt uns das
  Framing ab; das ist der geringste Risikoaufwand fuer die beste Wirkung. Der
  Multipart-Laengen-Push ist die Ausweichvariante, falls der Handshake scheitert.

### 2.2 Bildformat

**Rohpuffer RGB565, 2 Byte/Pixel, `rgb565_byte_swap=True`** -- exakt das, was
`/screen.raw?scale=1` heute liefert und was `app.js` bereits im Canvas korrekt
zurueckrechnet (Zeile 167-173: `roh[i] | roh[i+1]<<8`, dann RGB565->RGBA). Kein
Geraete-seitiges Kodieren.

Bewertung der Formatalternativen **auf diesem Board**:

| Format | Aufwand am Geraet | Urteil |
|---|---|---|
| **Roh RGB565** | nur Kopie (307200 B = **38 ms**, 8,1 MB/s memcpy) | **Standard** |
| **Deflate** (`deflate.DeflateIO` existiert) | reines Python-Deflate kostet **3-22 s** pro Frame | **ausgeschlossen** |
| **RLE** | Encoder waere reines Python; schon der *Diff-Scan* kostet 395 ms (s. 4.3) | **nur in C sinnvoll** -- mit reinem Python unbrauchbar |
| **Delta-Rechtecke** | LVGL liefert das Rechteck **umsonst** (C-seitig, s. 4.3) | **bevorzugt ab P2** |
| **PNG/JPEG** | PNG 3-22 s; JPEG fehlt | **ausgeschlossen** |

Merksatz: **Nicht auf dem Geraet in Python ueber Pixel laufen.** Weder verkleinern
(2.3), noch komprimieren, noch diffen. Ueber Pixel laeuft der **Browser** (JS ist
schnell) oder ein C-Pfad im LVGL-Flush.

### 2.3 Bildrate, Speicher, CPU

* Native Aufloesung 320x480 ist die **einzige** sinnvolle Uebertragungsgroesse: das
  geraeteseitige Verkleinern ist der langsamste Pfad ueberhaupt (Abschnitt 4.2). Will
  man kleiner darstellen, **skaliert der Browser** das Canvas hoch/runter -- das ist
  gratis.
* **Vollbild-Push** erreicht **~2,2 fps** (0,455 s Transfer + ~0,067 s Aufschlag
  beim Polling). Das ist fuer "mitlesen/debuggen" brauchbar, fuer flüssige Animationen
  nicht.
* **Delta-Rechtecke ab P2** heben das auf **8-26 fps** fuer typische UI-Aenderungen
  (Extrapolation, Abschnitt 4.4); im Ruhezustand fluessen **0 Byte**.
* **Speicher:** anliegendes Vollbild braucht in PSRAM einen Schatten-/Sendepuffer von
  307200 B. Der MicroPython-GC-Heap ist PSRAM-gedeckt (frei gemessen: **~6,0-6,5 MB**).
  Der **interne SRAM** ist mit **~32 KB frei** sehr knapp -- jede Zusatzstruktur dort
  (Queues, Socket-Puffer) klein halten und Datenpuffer in PSRAM lassen.
* **CPU:** Der eigentliche Engpass ist die Funkstrecke; das Senden laeuft in C. Der
  Python-Anteil pro Vollbild ist ~2 Kopien (38 ms). Wichtig: der **Framebuffer-Abzug
  beruehrt LVGL nicht** -- er liest nur Speicher, die Hauptschleife laeuft weiter.

---

## 3. Eingabeweg: Browser-Zeiger -> LVGL

Wir koennen keinen bestehenden LVGL-Indev "fernsteuern", weil der physische Touch
(`axs15231.AXS15231`) seine Koordinaten selbst am I2C liest. Stattdessen registrieren
wir einen **zweiten Pointer-Indev**, dessen Python-Lese-Callback die Ereignisse aus
einer Warteschlange zieht. Verifizierte API (aus
`/opt/lvgl_micropython/api_drivers/py_api_drivers/frozen/indev/_indev_base.py`,
`pointer_framework.py` und `lvgl.pyi`):

* `lv.indev_create()` -> `indev_t` (`lvgl.pyi:19701`)
* `indev.set_type(lv.INDEV_TYPE.POINTER)` (`:10842`, `INDEV_TYPE` ab `:979`)
* `indev.set_display(lv.display_get_default())` (`:10866`)
* `indev.set_read_cb(cb)` (`:10848`) -- `cb(drv, data)`; `data` ist `indev_data_t`
  mit `data.point.x`, `data.point.y`, `data.state`, `data.continue_reading`
  (`:11204-11278`)
* `indev.enable(True)` (`:10836`)

`_indev_base.IndevBase._read` ist genau das Muster: `data.point.x/y` setzen,
`data.state` setzen, `data.continue_reading = False`.

### 3.1 Empfohlener Code (laeuft im LVGL-/Hauptthread)

```python
# New file: firmware/mcpsrv/mcp_pointer.py
# A second LVGL pointer indev fed from a queue. LVGL is not thread-safe, so this
# object is created in the main thread; only the plain list is touched by the
# server thread (guarded by a lock). No LVGL call happens outside the main loop.
import _thread
import lvgl as lv

_LOCK = _thread.allocate_lock()
_EVENTS = []          # each item: (pressed: bool, x: int, y: int)
_INDEV = None


def push(x, y, pressed):
    """Called from the HTTP server thread with raw panel coordinates."""
    with _LOCK:
        _EVENTS.append((bool(pressed), int(x), int(y)))


def _pop():
    with _LOCK:
        return _EVENTS.pop(0) if _EVENTS else None


def _read_cb(drv, data):
    ev = _pop()
    if ev is None:
        data.state = lv.INDEV_STATE.RELEASED
    else:
        pressed, x, y = ev
        data.point.x, data.point.y = x, y
        data.state = (lv.INDEV_STATE.PRESSED if pressed
                      else lv.INDEV_STATE.RELEASED)
    data.continue_reading = False


def create():
    """Create and enable the web-pointer indev. MUST run in the LVGL thread,
    after the display is initialised (IndevBase requires a display)."""
    global _INDEV
    if _INDEV is not None:
        return _INDEV
    indev = lv.indev_create()
    indev.set_type(lv.INDEV_TYPE.POINTER)
    indev.set_display(lv.display_get_default())
    indev.set_read_cb(_read_cb)
    indev.enable(True)
    _INDEV = indev
    return _INDEV
```

`main.py` bekommt **eine** Zeile nach `start_touch()`: `mcp_pointer.create()`
(im LVGL-Thread, also vor der Hauptschleife). Der bestehende physische Touch-Indev
bleibt unveraendert daneben bestehen -- LVGL wertet beide Zeigerquellen aus.

### 3.2 Alternative: `PointerDriver`-Unterklasse

Wer die vorhandene Kette mit Kalibrierung nutzen will, kann
`pointer_framework.PointerDriver` unterklassen und `_get_coords()` ueberschreiben:

```python
class WebPointer(pointer_framework.PointerDriver):
    def _get_coords(self):
        ev = _pop()
        if ev is None:
            return None                      # -> Driver meldet RELEASED
        pressed, x, y = ev
        return (self.PRESSED if pressed else self.RELEASED), x, y
```

`PointerDriver._read` behandelt `None` korrekt (Zustand RELEASED, Koordinaten
bleiben auf dem letzten Wert). Nachteil: erzwingt Kalibrierdaten und die
Display-Wrapper-Logik. Fuer eingespeiste Pixelkoordinaten ist der direkte
`lv.indev_create`-Weg (3.1) schlanker und exakter.

### 3.3 Die Server-Seite (Eingabe)

Ein winziger POST-Endpunkt reicht, weil die Eingaberichtung **sehr** wenig Daten
bewegt (ein paar Dutzend Byte je Ereignis) -- der 67-ms-Aufschlag faellt hier nicht
ins Gewicht:

```python
# GET/POST /api/pointer?x=..&y=..&p=1   (p=1 drauf, p=0 los)
def api_pointer(req):
    x = int(req.arg("x", "0")); y = int(req.arg("y", "0"))
    p = req.arg("p", "1") == "1"
    mcp_pointer.push(x, y, p)          # nur Liste anfassen, kein LVGL
    return mcp_httpd.json_response({"ok": True})
```

Im Browser (in `app.js` des Viewers): `pointerdown`/`pointermove`/`pointerup` auf dem
Canvas; `clientX/Y` minus Canvas-Ursprung, durch den Darstellungsmassstab geteilt
-> Panel-Koordinaten -> `fetch("/api/pointer?x=..&y=..&p=..")`. Bei einer WebSocket
(P2) entfaellt der zweite Kanal: dieselbe Sitzung traegt das Zeigerpaket
`[flag][x_hi][x_lo][y_hi][y_lo]` (Muster aus `lv_port_esp32_web`).

**Threadsicherheit:** LVGL wird **ausschliesslich** im Lese-Callback im Hauptthread
angefasst. Der Server-Thread schiebt nur Tupel in eine Liste unter einem Lock -- dieselbe
Disziplin wie `mcp_screen.request()`.

---

## 4. Gemessene Werte am echten Board

Board: 192.168.1.168, `gc_free` ~6,0-6,5 MB, `freq 240 MHz`, Bildquelle
`Display-Framebuffer 1` (320x480 RGB565, `byte_swap=True`). Alle Messungen **nur
lesend** (GET + `exec_python` ohne Zustandsaenderung).

### 4.1 Vollbild / Durchsatz (`tools/bench_vorschau.py`)

| Aufruf | Bytes | Aufloesung | Zeit | Durchsatz |
|---|---|---|---|---|
| `/screen.raw?scale=1` | 307200 | 320x480 | **0,397-0,602 s**, Mittel **0,457 s** (n=10) | **657 KB/s**, **~2,2 fps** |
| `/screen.raw?scale=2` | 76800 | 160x240 | **4,6-6,0 s** | ~16 KB/s |
| `/screen.raw?scale=4` | 19200 | 80x120 | 1,19-1,32 s | ~15 KB/s |
| `/screen.raw?scale=8` | 4800 | 40x60 | ~0,39 s | ~12 KB/s |
| `GET /screen` (klein) | ~120 | -- | **~0,067 s** | (Aufschlagsmessung) |

Lesart:

* **`scale=1` ist der schnellste Weg** -- es ist die reine Framebuffer-Kopie plus
  Funkstrecke. Jede Verkleinerung ist **langsamer**, nicht schneller (4.2).
* Reale Netto-Rate: **~660-830 KB/s**. Das ist das Bandbreiten-Budget fuer alles.
* **~67 ms pro Verbindung** -- bei Vollbild vernachlaessigbar (400 ms dominiert), bei
  kleinen Delta-Rechtecken der **beherrschende** Posten (4.4). Genau deshalb ist fuer
  P2 ein dauerhafter Kanal wichtig.

### 4.2 Warum Verkleinern auf dem Geraet scheitert

`mcp_screen._downscale()` laeuft als **Python-Schleife ueber jedes Ziel-Pixel**
(Zeile 123-137). `scale=2` = 76800 Python-Iterationen -> **4,6-6,0 s**. Deshalb ist
der heute in der Weboberflaeche genutzte `scale=4`-Weg (~1,2 s/Frame) **kein** guter
Ausgangspunkt fuer einen Live-Viewer. Fuer Live gilt: **Vollbild roh senden** und im
Browser skalieren.

### 4.3 Speicher-/CPU-Kosten auf dem Board (`exec_python`, nur rechnend)

* **Framebuffer-Kopie** 307200 B (`bytearray(fb)`): **38 ms** -> **8,1 MB/s**
  Speicherbandbreite. Das ist der einzige noetige Python-Anteil; er ist 12x schneller
  als die Funkstrecke, also irrelevant.
* **Diff-Scan in reinem Python** (480 Zeilen als Zeilenvergleich): **395 ms/Frame** ->
  fuer einen Frame-Diff **unbrauchbar**. Ein Python-Schattenpuffer-Vergleich ist damit
  **kein** gangbarer Weg.
* **Idle-Diff** (zwei Vollbilder im Abstand 1 s): **0 unterschiedliche Pixel** von
  153600. Bei stehender UI ist der Delta-Uebertrag **0 Byte** -- der Nutzen von
  Delta-Rechtecken ist also maximal.
* **Heap:** `gc_free` schwankte waehrend der Benchmark-Runde um ~0,4 MB
  (6,44 -> 6,04 MB, danach erholt) -- die Vollbild-Puffer erzeugen Allokations-Churn.
  Kein Leck, aber Grund, Sendepuffer wiederzuverwenden statt pro Frame neu zu bauen.
  **Interner SRAM frei: ~32 KB** -- sehr knapp.

### 4.4 Delta-Rechtecke: die entscheidende Wiederverwendung (Schluesselbefund)

Der laufende Display-Treiber ist im **FULL-Render-Modus mit vollen Framebuffern**
(`display_driver_framework.py:253`, 2 x 307200 B), und **`_flush_cb(_, area, color_p)`
bekommt von LVGL das geaenderte Rechteck `area`** (`:580`). Genau der Ansatzpunkt von
`LVGLRemoteServer`: **statt den Schirm zu diffen, das fertige Rechteck aus dem Flush
mitnehmen.** Kein Python-Scan noetig, keine 395 ms.

Extrapolation des erreichbaren Bildraten-Budgets bei **660 KB/s** (gemessenes
`_flush`-`area`-Rechteck -> bytes):

| Rechteck | Bytes | Polling (mit 67 ms) | **dauerhafter Kanal** |
|---|---|---|---|
| 320x480 (Vollbild) | 307200 | 1,9 fps | 2,2 fps |
| 320x240 | 153600 | 3,4 fps | 4,4 fps |
| 320x120 | 76800 | 5,5 fps | 8,8 fps |
| 160x120 | 38400 | 8,1 fps | 17,6 fps |
| 320x40 (Zaehler/Label) | 25600 | 9,5 fps | 26,4 fps |
| 80x60 | 9600 | 12,3 fps | 70 fps (LVGL-Refresh deckelt) |

**Fazit:** Vollbild = "mitlesen/debuggen"; typische UI-Aenderungen per Flush-Rechteck
+ dauerhaftem Kanal = fluessige Fernbedienung.

---

## 5. Umsetzungsplan in Stufen

### P0 -- nur Anzeige, niedrige Bildrate (kein Firmware-Eingriff in LVGL)

* **Neue Datei** `firmware/webfiles/viewer.html` + `viewer.js` (bzw. ein Reiter
  "Bildschirm" in der bestehenden `index.html`). Holt im Takt
  `fetch("/screen.raw?scale=1", {cache:"no-store"})`, liest `X-Screen` und
  `X-Byte-Swap`, rechnet RGB565 im Canvas (Vorlage: `app.js` `shot()`, Zeile 145-179),
  zeichnet. **Kein** `scale>1` benutzen (4.2).
* **Neuer Endpunkt** in `mcp_tools.build_routes()`: nichts noetig -- `/screen.raw`
  existiert. Optional ein `GET /viewer` -> `statisch("viewer.html")` in
  `mcp_webui.build_routes()`.
* **Ergebnis:** ~2 fps, reine Anzeige. Sofort nutzbar, ohne Risiko.

### P1 -- Eingabe (Fernbedienung)

* **Neue Datei** `firmware/mcpsrv/mcp_pointer.py` (Code aus 3.1).
* **`firmware/device/main.py`:** eine Zeile `mcp_pointer.create()` nach
  `start_touch()` (LVGL-Thread!). Das ist die **einzige** Beruehrung einer
  Bestandsdatei -- absichtlich minimal.
* **Neuer Endpunkt** `GET/POST /api/pointer` in `mcp_webui.build_routes()` +
  `api_pointer()` (3.3).
* **`viewer.js`:** `pointerdown/move/up` -> Koordinaten umrechnen -> `/api/pointer`.
* **Ergebnis:** Klicken/Ziehen im Browser bedient die echte UI; auf dem Panel sichtbar.

### P2 -- Optimierung auf geaenderte Bereiche + dauerhafter Kanal

* **Delta-Quelle (Firmware, klein):** den Display-Flush anzapfen, ohne LVGL zu
  duplizieren. Eleganteste Variante: `axs15231b.AXS15231B._flush_cb` bzw. den
  `display_driver_framework`-Flush **erweitern** um einen Hook, der `area` +
  `color_p`-Ausschnitt an `mcp_screen` reicht (z. B. `mcp_screen.push_region(x1,y1,x2,y2, view)`).
  Der Treiber liegt in `firmware/device/drivers/axs15231b.py` (bereits geforkt) bzw.
  `display_driver_framework.py`. Achtung: Hook **im LVGL-Thread** ausfuehren, nur
  kopieren/ablegen.
* **Kanal:** `websocket`-Extmod + `asyncio` auf eigenem Port (z. B. 81, Route `/ws`),
  additiv neben `mcp_httpd` -- so bleibt der bestehende Server unberuehrt. Handshake
  mit `hashlib.sha1().digest()` + `ubinascii.b2a_base64()`; binaere Frames
  `[x1][y1][x2][y2][rgb565...]` (Muster `lv_port_esp32_web`); Zeiger-Rueckpaket auf
  derselben Leitung.
  Ausweichvariante ohne WebSocket: langlebige `GET`-Antwort mit
  `[4 Byte Laenge][Frame]`-Praefix; dafuer muss `mcp_httpd` den Socket an den Handler
  durchreichen.
* **Browser:** Canvas-Delta zeichnen (`ctx.putImageData(img, x1, y1)`), nur das
  empfangene Rechteck.
* **Ergebnis:** Ruhe = 0 Byte; typische UI-Aenderungen ~8-26 fps (4.4).

### Betroffene / neue Dateien im Ueberblick

| Datei | Stufe | Art |
|---|---|---|
| `firmware/webfiles/viewer.html`, `viewer.js` | P0 | **neu** |
| `firmware/webfiles/app.js` (Reiter) | P0 | Bestand (optional) |
| `firmware/mcpsrv/mcp_pointer.py` | P1 | **neu** |
| `firmware/device/main.py` | P1 | Bestand (eine Zeile) |
| `firmware/mcpsrv/mcp_webui.py` (`/api/pointer`) | P1 | Bestand (additiv) |
| `firmware/mcpsrv/mcp_screen.py` (`push_region`) | P2 | Bestand (additiv) |
| `firmware/device/drivers/axs15231b.py` / `display_driver_framework.py` (Flush-Hook) | P2 | Bestand (klein) |
| `firmware/mcpsrv/mcp_ws.py` (WS-Server, Port 81) | P2 | **neu** |
| `tools/bench_vorschau.py` | Messung | **neu** (bereits angelegt) |

---

## 6. Risiken und offene Punkte

* **Threadsicherheit (groesste Gefahr).** LVGL darf **nur** im Hauptthread angefasst
  werden. Der Zeiger-Callback laeuft dort (gut); die Queue wird per Lock geteilt.
  Jede Abkuerzung -- z. B. `lv.obj`-Aufrufe aus dem Server-Thread -- fuehrt zu
  sporadischen Abstuerzen. Disziplin wie bei `mcp_screen.request()` beibehalten.
* **Speicher.** Ein 307200-Byte-Sendepuffer muss in **PSRAM** liegen; der **interne
  SRAM ist mit ~32 KB frei** praktisch voll. Bei mehreren Betrachtern (bis 4 Worker)
  vorher rechnen: 4 x Vollbildpuffer = ~1,2 MB -- in PSRAM machbar, im internen SRAM
  unmoeglich. Puffer **wiederverwenden** (Churn gemessen: ~0,4 MB je Runde).
* **LVGL-Invalidate/Flush-Verhalten.** Der Delta-Nutzen haengt daran, dass der
  Flush-`area` **wirklich klein** ist. Bei **Vollbild-Refresh** (dieses Panel braucht
  vollen Bildwiederholaufbau mit gestuecktem Transfer ueber `SPIBusFast`) kann die
  `area` **gross** ausfallen -- dann schrumpft der Delta-Vorteil. Vor P2 **messen**:
  Groesse der `flush`-`area` bei typischen UI-Aenderungen protokollieren. Ist sie
  dauerhaft ~Vollbild, bleibt nur Vollbild-Push (2,2 fps) oder SCALE im Browser.
* **Tearing / Konsistenz.** Der Abzug liest den Framebuffer **waehrend** LVGL
  schreibt. Fuer Vorschau unerheblich, fuer Delta-Rechtecke aus dem Flush aber
  wichtig: dort den Puffer **im Flush-Moment kopieren**, nicht spaeter aus dem
  Framebuffer (sonst reisst das Rechteck). Die Flush-`color_p`-Sicht ist der richtige
  Ort.
* **Verbindungs-Aufschlag (67 ms).** Bei Polling begrenzt er kleine Deltas hart
  (12 fps-Decke fuer 80x60). Entweder **dauerhafter Kanal** (P2) oder bewusst
  **Vollbild @ 2 fps**.
* **WebSocket-Aufwand.** Handshake und Socket-Durchreichung sind Handarbeit; `asyncio`
  und der Radio-Treiber teilen sich die CPU. Wenn eine Sitzung einen Worker dauerhaft
  belegt, sinkt die Zahl gleichzeitiger Debug-Verbindungen -- Port 81/`/ws` getrennt
  fuehren, damit der Debug-Server erreichbar bleibt.
* **Aufsicht.** `mcp_serve._aufsicht` startet nur den **eigenen** Listener neu. Ein
  zweiter WS-Listener braucht dieselbe Aufsicht, sonst stirbt er still (bekanntes
  Muster: Board pingt, aber Port tot).
* **Keine Authentifizierung.** Wie die bestehende Oberflaeche: beliebiger Code aus dem
  Netz ausfuehrbar, jetzt **plus** aktive Bedienung des Panels. Nur vertrauenswuerdiges
  LAN; idealerweise eine Not-Aus-Sperre ("Fernbedienung aus").
* **Offene Frage Bildrate-Wahrnehmung.** Der Browser zeichnet nur so oft, wie `requestAnimationFrame`
  laeuft (60 Hz) -- die echte Decke setzt das Netz. Bei Vollbild sind im Standbild
  ~2 fps zu erwarten; fuer Animationen (Fortschrittsbalken) liefert erst P2 Fluessigkeit.

---

## Anhang: Rohdaten der Messung

```
copy 307200 bytes: 37957 us (8.09 MB/s)          # bytearray(frame_buffer1)
scan 480 rows (307200 B): 395049 us               # reiner Python-Zeilenvergleich
gc_free=6313760 gc_alloc=410336                   # waehrend Messung
internal heap frei: ~32031 Byte

scale=1 x10: 0.602 0.423 0.428 0.407 0.592 0.431 0.428 0.432 0.397 0.429
             mean 0.457 s -> 2.19 fps, ~657 KB/s
scale=2 x3 : 6.048 4.606 4.621 s
scale=4 x3 : 1.187 1.199 1.324 s
scale=8 x3 : 0.391 0.381 0.387 s
GET /screen x10: mean 0.067 s

idle diff (2 Frames, 1 s Abstand): 0 geaenderte Pixel / 153600

Board-Features: websocket(extmod, Framing)  asyncio: ok  hashlib.sha1().digest(): ok
                ubinascii.b2a_base64: ok     _thread.allocate_lock: ok
                deflate.DeflateIO: vorhanden
Display: FULL-Render-Modus, 2 x 307200-B-Framebuffer, _flush_cb erhaelt area=Rechteck
```
