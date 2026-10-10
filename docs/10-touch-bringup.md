# 10 -- Touch-Bring-up (AXS15231B, JC3248W535)

Ergebnis: **Der Touch funktioniert.** Gemessen am laufenden System: 8419
Treiberlesevorgänge in 300 s (~28 Hz), **262 erkannte Berührungspunkte** mit
echten Koordinaten, UI-Zähler von `Touch: 0` auf `Touch: 1`.

Es waren **vier unabhängige Fehler** -- jeder einzelne reicht, damit der Touch
tot wirkt:

## 1. LVGL bekam keinen Zeittakt (die eigentliche Hauptursache)

`lv.tick_get()` stand konstant auf 0. Ein `lv.timer_handler()` ohne fortlaufenden
Takt führt **keinen einzigen Timer** aus -- deshalb wurde der Input-Treiber nie
abgefragt (Messung: 0 Aufrufe von `_get_coords` in 60 s), es gab keine Animation
und keinen Refresh. Das Panel zeigte trotzdem sein Bild, weil der Bustreiber den
Framebuffer selbst wegschreibt -- das hat die Diagnose lange in die Irre geführt.

```python
last_tick = time.ticks_ms()
while True:
    now = time.ticks_ms()
    lv.tick_inc(time.ticks_diff(now, last_tick))   # <-- fehlte
    last_tick = now
    lv.timer_handler()
    mcp_screen.service_requests()
    time.sleep_ms(5)
```

Nach dem Fix: Takt läuft (20960 -> 21857), LVGL fragt den Treiber 41x in 1,5 s ab
(~27 Hz).

## 2. `enable_input_priority()` legt den Touch still

Der Aufruf stammt aus der Referenzkonfiguration (`straga/micropython_lcd`) und
schaltet den Indev auf `lv.INDEV_MODE.EVENT`. In `lv_indev.c` **pausiert
`lv_indev_set_mode` dabei LVGLs eigenen Abfrage-Timer** und setzt auf den
33-ms-Timer des Treibers. Faellt dessen Erzeugung aus (bei uns in einem
`try/except pass` versteckt), wird der Touch nie gelesen.

Loesung: Aufruf entfernen, Standardmodus (TIMER, Wert 1) nutzen -- LVGL fragt
selbst alle 33 ms ab.

## 3. GPIO 8 doppelt belegt: Display-DC = Touch-SCL

Die Referenzkonfiguration uebergibt dem Display-Bus `dc=8` -- und GPIO 8 ist
gleichzeitig der I2C-Takt des Touch. Messung: Ohne Display liest der Touch
(noch) Konstanten, **mit initialisiertem Display bricht der Bus ab**
(`OSError: [Errno 116] ETIMEDOUT`).

Im QSPI-Modus braucht das Panel kein DC: Das Kommando steckt im Opcode
(`0x02` Schreiben Kommando, `0x32` Schreiben Pixel). Das Hersteller-BSP uebergibt
dementsprechend `NULL`. Loesung: `dc=-1` ("kein DC-Pin" in ESP-IDF).
Danach bleibt der Touch-Bus nach der Display-Initialisierung benutzbar.

## 4. Reset-/Interrupt-Theorie war falsch (und wurde verworfen)

Zwischenzeitlich sah es so aus, als haenge der Controller im Reset (GPIO 12
flottet auf LOW, `RST` imponierte die Datenlage). Das Hersteller-BSP sagt:

```c
#define EXAMPLE_PIN_NUM_QSPI_TOUCH_RST  (-1)   // keine Reset-Leitung
#define EXAMPLE_PIN_NUM_QSPI_TOUCH_INT  (-1)   // keine Interrupt-Leitung
#define BSP_I2C_NUM                     (I2C_NUM_0)
#define BSP_I2C_CLK_SPEED_HZ            400000
```

GPIO 12 ist die SD-Karten-Taktleitung, GPIO 11 nicht der Touch-INT. Der
Controller wird rein pollend gelesen. Unsere Konfiguration folgt jetzt den
Herstellerwerten: **I2C-Port 0, 400 kHz, kein RST/INT**.

## Datenformat (zur Kontrolle)

Die Ruheantwort ist `85 85 85 85 85 85 85 85` -- **kein Fehler**, sondern
"nichts beruehrt" (Byte 1 = Punktzahl; der Vendor-Code verwirft `> 1` genauso wie
unser Treiber). Ein echter Datensatz sieht so aus:

```
00 01 80 45 01 b4 38 39
 |  |  |  |  |  |  |  +-- y_l
 |  |  |  |  |  |  +----- y_h (nur untere 4 Bit)
 |  |  |  |  |  +-------- nicht benutzt
 |  |  |  |  +----------- x_l
 |  |  |  +-------------- x_h (untere 4 Bit) + Event-Bits (oben)
 |  |  +----------------- 1 = ein Beruehrungspunkt
 |  +-------------------- Punktzahl
 +----------------------- Gestik
```

Dekodiert: x = 0x45 = 69, y = 0x1b4 = 436, Event "gedrueckt". Loslass-Frames
beginnen mit `ff`, Ruhe mit `85`.

## Pruefwerkzeuge (im Repo)

| Werkzeug | Zweck |
|---|---|
| `tools/touch_long.py [s]` | Lange Beobachtung: protokolliert jede von der Ruheantwort abweichende Antwort, erkannte Punkte und die UI-Beschriftung. Liest **nicht** selbst am I2C (zwei Leser am selben Geraet zerstoeren die Antworten). |
| `tools/touch_probe_rst.py` | Reset-/INT-Variante (nur fuer andere Board-Revisionen sinnvoll). |
| `tools/mcp_call.py <tool> [json]` | Einzelner MCP-Aufruf, auch fuer `exec_python`. |
| `firmware/device/probe_touch*.py` | Isolierte Bring-up-Proben (ohne/mit Display, Bustakt, Leselaenge, Kommandovarianten, Registerzugriff). |

## Was ausgeschlossen wurde

* **Kommandoprotokoll:** identisch in allen Referenzen (11 Byte
  `b5 ab a5 5a 00 00 00 08 00 00 00`, danach 8 Byte lesen).
* **Zugriffsschicht:** `i2c`-Modul und `machine.I2C` liefern identisch -- die
  Softwareschicht ist es nicht.
* **Bustakt / Leselaenge / Kommandovarianten / Registerzugriff / Wartezeiten:**
  durchgetestet, kein Unterschied.
* **Hardware:** Die Demosoftware des Herstellers kann Touch -- die Hardware ist
  in Ordnung. Die Angaben aus dem Hersteller-BSP (Pins, I2C-Port, kein DC) waren
  am Ende der Schluessel.
