# main.py -- board startup: display, touch, application, debug server.
#
# Verified order on the JC3248W535:
#   1. SPI bus + display first. The full-frame path needs a bus driver that chunks
#      large transfers (SPIBusFast); without it a full 307200 byte frame exceeds
#      the SPI bus limit of 32768 bytes.
#   2. Touch AFTER the display (the pointer framework checks that a display is
#      initialised) and through the `i2c` module -- a raw machine.I2C does not work.
#   3. The server last; afterwards the loop runs, which also executes the server's
#      screen requests (LVGL is not thread safe).
#
# Errors in one step are reported but never fatal: the debug server should stay
# reachable as long as possible.
#
# If the board is not configured, boot.py has already opened the setup access
# point; then only the setup page is served (see portal.SETUP_MODE) and no
# application is started.

import sys
import time

import lvgl as lv

import display_config
import mcp_logbuf
import mcp_screen
import mcp_serve
import portal

WIDTH = display_config.WIDTH
HEIGHT = display_config.HEIGHT

# Kept references: without them the garbage collector may collect driver objects.
_DISPLAY = None
_TOUCH = None
_APP = None

# Hooks called once per main loop iteration (LVGL work must stay in this thread).
_LOOP_HOOKS = []


def report(step, exc):
    mcp_logbuf.log("main: %s failed -- %s: %s" % (step, type(exc).__name__, exc))


def start_display():
    global _DISPLAY
    _DISPLAY, _bus = display_config.create_display()
    return _DISPLAY


def start_touch():
    global _TOUCH
    _TOUCH = display_config.create_touch()
    mcp_logbuf.log("main: touch ok")
    return _TOUCH


def device_ip():
    try:
        import network
        sta = network.WLAN(network.STA_IF)
        if sta.isconnected():
            return sta.ifconfig()[0]
    except Exception:  # noqa: BLE001
        pass
    return "offline"


def build_demo_ui(ip):
    """Fallback screen when no application is available."""
    scr = lv.screen_active()
    scr.set_style_bg_color(lv.color_hex(0x101820), 0)

    title = lv.label(scr)
    title.set_text("ESP32-S3 DEBUG")
    title.set_style_text_color(lv.color_hex(0xFFFFFF), 0)
    title.align(lv.ALIGN.TOP_MID, 0, 16)

    info = lv.label(scr)
    info.set_text("IP: %s\nWeb: http://%s/" % (ip, ip))
    info.set_style_text_color(lv.color_hex(0x8FD4FF), 0)
    info.align(lv.ALIGN.TOP_LEFT, 12, 60)

    box = lv.obj(scr)
    box.set_size(100, 100)
    box.center()
    box.set_style_bg_color(lv.color_hex(0xE03030), 0)
    box.set_style_border_width(3, 0)
    box.set_style_border_color(lv.color_hex(0xFFFFFF), 0)

    counter = {"n": 0}
    note = lv.label(scr)
    note.set_text("Touch: 0")
    note.set_style_text_color(lv.color_hex(0x00E070), 0)
    note.align(lv.ALIGN.BOTTOM_LEFT, 12, -70)

    def on_click(_event):
        counter["n"] += 1
        note.set_text("Touch: %d" % counter["n"])
        mcp_logbuf.log("main: touch %d" % counter["n"])

    try:
        box.add_flag(lv.obj.FLAG.CLICKABLE)
    except Exception:  # noqa: BLE001
        pass
    box.add_event_cb(on_click, lv.EVENT.CLICKED, None)

    bar = lv.bar(scr)
    bar.set_size(280, 18)
    bar.align(lv.ALIGN.BOTTOM_MID, 0, -30)
    bar.set_value(60, 0)
    mcp_logbuf.log("main: demo UI ready")


def start_app():
    """Start the configured application, else the built-in demo screen.

    Applications live in firmware/apps and are started through app_loader, which
    also allows switching them at runtime from the web UI. If the loader is not on
    the device the demo screen is used instead.
    """
    global _APP
    name = display_config.load_config().get("app") or "launcher"
    try:
        import app_loader
    except ImportError:
        mcp_logbuf.log("main: app_loader not available -- using the demo screen")
        build_demo_ui(device_ip())
        return None
    try:
        _LOOP_HOOKS.append(app_loader.service_requests)
        _APP = app_loader.start_app(name)
    except Exception as exc:  # noqa: BLE001
        report("app %s" % name, exc)
        build_demo_ui(device_ip())
    return _APP


def build_setup_hint():
    """Screen shown in setup mode."""
    scr = lv.screen_active()
    scr.set_style_bg_color(lv.color_hex(0x101820), 0)

    title = lv.label(scr)
    title.set_text("SETUP MODE")
    title.set_style_text_color(lv.color_hex(0xFFFFFF), 0)
    title.align(lv.ALIGN.TOP_MID, 0, 20)

    info = lv.label(scr)
    info.set_text("1. Join WiFi %r\n2. Open http://%s/\n\nConfigure your network and\n"
                  "the display in the browser."
                  % (portal.AP_SSID_DEFAULT, portal.AP_IP))
    info.set_style_text_color(lv.color_hex(0x8FD4FF), 0)
    info.align(lv.ALIGN.TOP_LEFT, 12, 70)
    mcp_logbuf.log("main: setup hint shown")


def run_setup_mode():
    """Open access point with captive portal: only the setup page is served."""
    mcp_logbuf.log("main: setup mode -- captive portal at http://%s/" % portal.AP_IP)
    portal.start_dns_hijack()
    try:
        mcp_serve.start(port=80, setup_only=True)
    except Exception as exc:  # noqa: BLE001
        report("setup server", exc)
    # The display is tried only after the server is up: a wrong display
    # configuration can block in a C call, and the user must still be able to
    # reach the setup page to correct it.
    try:
        start_display()
        mcp_screen.attach_framebuffer()
        build_setup_hint()
    except Exception as exc:  # noqa: BLE001
        report("setup display", exc)
    while True:
        try:
            time.sleep(0.5)
        except KeyboardInterrupt:
            raise


def main():
    if portal.SETUP_MODE:
        run_setup_mode()
        return

    ip = device_ip()
    try:
        start_display()
        mcp_screen.attach_framebuffer()
    except Exception as exc:  # noqa: BLE001
        report("display", exc)
    try:
        start_touch()
    except Exception as exc:  # noqa: BLE001
        report("touch", exc)
    try:
        start_app()
    except Exception as exc:  # noqa: BLE001
        report("app", exc)
    try:
        mcp_serve.start(port=80)
        print("main: debug server on http://%s/" % ip)
    except Exception as exc:  # noqa: BLE001
        report("server", exc)
        try:
            sys.print_exception(exc)
        except Exception:  # noqa: BLE001
            pass

    # Main loop. Two things matter here:
    #
    # 1. LVGL needs a continuous tick. Without `lv.tick_inc()` `lv.tick_get()` stays
    #    at 0 and `lv.timer_handler()` executes NO timer at all -- no input polling,
    #    no refresh, no animation.
    # 2. Do NOT swallow KeyboardInterrupt -- in MicroPython it inherits from
    #    Exception, and without re-raising, the board is unreachable for Ctrl-C
    #    (and therefore for mpremote).
    _LOOP_HOOKS.insert(0, mcp_screen.service_requests)
    last_tick = time.ticks_ms()
    while True:
        try:
            now = time.ticks_ms()
            lv.tick_inc(time.ticks_diff(now, last_tick))
            last_tick = now
            lv.timer_handler()
            for hook in _LOOP_HOOKS:
                hook()
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # noqa: BLE001
            print("main: loop -- %s: %s" % (type(exc).__name__, exc))
        time.sleep_ms(5)


main()
