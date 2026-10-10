# Display-Bring-up JC3248W535 — gemessene Befunde

Stand: 2026-10-10, alles auf echter Hardware gemessen (Board am Dock-Port 1‑4.4.3,
Webcam am Server als „Auge", MCP-Debug-Server am Board).

## Symptom am Anfang

- Backlight an, Panel schwarz.
- Beim Start zeigt das Panel **helle, zufällige bunte Pixel** (GRAM-Rauschen).
- Das heißt: das Panel wird angesteuert (Backlight, QSPI-Kommunikation), aber es
  bekommt keine **gültigen Bilddaten**.

## Messung 1: Buslimit

`machine.SPI.Bus` setzt `max_transfer_sz = SPI_LL_DMA_MAX_BIT_LEN / 8` = **32768 Byte**
(siehe `micropy_updates/esp32/machine_hw_spi.c`). Ein kompletter Frame ist
320 × 480 × 2 = **307200 Byte** — als *eine* Transaktion scheitert er mit
`OSError: 257(lcd_panel_io_tx_color)` (ESP_ERR_NO_MEM).

| Größe | Ergebnis |
|---|---|
| 30720 Byte (48 Zeilen) | geht |
| 32000 Byte (50 Zeilen) | scheitert (257) |

Aus dem automatischen Pufferschema des Frameworks: es legt **2 × 30720 Byte** an und
wählt damit Partial-Render.

## Messung 2: Partial-Render läuft ohne Fehler, zeigt aber nichts

Mit vom Framework verwalteten Puffern (2 × 30720 Byte, internes DMA) laufen alle Flushes
**fehlerfrei durch** — das Panel blieb trotzdem schwarz (Kamerabild: nur Reflexionen).
Grund: Im QSPI-Modus setzt der Treiber in `_set_memory_location` nur **CASET** und
verlässt sich auf den Adresszähler des Panels. LVGL-Partial-Render schreibt aber
48-Zeilen-Bänder an beliebiger Stelle; die Zeilenadresse (RASET) wird nie gesetzt.
Ohne Full-Frame-Refresh läuft der Zähler auseinander.

## Messung 3: Full-Frame mit eigenem Chunking bricht ab

Eigener Framebuffer in PSRAM (307200 Byte) + abgeleiteter Treiber, der den Frame in
10 × 30720-Byte-Stücke zerlegt (erster Block mit Kommando, weitere mit `cmd=-1`):
Panel-Init ok, danach **USB-Verbindung weg (EIO)** → das Board startet neu (Panik/Reset)
beim ersten Flush. Zusätzlich liefert das Framework im Full-Frame-Modus für
`_set_memory_location` nur noch `_dummy_set_memory_location` → **`_RAMWR = 0x2C` ohne die
QSPI-Kodierung** (`(0x32 << 24) | (cmd << 8)`), die dieser Treiber im Quad-Modus braucht.

## Konsequenz und Lösung

Der Mainline-Bau von `lvgl_micropython` kann dieses Panel nicht bedienen: Es fehlt der
DMA-Bustreiber, der große Transfers stückelt (`SPIBusFast`).

**Gangbarer Weg (so umgesetzt):** Nur dieses eine Feature in den Baum übernehmen, der
sauber baut. Der gesamte Unterschied zwischen Fork und Mainline liegt in
`ext_mod/lcd_bus/`:

- neu: `esp32_src/spi_bus_fast.c`, `spi_bus_fast_task.c`, `spi_bus_fast_rotation.c`
  und die zugehörigen Header
- geändert: `modlcd_bus.c` (15 Zeilen), `esp32_src/i80_bus.c` (7), `esp32_include/rgb_bus.h` (3),
  `micropython.cmake` (3 Einträge für die neuen Quelldateien)

Also: `ext_mod/lcd_bus/` aus dem Fork kopieren (Sicherung als `lcd_bus.orig`), Rest des
Mainline-Baums behalten, neu bauen. Kein Fork-Build nötig — dessen Kompilierung scheitert
ohnehin an einem Versionskonflikt der Komponenten (`espressif__esp_tinyusb` neu, aber
`espressif__tinyusb` alt: `error: 'CFG_TUD_CDC_EP_BUFSIZE' undeclared`).

**Zweiter notwendiger Patch:** `lcd_bus.SPIBusFast` ist im C-Modul ein **eigener Typ**
(`isinstance(bus, lcd_bus.SPIBus)` ist `False`). Der Display-Treiber prüft genau darauf und
lehnt ihn mit `RuntimeError: incompatable bus driver` ab; außerdem schlägt dann die
QSPI-Erkennung fehl (32-Bit-Kommandos statt 8). Deshalb liegt in
`firmware/device/drivers/axs15231b.py` eine Kopie, die `SPIBusFast` wie `SPIBus`
behandelt (Dateisystem überdeckt das eingefrorene Modul).

**Ergebnis (am Gerät und per Kamera bestätigt):** `SPIBusFast` + zwei volle PSRAM-Framebuffer
(je 307200 Byte) + gepatchter Treiber → Panel zeigt den LVGL-Inhalt korrekt, Farben
stimmen (Rot/Grün/Blau in der gezeichneten Reihenfolge). Der Kamera-Weißabgleich macht
aus reinem Rot „orange/gelb" und aus Grün „weiß" — für Farbaussagen am Panel ist deshalb
das Auge (oder der MCP-Screenshot) maßgeblich, nicht das Kamerabild.

```python
spi_bus = machine.SPI.Bus(host=1, sck=47, quad_pins=(21, 48, 40, 39))
bus = lcd_bus.SPIBusFast(spi_bus=spi_bus, dc=8, cs=45,
                         freq=40_000_000, spi_mode=3, quad=True)
fb1 = bus.allocate_framebuffer(320 * 480 * 2, lcd_bus.MEMORY_SPIRAM)
fb2 = bus.allocate_framebuffer(320 * 480 * 2, lcd_bus.MEMORY_SPIRAM)
display = axs15231b.AXS15231B(bus, 320, 480, frame_buffer1=fb1, frame_buffer2=fb2,
                              backlight_pin=1, color_space=lv.COLOR_FORMAT.RGB565,
                              rgb565_byte_swap=True)
```

Bauen: `tools/build_fork.sh` bzw. direkt im Mainline-Baum
(`python3 make.py esp32 BOARD=ESP32_GENERIC_S3 BOARD_VARIANT=SPIRAM_OCT --flash-size=16
DISPLAY=axs15231b INDEV=axs15231 --ota --partition-size=4194304`).
Panel + UI + Debug-Server laufen so im Kaltstart hoch (`main.py`).

## Was sonst noch am Board gemessen wurde

- **Touch**: I2C-Adresse `0x3B`, Pins SDA=4, SCL=8 — mit dem `i2c`-Modul (`I2C.Bus`,
  `I2C.Device`) angebunden. Mit `machine.I2C` scheitert der Treiber mit
  `OSError: I2C operation not supported`.
- **Reihenfolge**: Der Touch-Treiber muss **nach** dem Display erzeugt werden, sonst
  `RuntimeError: the display driver must be initilized before the pointer driver`.
- **Treiberfehler upstream**: `api_drivers/.../indev/axs15231.py` benutzt blankes
  `lv.DISPLAY_ROTATION._0`, ohne `lvgl` zu importieren → `NameError`. Deshalb liegt in
  `firmware/device/drivers/axs15231.py` eine Kopie mit ergänztem Import (Dateisystem
  überdeckt das eingefrorene Modul).
- **SPI-Bus bleibt belegt**: Ein Skript, das `machine.SPI.Bus(host=1, …)` anlegt, lässt
  den Bus C-seitig initialisiert zurück. Der nächste `machine.SPI.Bus(host=1, …)` im
  selben Boot scheitert und reißt den Interpreter mit (hässlicher `TypeError:
  can't convert module to int`). Vor jedem Geraeteskript daher **Reset**.
- **native USB**: Nach einem Reset verschwindet `/dev/…ttyACM*` kurz; vor Zugriffen aktiv
  warten (nicht blind `sleep`).
- **by-id ändert sich mit der Firmware**: Factory/Annex melden
  `USB JTAG/serial debug unit`, MicroPython `Espressif Device`. Deshalb wird der Port
  über den USB-Pfad (`…-usb-0:4.4.3:1.0`) bestimmt, mit by-id als Rückfall.
