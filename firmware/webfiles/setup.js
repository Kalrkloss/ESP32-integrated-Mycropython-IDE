// Setup page: board selection, display/touch driver and pin configuration.
// Loads /api/profiles (board profiles plus the current configuration) and
// /api/drivers (drivers present on the device), renders the form from the field
// list below and writes everything back through POST /api/config.

var FIELDS = [
  ["display", "driver", "Driver", "driver_display"],
  ["display", "bus", "Bus", "option:spi,qspi"],
  ["display", "width", "Width (px)", "int"],
  ["display", "height", "Height (px)", "int"],
  ["display", "host", "SPI host", "int"],
  ["display", "sck", "Clock (SCK)", "int"],
  ["display", "data", "Data pins (QSPI D0-D3)", "pins"],
  ["display", "mosi", "MOSI", "int"],
  ["display", "miso", "MISO", "int"],
  ["display", "cs", "CS", "int"],
  ["display", "dc", "DC/RS", "int"],
  ["display", "reset", "Reset", "int"],
  ["display", "freq", "Frequency (Hz)", "int"],
  ["display", "spi_mode", "SPI mode", "int"],
  ["display", "quad", "Quad (QSPI)", "bool"],
  ["display", "backlight", "Backlight pin", "int"],
  ["display", "backlight_on_state", "Backlight on state", "option:,high,low,pwm"],
  ["display", "color_space", "Color space", "option:RGB565,RGB888,BGR565"],
  ["display", "byte_swap", "Byte swap", "bool"],
  ["display", "full_frames", "Full frame buffers", "bool"],
  ["display", "brightness", "Brightness (0-100)", "int"],
  ["display", "init_arg", "Init argument", "int"],
  ["touch", "driver", "Driver", "driver_touch"],
  ["touch", "host", "I2C host", "int"],
  ["touch", "sda", "SDA", "int"],
  ["touch", "scl", "SCL", "int"],
  ["touch", "freq", "Frequency (Hz)", "int"],
  ["touch", "addr", "Address (decimal)", "int"],
  ["touch", "bits", "Bits", "int"],
  ["touch", "rst", "Reset", "int"],
  ["touch", "int", "Interrupt", "int"],
];

var DATA = { profiles: [], drivers: { display: [], touch: [] }, config: {} };

function el(id) {
  return document.getElementById(id);
}

function label(entry) {
  return '<label for="' + entry[0] + "-" + entry[1] + '">' + entry[2] + "</label>";
}

function inputFor(entry, value) {
  var id = entry[0] + "-" + entry[1];
  var kind = entry[3];
  if (kind === "bool") {
    return '<input type="checkbox" id="' + id + '"' + (value ? " checked" : "") + ">";
  }
  if (kind === "driver_display" || kind === "driver_touch") {
    var names = kind === "driver_display" ? DATA.drivers.display : DATA.drivers.touch;
    var options = names.map(function (name) {
      return '<option value="' + name + '"' + (name === value ? " selected" : "") +
             ">" + name + "</option>";
    });
    if (names.indexOf(value) < 0 && value) {
      options.unshift('<option value="' + value + '" selected>' + value +
                      " (missing on the device)</option>");
    }
    return '<select id="' + id + '">' + options.join("") + "</select>";
  }
  if (kind.indexOf("option:") === 0) {
    var list = kind.slice(7).split(",");
    return '<select id="' + id + '">' + list.map(function (name) {
      return '<option value="' + name + '"' + (String(value) === name ? " selected" : "") +
             ">" + (name || "(default)") + "</option>";
    }).join("") + "</select>";
  }
  if (kind === "pins") {
    var text = (value || []).join(", ");
    return '<input type="text" id="' + id + '" value="' + text + '" placeholder="21, 48, 40, 39">';
  }
  return '<input type="' + (kind === "int" ? "number" : "text") + '" id="' + id +
         '" value="' + (value === null || value === undefined ? "" : value) + '">';
}

function render(section) {
  var values = DATA.config[section] || {};
  el("form-" + section).innerHTML = FIELDS.filter(function (entry) {
    return entry[0] === section;
  }).map(function (entry) {
    return '<div class="row">' + label(entry) + inputFor(entry, values[entry[1]]) + "</div>";
  }).join("");
}

function collect(section) {
  var result = {};
  FIELDS.filter(function (entry) {
    return entry[0] === section;
  }).forEach(function (entry) {
    var node = el(entry[0] + "-" + entry[1]);
    if (!node) {
      return;
    }
    var kind = entry[3];
    if (kind === "bool") {
      result[entry[1]] = node.checked;
    } else if (kind === "int") {
      var number = parseInt(node.value, 10);
      result[entry[1]] = isNaN(number) ? -1 : number;
    } else if (kind === "pins") {
      result[entry[1]] = node.value.split(/[;,]/).map(function (part) {
        return parseInt(part.trim(), 10);
      }).filter(function (number) {
        return !isNaN(number);
      });
    } else {
      result[entry[1]] = node.value;
    }
  });
  return result;
}

function applyProfile() {
  var short = el("board").value;
  var found = null;
  DATA.profiles.forEach(function (profile) {
    if (profile.short === short) {
      found = profile;
    }
  });
  if (!found) {
    return;
  }
  DATA.config.display = found.display;
  DATA.config.touch = found.touch;
  DATA.config.board = found.short;
  render("display");
  render("touch");
  el("board-info").textContent = found.name + " -- source: " + (found.source || "?") +
    (found.note ? " -- " + found.note : "");
}

function fill() {
  el("chip").textContent = "chip: " + (DATA.chip || "?");
  el("ssid").value = DATA.config.ssid || "";
  el("hostname").value = DATA.config.hostname || "";
  el("ap_ssid").value = DATA.config.ap_ssid || "";
  el("password").placeholder = DATA.config.password_gesetzt ? "stored" : "unchanged";
  var board = el("board");
  board.innerHTML = DATA.profiles.map(function (profile) {
    return '<option value="' + profile.short + '"' +
           (profile.short === DATA.config.board ? " selected" : "") + ">" +
           profile.name + "</option>";
  }).join("");
  render("display");
  render("touch");
  applyProfile();
  el("drivers").textContent = "Drivers on the device -- display: " +
    (DATA.drivers.display.join(", ") || "none") + " | touch: " +
    (DATA.drivers.touch.join(", ") || "none");
}

function save(restart) {
  var payload = {
    configured: true,
    ssid: el("ssid").value.trim(),
    hostname: el("hostname").value.trim(),
    ap_ssid: el("ap_ssid").value.trim(),
    ap_password: el("ap_password").value,
    board: el("board").value,
    display: collect("display"),
    touch: collect("touch"),
  };
  if (el("password").value) {
    payload.password = el("password").value;
  }
  if (!payload.ssid) {
    el("err").textContent = "WiFi name is required";
    return;
  }
  el("status").textContent = "saving ...";
  el("err").textContent = "";
  fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then(function (response) {
    return response.json().then(function (data) {
      if (!response.ok) {
        throw new Error(data.error || ("HTTP " + response.status));
      }
      return data;
    });
  }).then(function () {
    el("status").textContent = "saved";
    if (restart) {
      el("status").textContent = "saved -- restarting";
      setTimeout(function () { fetch("/api/reset", { method: "POST" }); }, 400);
      setTimeout(function () {
        el("status").textContent = "restarted -- connect to your network and open the board";
      }, 2500);
    }
  }).catch(function (error) {
    el("status").textContent = "";
    el("err").textContent = "error: " + error;
  });
}

fetch("/api/profiles", { cache: "no-store" })
  .then(function (response) { return response.json(); })
  .then(function (profiles) {
    DATA = profiles;
    return fetch("/api/drivers", { cache: "no-store" });
  })
  .then(function (response) { return response.json(); })
  .then(function (drivers) {
    DATA.drivers = drivers;
    fill();
  })
  .catch(function (error) {
    el("err").textContent = "cannot load configuration: " + error;
  });
