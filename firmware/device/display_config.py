# Panel- und Touch-Konfiguration des JC3248W535 -- an EINER Stelle.
#
# Wichtig (alles am Board gemessen, siehe docs/09-display-bringup.md):
#   * Das QSPI-Panel braucht LVGL-Full-Refresh mit vollem Framebuffer (307200 Byte).
#     Dafuer gibt es `lcd_bus.SPIBusFast` im Fork-Branch feature/spi_bus_fast.
#   * KEIN DC-Pin verwenden: In QSPI steckt das Kommando im Opcode (0x02/0x32),
#     ein DC-Pin wird nicht gebraucht. Die Referenzkonfiguration uebergibt hier
#     dc=8 -- und GPIO 8 ist gleichzeitig der I2C-Takt (SCL) des Touch-Controllers!
#     Folge: sobald der Display-Treiber laeuft, bricht der Touch-Bus weg
#     (gemessen: ETIMEDOUT). Deshalb dc=-1 (= "kein DC-Pin" in ESP-IDF).
#   * Der Touch-Controller haengt ohne Beschaltung im Reset: RST (GPIO 12) ist
#     von Haus aus LOW. Er beantwortet dann zwar seine I2C-Adresse 0x3B, liefert
#     aber nur Konstanten (0x85/0x4A) statt Beruehrungsdaten. RST muss gepulst
#     und danach HIGH gehalten werden.

import time

import lcd_bus
import machine
import lvgl as lv
import axs15231b

WIDTH = 320
HEIGHT = 480

# Referenzen auf die zuletzt erzeugten Objekte. Wichtig: ohne gehaltene Referenz
# kann der Garbage Collector Display-, Touch- und Pin-Objekte wegraeumen -- LVGL
# verliert dann seine Puffer bzw. den Input-Treiber, und ein freigegebener RST-Pin
# faellt zurueck auf LOW (Touch-Controller wieder im Reset). Ausserdem sind sie so
# zur Laufzeit ueber den Debug-Server abfragbar (display_config.LAST_TOUCH).
LAST_DISPLAY = None
LAST_BUS = None
LAST_TOUCH = None
LAST_TOUCH_PINS = None

QSPI_SCK = 47
QSPI_PINS = (21, 48, 40, 39)
QSPI_CS = 45
QSPI_DC = -1          # -1 = kein DC-Pin (QSPI: Kommando steckt im Opcode).
                      # ACHTUNG: GPIO 8 ist der Touch-Takt und darf hier nicht stehen!
BACKLIGHT = 1
FREQ = 40_000_000

TOUCH_SDA = 4
TOUCH_SCL = 8
TOUCH_I2C_HOST = 0    # Hersteller-BSP nutzt I2C_NUM_0 (nicht 1) bei 400 kHz
FREQ_TOUCH = 400_000
# KEIN RST/INT: Im Hersteller-BSP (esp_bsp.h) stehen
#   EXAMPLE_PIN_NUM_QSPI_TOUCH_RST (-1)  und  ..._TOUCH_INT (-1)
# Der Controller wird also ausschliesslich pollend gelesen. GPIO 12 ist auf
# diesem Board die SD-Karten-Taktleitung, GPIO 11 ist nicht der Touch-INT --
# ein Reset-Impuls darauf ist wirkungslos (gemessen: kein Unterschied).


def bus_fast_available():
    return getattr(lcd_bus, "SPIBusFast", None) is not None


def create_display(full_frames=True, brightness=70):
    """Bus + Display erzeugen und initialisieren. Rueckgabe: (display, bus)."""
    spi_bus = machine.SPI.Bus(host=1, sck=QSPI_SCK, quad_pins=QSPI_PINS)

    fast = getattr(lcd_bus, "SPIBusFast", None)
    if fast is not None:
        bus = fast(spi_bus=spi_bus, dc=QSPI_DC, cs=QSPI_CS,
                   freq=FREQ, spi_mode=3, quad=True)
        print("display_config: SPIBusFast (DMA, gestueckelte Transfers)")
    else:
        bus = lcd_bus.SPIBus(spi_bus=spi_bus, dc=QSPI_DC, cs=QSPI_CS,
                             freq=FREQ, spi_mode=3, quad=True)
        print("display_config: WARNUNG -- nur SPIBus vorhanden (Mainline-Bau). "
              "Ein voller Frame (307200 Byte) kann damit nicht gesendet werden; "
              "das Panel wird vermutlich schwarz bleiben (Buslimit 32768 Byte).")

    kwargs = {}
    if full_frames:
        size = WIDTH * HEIGHT * 2
        kwargs["frame_buffer1"] = bus.allocate_framebuffer(size, lcd_bus.MEMORY_SPIRAM)
        kwargs["frame_buffer2"] = bus.allocate_framebuffer(size, lcd_bus.MEMORY_SPIRAM)
        print("display_config: 2 volle Framebuffer (%d Byte je)" % size)

    extra = {}
    try:
        extra["backlight_on_state"] = axs15231b.STATE_PWM
    except AttributeError:
        pass

    display = axs15231b.AXS15231B(
        bus, WIDTH, HEIGHT,
        backlight_pin=BACKLIGHT,
        color_space=lv.COLOR_FORMAT.RGB565,
        rgb565_byte_swap=True,
        **kwargs, **extra)

    display.set_power(True)
    display.set_backlight(brightness)
    display.init()
    print("display_config: init ok (fb1=%d Byte)" % len(display._frame_buffer1))
    global LAST_DISPLAY, LAST_BUS
    LAST_DISPLAY = display
    LAST_BUS = bus
    return display, bus


def prepare_touch_pins():
    """Kein Hardware-Reset noetig: Im Hersteller-BSP sind RST und INT auf -1.

    Der Controller auf diesem Board wird rein pollend gelesen. Die Funktion
    bleibt als Platzhalter erhalten (falls eine andere Board-Revision doch
    Leitungen hat), tut aber bewusst nichts.
    """
    return None


def create_touch():
    """Touch-Treiber -- MUSS nach dem Display erzeugt werden.

    Kein `enable_input_priority()`: das schaltet den LVGL-Indev auf
    INDEV_MODE_EVENT und LVGL pausiert dann seinen eigenen Abfrage-Timer
    (lv_indev.c: `lv_indev_set_mode` pausiert bei EVENT). Ohne den 33-ms-Timer
    des Treibers wird der Touch dann nie gelesen. Im Standardmodus fragt LVGL
    den Treiber selbst alle 33 ms ab -- das ist der robustere Weg.
    """
    import i2c
    import axs15231
    prepare_touch_pins()
    bus = i2c.I2C.Bus(host=TOUCH_I2C_HOST, sda=TOUCH_SDA, scl=TOUCH_SCL,
                      freq=FREQ_TOUCH)
    device = i2c.I2C.Device(bus, axs15231.I2C_ADDR, axs15231.BITS)
    indev = axs15231.AXS15231(device)
    global LAST_TOUCH
    LAST_TOUCH = indev
    return indev
