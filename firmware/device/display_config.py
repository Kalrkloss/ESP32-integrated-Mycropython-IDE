# Display and touch configuration -- data driven from config.json + profiles.json.
#
# Structure:
#   * profiles.json holds ready-made board profiles (pins, drivers, resolution).
#     Only profiles matching the ESP32 type of this firmware (field "chip") are
#     offered, because the firmware is built for exactly one chip.
#   * config.json holds the effective configuration: the chosen profile is the
#     base, anything the user enters in the web UI wins.
#   * The drivers themselves are Python files living on the device under
#     /drv/display/<name>/ and /drv/indev/<name>.py. They are imported at
#     runtime, which is what makes a driver selectable from the web UI without
#     rebuilding the firmware.
#
# Everything hardware related (lcd_bus, lvgl, machine, i2c) is imported inside
# the functions so this module stays usable on a host (tests).

import json
import os
import sys
import time

CONFIG_FILE = "config.json"
PROFILES_FILE = "profiles.json"
DRIVER_ROOT = "/drv"            # host tests point this at a directory in the repo
ROOT = ""                       # prefix for relative file paths (host tests set a tmp dir)
UNUSED = -1                     # "not connected"

# Effective values and handles of the last created objects. main.py and the debug
# server read them; the references must be kept, otherwise the garbage collector
# collects driver and pin objects (LVGL would lose its buffers and the input
# driver, a released RST pin would fall back and reset the touch controller).
LAST_DISPLAY = None
LAST_BUS = None
LAST_TOUCH = None
LAST_TOUCH_PINS = None
WIDTH = 320
HEIGHT = 480

DEFAULT_DISPLAY = {
    "driver": "axs15231b",
    "bus": "qspi",
    "width": 320,
    "height": 480,
    "host": 1,
    "sck": 47,
    "data": [21, 48, 40, 39],
    "mosi": -1,
    "miso": -1,
    "cs": 45,
    "dc": -1,
    "reset": -1,
    "freq": 40000000,
    "spi_mode": 3,
    "quad": True,
    "backlight": 1,
    "backlight_on_state": "pwm",
    "color_space": "RGB565",
    "byte_swap": True,
    "full_frames": True,
    "brightness": 70,
    "init_arg": None,
}

DEFAULT_TOUCH = {
    "driver": "axs15231",
    "host": 0,
    "sda": 4,
    "scl": 8,
    "freq": 400000,
    "addr": 59,
    "bits": 8,
    "rst": -1,
    "int": -1,
}


# ------------------------------------------------------------------ helpers

def chip_name():
    """ESP32 type of the running firmware, e.g. "esp32s3"."""
    try:
        machine_name = os.uname().machine.lower()
    except Exception:  # noqa: BLE001
        return "unknown"
    for name in ("esp32s3", "esp32s2", "esp32c3", "esp32c6", "esp32c2", "esp32p4"):
        if name in machine_name.replace("-", ""):
            return name
    if "esp32" in machine_name:
        return "esp32"
    return machine_name


def _as_int(value, fallback):
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _pin_list(value, fallback):
    if isinstance(value, (list, tuple)):
        return [_as_int(p, UNUSED) for p in value]
    if isinstance(value, str):
        parts = [p for p in value.replace(";", ",").split(",") if p.strip()]
        if parts:
            return [_as_int(p.strip(), UNUSED) for p in parts]
    return list(fallback)


def _read_json(path, fallback):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return fallback


def _json_path(name):
    return (ROOT + "/" + name) if ROOT else name


def load_profiles(all_chips=False):
    """Board profiles. Without `all_chips` only those matching this firmware's chip.

    profiles.json ships with the firmware next to the script, so ROOT (the
    writable area) does not apply to it.
    """
    content = _read_json(PROFILES_FILE, {})
    profiles = content.get("profile", []) if isinstance(content, dict) else []
    if all_chips:
        return profiles
    mine = chip_name()
    return [p for p in profiles if str(p.get("chip", "")).lower() == mine]


def find_profile(short_name):
    for profile in load_profiles(all_chips=True):
        if profile.get("short") == short_name or profile.get("name") == short_name:
            return profile
    return None


def load_config():
    """Effective configuration: chosen profile as base, config.json wins."""
    raw = _read_json(_json_path(CONFIG_FILE), {})
    if not isinstance(raw, dict):
        raw = {}
    profile = find_profile(raw.get("board")) or {}
    display = dict(DEFAULT_DISPLAY)
    display.update(profile.get("display", {}))
    display.update(raw.get("display", {}) or {})
    display["data"] = _pin_list(display.get("data"), DEFAULT_DISPLAY["data"])
    display["width"] = _as_int(display.get("width"), DEFAULT_DISPLAY["width"])
    display["height"] = _as_int(display.get("height"), DEFAULT_DISPLAY["height"])
    for key in ("host", "sck", "mosi", "miso", "cs", "dc", "reset", "backlight"):
        display[key] = _as_int(display.get(key), DEFAULT_DISPLAY.get(key, UNUSED))
    display["freq"] = _as_int(display.get("freq"), DEFAULT_DISPLAY["freq"])
    display["spi_mode"] = _as_int(display.get("spi_mode"), DEFAULT_DISPLAY["spi_mode"])
    display["quad"] = bool(display.get("quad"))
    display["byte_swap"] = bool(display.get("byte_swap"))
    display["full_frames"] = bool(display.get("full_frames"))
    display["brightness"] = max(0, min(100, _as_int(display.get("brightness"),
                                                    DEFAULT_DISPLAY["brightness"])))

    touch = dict(DEFAULT_TOUCH)
    touch.update(profile.get("touch", {}))
    touch.update(raw.get("touch", {}) or {})
    for key in ("host", "sda", "scl", "freq", "addr", "bits", "rst", "int"):
        touch[key] = _as_int(touch.get(key), DEFAULT_TOUCH[key])

    return {
        "configured": bool(raw.get("configured")),
        "ssid": raw.get("ssid", ""),
        "password": raw.get("password", ""),
        "hostname": raw.get("hostname", "esp32-debug"),
        "ap_ssid": raw.get("ap_ssid", "ESP32-Setup"),
        "ap_password": raw.get("ap_password", ""),
        "app": raw.get("app", "launcher"),
        "board": raw.get("board") or profile.get("short", ""),
        "display": display,
        "touch": touch,
    }


def save_config(data):
    """Store only what was given. An empty password field deletes nothing.

    config.json is treated as a delta on top of the board profile: fields the
    caller does not mention keep coming from the profile, so switching profiles
    later really changes the pins. Without that, the first save would pin the whole
    display section and a later profile change would silently do nothing.
    """
    raw = _read_json(_json_path(CONFIG_FILE), {})
    if not isinstance(raw, dict):
        raw = {}
    effective = load_config()
    for key in ("configured", "ssid", "hostname", "ap_ssid", "ap_password", "board", "app"):
        if key in data:
            raw[key] = data[key]
    if "brightness" in data:            # legacy top-level field of the old web UI
        raw["display"] = dict(raw.get("display") or {})
        raw["display"]["brightness"] = data["brightness"]
    if "password" in data and (data["password"] or not effective.get("password")):
        raw["password"] = data["password"]
    for section in ("display", "touch"):
        if isinstance(data.get(section), dict):
            stored = dict(raw.get(section) or {})
            stored.update(data[section])
            raw[section] = stored
    with open(_json_path(CONFIG_FILE), "w") as fh:
        json.dump(raw, fh)
    return load_config()


def available_drivers():
    """Drivers present on the device -- the basis for the selection lists.

    Deliberately without os.path: this MicroPython build has no os.path module,
    which is exactly the kind of difference the host tests cannot see on CPython.
    A directory is recognised by being listable.
    """
    result = {"display": [], "touch": []}
    try:
        for name in os.listdir(DRIVER_ROOT + "/display"):
            try:
                os.listdir(DRIVER_ROOT + "/display/" + name)
                result["display"].append(name)
            except OSError:
                pass
    except OSError:
        pass
    try:
        for name in os.listdir(DRIVER_ROOT + "/indev"):
            if name.endswith(".py"):
                result["touch"].append(name[:-3])
    except OSError:
        pass
    result["display"] = sorted(result["display"])
    result["touch"] = sorted(result["touch"])
    return result


def import_driver(kind, name):
    """Import a driver module. kind: "display" or "indev".

    The filesystem takes precedence over frozen modules, so on the device our
    patched copy wins over the one compiled into the image.
    """
    if not name or "/" in name or name.startswith("."):
        raise ValueError("invalid driver name: %r" % name)
    if kind == "display":
        path = DRIVER_ROOT + "/display/" + name
    else:
        path = DRIVER_ROOT + "/indev"
    if path not in sys.path:
        sys.path.insert(0, path)
    return __import__(name)


def driver_class(module):
    """Find the driver class inside a module (the class name is not always equal)."""
    name = module.__name__.rsplit(".", 1)[-1].lower()
    candidates = []
    for attribute in dir(module):
        value = getattr(module, attribute)
        if isinstance(value, type) and attribute[0].isupper():
            candidates.append((attribute, value))
    for attribute, value in candidates:
        if attribute.lower() == name:
            return value
    if candidates:
        return candidates[0][1]
    raise RuntimeError("no driver class found in %s" % module.__name__)


def _make_bus(display):
    import lcd_bus
    import machine

    quad = display.get("quad")
    if display.get("bus") == "qspi" or quad:
        spi_bus = machine.SPI.Bus(host=display["host"], sck=display["sck"],
                                  quad_pins=tuple(display["data"]))
    else:
        spi_bus = machine.SPI.Bus(host=display["host"], sck=display["sck"],
                                  mosi=display["mosi"], miso=display["miso"])

    fast = getattr(lcd_bus, "SPIBusFast", None)
    bus_class = fast if (fast is not None and quad) else lcd_bus.SPIBus
    bus = bus_class(spi_bus=spi_bus, dc=display["dc"], cs=display["cs"],
                    freq=display["freq"], spi_mode=display["spi_mode"], quad=bool(quad))
    if quad and fast is not None:
        print("display_config: SPIBusFast (DMA, chunked transfers)")
    elif quad:
        print("display_config: WARNING -- no SPIBusFast in the image, a full frame "
              "cannot be sent (bus limit 32768 bytes).")
    return bus


def create_display(full_frames=None, brightness=None):
    """Create and initialise bus + display from the configuration."""
    import lcd_bus
    import lvgl as lv

    cfg = load_config()
    display_cfg = cfg["display"]
    if full_frames is not None:
        display_cfg["full_frames"] = bool(full_frames)
    if brightness is not None:
        display_cfg["brightness"] = max(0, min(100, _as_int(brightness,
                                                           display_cfg["brightness"])))
    print("display_config: board %s, display %s (%dx%d, %s)"
          % (cfg.get("board") or "?", display_cfg["driver"], display_cfg["width"],
             display_cfg["height"], display_cfg["bus"]))

    bus = _make_bus(display_cfg)

    kwargs = {}
    if display_cfg["full_frames"]:
        size = display_cfg["width"] * display_cfg["height"] * 2
        kwargs["frame_buffer1"] = bus.allocate_framebuffer(size, lcd_bus.MEMORY_SPIRAM)
        kwargs["frame_buffer2"] = bus.allocate_framebuffer(size, lcd_bus.MEMORY_SPIRAM)
        print("display_config: two full frame buffers (%d bytes each)" % size)
    else:
        kwargs["frame_buffer1"] = None
        kwargs["frame_buffer2"] = None

    module = import_driver("display", display_cfg["driver"])
    driver = driver_class(module)

    for field, value in (("reset_pin", display_cfg["reset"]),
                         ("backlight_pin", display_cfg["backlight"])):
        if value is not None and value != UNUSED:
            kwargs[field] = value
    if display_cfg["backlight_on_state"]:
        state = getattr(module, "STATE_" + str(display_cfg["backlight_on_state"]).upper(), None)
        if state is not None:
            kwargs["backlight_on_state"] = state
    kwargs["color_space"] = getattr(lv.COLOR_FORMAT,
                                    str(display_cfg["color_space"]).upper(),
                                    lv.COLOR_FORMAT.RGB565)
    kwargs["rgb565_byte_swap"] = display_cfg["byte_swap"]

    display = driver(bus, display_cfg["width"], display_cfg["height"], **kwargs)

    display.set_power(True)
    display.set_backlight(display_cfg["brightness"])
    if display_cfg.get("init_arg") is not None:
        display.init(_as_int(display_cfg["init_arg"], 0))
    else:
        display.init()

    global LAST_DISPLAY, LAST_BUS, WIDTH, HEIGHT
    LAST_DISPLAY = display
    LAST_BUS = bus
    WIDTH = display_cfg["width"]
    HEIGHT = display_cfg["height"]
    print("display_config: init ok")
    return display, bus


def prepare_touch_pins(cfg=None):
    """Bring up the touch controller's RST/INT lines if the profile defines them.

    Many boards (including the JC3248W535) have neither line -- then nothing is
    touched. When pins are given the references must be kept: if the garbage
    collector frees the pin object, the line falls back.
    """
    global LAST_TOUCH_PINS
    cfg = cfg or load_config()
    touch = cfg["touch"]
    if touch["rst"] == UNUSED and touch["int"] == UNUSED:
        LAST_TOUCH_PINS = None
        return None
    import machine
    pins = []
    if touch["int"] != UNUSED:
        pins.append(machine.Pin(touch["int"], machine.Pin.IN, machine.Pin.PULL_UP))
    if touch["rst"] != UNUSED:
        rst = machine.Pin(touch["rst"], machine.Pin.OUT)
        rst.value(0)
        time.sleep_ms(100)
        rst.value(1)
        time.sleep_ms(100)
        pins.append(rst)
    LAST_TOUCH_PINS = pins
    return pins


def create_touch(cfg=None):
    """Create the touch driver from the configuration (after the display).

    No `enable_input_priority()`: it switches the LVGL indev to INDEV_MODE_EVENT,
    which makes LVGL pause its own polling timer -- without the driver's own
    33 ms timer the touch is then never read.
    """
    import i2c

    cfg = cfg or load_config()
    touch = cfg["touch"]
    prepare_touch_pins(cfg)
    bus = i2c.I2C.Bus(host=touch["host"], sda=touch["sda"], scl=touch["scl"],
                      freq=touch["freq"])
    device = i2c.I2C.Device(bus, touch["addr"], touch["bits"])
    module = import_driver("indev", touch["driver"])
    driver = driver_class(module)
    indev = driver(device)
    global LAST_TOUCH
    LAST_TOUCH = indev
    print("display_config: touch %s at address 0x%02X" % (touch["driver"], touch["addr"]))
    return indev


def bus_fast_available():
    try:
        import lcd_bus
        return getattr(lcd_bus, "SPIBusFast", None) is not None
    except ImportError:
        return False
