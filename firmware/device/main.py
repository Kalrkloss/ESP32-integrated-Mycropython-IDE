# main.py -- Bildschirm starten + Debug-MCP-Server hochziehen.
# Reihenfolge ist wichtig: erst Display (damit der Framebuffer existiert und beim
# Server angemeldet werden kann), dann Server, dann LVGL-Schleife.

import sys
import time

# Module des Debug-Servers liegen flach im Geraete-Root (siehe tools/deploy.sh)
import mcp_serve
import mcp_screen

WIDTH = 320
HEIGHT = 480


def start_display():
    """Display + Touch initialisieren, Framebuffer beim Debug-Server anmelden."""
    import machine
    import lcd_bus
    import lvgl as lv
    import axs15231b
    import axs15231

    # QSPI-Panel (Pins des JC3248W535)
    spi_bus = machine.SPI.Bus(
        host=1,
        sck=47,
        quad_pins=(21, 48, 40, 39),
    )
    display_bus = lcd_bus.SPIBus(
        spi_bus=spi_bus,
        dc=8,
        cs=45,
        freq=40_000_000,
        spi_mode=3,
        quad=True,
    )
    # EIN voller Framebuffer in PSRAM: wir halten die Referenz und koennen sie
    # fuer Screenshots auslesen (das Panel braucht ohnehin Full-Frame-Updates).
    fb = display_bus.allocate_framebuffer(WIDTH * HEIGHT * 2, lcd_bus.MEMORY_SPIRAM)
    display = axs15231b.AXS15231B(
        display_bus,
        WIDTH,
        HEIGHT,
        frame_buffer1=fb,
        backlight_pin=1,
        color_space=lv.COLOR_FORMAT.RGB565,
        rgb565_byte_swap=True,
        backlight_on_state=axs15231b.STATE_PWM,
    )
    display.set_power(True)
    display.set_backlight(80)
    display.init()

    # Touch ueber I2C (AXS15231B); Pins werden beim Bring-up verifiziert
    i2c = machine.I2C(0, sda=4, scl=8, freq=400_000)
    indev = axs15231.AXS15231(i2c)
    indev.enable_input_priority()

    mcp_screen.attach(fb, WIDTH, HEIGHT, byte_swap=True, label="axs15231b fb1")
    return display, indev


def build_ui(ip):
    import lvgl as lv

    scr = lv.screen_active()
    scr.set_style_bg_color(lv.color_hex(0x101820), 0)

    title = lv.label(scr)
    title.set_text("ESP32-S3 Debug")
    title.set_style_text_color(lv.color_hex(0xFFFFFF), 0)
    title.align(lv.ALIGN.TOP_MID, 0, 20)

    info = lv.label(scr)
    info.set_text("IP: %s\nMCP: http://%s/mcp" % (ip, ip))
    info.set_style_text_color(lv.color_hex(0x8FD4FF), 0)
    info.align(lv.ALIGN.TOP_LEFT, 12, 70)

    btn = lv.button(scr)
    btn.set_size(200, 60)
    btn.align(lv.ALIGN.BOTTOM_MID, 0, -40)
    label = lv.label(btn)
    label.set_text("Tippen zaehlt")
    label.center()

    counter = {"n": 0}
    note = lv.label(scr)
    note.set_text("Touch: 0")
    note.align(lv.ALIGN.BOTTOM_MID, 0, -120)

    def on_click(_event):
        counter["n"] += 1
        note.set_text("Touch: %d" % counter["n"])
        print("touch %d" % counter["n"])

    btn.add_event_cb(on_click, lv.EVENT.CLICKED, None)
    return scr


def main():
    ip = "offline"
    try:
        import network
        sta = network.WLAN(network.STA_IF)
        if sta.isconnected():
            ip = sta.ifconfig()[0]
    except Exception:
        pass

    try:
        start_display()
    except Exception as exc:  # noqa: BLE001 - Fehler sichtbar machen statt Absturz
        print("main: Display-Start fehlgeschlagen: %s: %s" % (type(exc).__name__, exc))

    try:
        build_ui(ip)
    except Exception as exc:  # noqa: BLE001
        print("main: UI-Aufbau fehlgeschlagen: %s: %s" % (type(exc).__name__, exc))

    try:
        mcp_serve.start(port=80)
        print("main: Debug-Server auf http://%s/" % ip)
    except Exception as exc:  # noqa: BLE001
        print("main: Server-Start fehlgeschlagen: %s: %s" % (type(exc).__name__, exc))

    # LVGL-Schleife: eigener Timer-Task, wenn verfuegbar, sonst manuell
    try:
        import task_handler
        task_handler.TaskHandler(33)
        while True:
            time.sleep(1)
    except ImportError:
        import lvgl as lv
        while True:
            lv.timer_handler()
            time.sleep_ms(5)


if __name__ == "__main__":
    main()
