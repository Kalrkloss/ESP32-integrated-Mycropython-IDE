// ESP32 debug: UI logic of the web interface.
// Classic script (no modules): the functions are global because the buttons in
// index.html call them inline via onclick="...".

var history = [];
var historyPos = 0;
var currentPath = "/";

function el(id) {
  return document.getElementById(id);
}

// ---------------------------------------------------------------- Editor

var editor = null;

function editorEinrichten() {
  if (typeof CodeMirror === "undefined") {
    // Ersatzweg: fehlen die editor files on the device, bleibt das einfache Textfeld
    editorTasten();
    setStatus("CodeMirror not loaded -- plain text area");
    return;
  }
  editor = CodeMirror.fromTextArea(el("code"), {
    mode: "python",
    lineNumbers: true,
    indentUnit: 4,
    tabSize: 4,
    indentWithTabs: false,
    smartIndent: true,
    lineWrapping: false,
    matchBrackets: true,
    autoCloseBrackets: true,
    styleActiveLine: true,
    extraKeys: {
      "Ctrl-S": saveFile,
      "Cmd-S": saveFile,
      "Tab": function (cm) { cm.replaceSelection("    ", "end"); },
      "Shift-Tab": "indentLess",
      "Ctrl-/": "toggleComment"
    }
  });
  editor.setSize(null, 420);
  editor.on("cursorActivity", zeilenInfo);
  editor.on("change", zeilenInfo);
}

function editorText() {
  return editor ? editor.getValue() : el("code").value;
}

function editorSet(text) {
  if (editor) {
    editor.setValue(text);
  } else {
    el("code").value = text;
  }
}

function openSearch() {
  if (editor) {
    editor.execCommand("find");
  } else {
    alert("Search: Ctrl-F in the text area (no editor loaded)");
  }
}

function show(text) {
  var o = el("out");
  o.textContent += text;
  o.scrollTop = o.scrollHeight;
}

function api(url, optionen, art) {
  art = art || "json";
  return fetch(url, optionen).then(function (a) {
    if (art === "text") {
      return a.text();
    }
    return a.json();
  });
}

// ---------------------------------------------------------------- Reiter

function reiterEinrichten() {
  var knoepfe = document.querySelectorAll("nav button");
  for (var i = 0; i < knoepfe.length; i++) {
    knoepfe[i].addEventListener("click", function () {
      var namen = ["repl", "editor", "files", "config"];
      for (var j = 0; j < namen.length; j++) {
        el(namen[j]).classList.remove("active");
      }
      for (var k = 0; k < knoepfe.length; k++) {
        knoepfe[k].classList.remove("active");
      }
      this.classList.add("active");
      el(this.getAttribute("data-tab")).classList.add("active");
      if (this.getAttribute("data-tab") === "editor" && editor) {
        // CodeMirror is created inside the hidden tab and has to redraw when it
        // becomes visible (otherwise line numbers and highlighting are missing).
        editor.refresh();
      }
    });
  }
}

// ---------------------------------------------------------------- Console

function sendCommand() {
  var feld = el("cmd");
  var code = feld.value;
  if (!code.trim()) {
    return;
  }
  history.push(code);
  historyPos = history.length;
  show(">>> " + code + "\n");
  feld.value = "";
  el("repl-status").textContent = "laeuft ...";
  api("/api/exec", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code: code })
  }).then(function (a) {
    show(a.output + "\n");
    el("repl-status").textContent = "";
    zustand();
  }).catch(function (f) {
    show("Error: " + f + "\n");
    el("repl-status").textContent = "";
  });
}

function fetchLog() {
  api("/api/log", {}, "text").then(function (t) {
    show(t + "\n");
  });
}

function clearLog() {
  el("out").textContent = "";
}

function shot(live) {
  // Full frame and let the browser scale: measured on this board, a full
  // 320x480 frame takes 0.45 s while scale=4 takes 1.2 s (the device-side
  // downscale is a pure Python pixel loop and dominates).
  var scale = live ? 1 : (parseInt(el("shot-scale").value, 10) || 1);
  el("prev-status").textContent = "loading ...";
  fetch("/screen.raw?scale=" + scale, { cache: "no-store" }).then(function (r) {
    if (!r.ok) {
      throw new Error("HTTP " + r.status);
    }
    var size = (r.headers.get("X-Screen") || "").split("x");
    return r.arrayBuffer().then(function (buffer) {
      return { buffer: buffer, width: parseInt(size[0], 10), height: parseInt(size[1], 10) };
    });
  }).then(function (a) {
    if (!a.width || !a.height) {
      throw new Error("missing size header");
    }
    var canvas = el("prev");
    canvas.width = a.width;
    canvas.height = a.height;
    var context = canvas.getContext("2d");
    var image = context.createImageData(a.width, a.height);
    var raw = new Uint8Array(a.buffer);
    var target = image.data;
    for (var i = 0, p = 0; i + 1 < raw.length; i += 2, p += 4) {
      var v = raw[i] | (raw[i + 1] << 8);          // RGB565, low byte first
      target[p] = ((v >> 11) & 0x1F) << 3;
      target[p + 1] = ((v >> 5) & 0x3F) << 2;
      target[p + 2] = (v & 0x1F) << 3;
      target[p + 3] = 255;
    }
    context.putImageData(image, 0, 0);
    el("prev-status").textContent = a.width + " x " + a.height + " (1/" + scale + ")";
  }).catch(function (f) {
    el("prev-status").textContent = "error: " + f;
  });
}

var liveTimer = null;

function liveToggle(box) {
  if (liveTimer) {
    clearInterval(liveTimer);
    liveTimer = null;
    el("prev-status").textContent = "live view stopped";
    return;
  }
  liveTimer = setInterval(function () { shot(true); }, 1500);
  shot(true);
}

function restartBoard() {
  if (!confirm("Really restart the board?")) {
    return;
  }
  api("/api/reset", { method: "POST" }).then(function () {
    show("Restart triggered.\n");
  });
}

// ---------------------------------------------------------------- Editor

function setStatus(text) {
  el("e-status").textContent = text;
}

function openFile() {
  var p = el("e-path").value;
  setStatus("opening ...");
  api("/api/file?path=" + encodeURIComponent(p)).then(function (a) {
    if (a.error) {
      setStatus(a.error);
      return;
    }
    if (a.binary) {
      setStatus("binary file (" + a.size + " Byte) -- download only");
      return;
    }
    editorSet(a.data);
    setStatus("opened: " + a.data.length + " characters");
    zeilenInfo();
  }).catch(function (f) {
    setStatus("Error: " + f);
  });
}

function saveFile() {
  var p = el("e-path").value;
  setStatus("saving ...");
  api("/api/file?path=" + encodeURIComponent(p), {
    method: "POST",
    headers: { "Content-Type": "text/plain" },
    body: editorText()
  }).then(function (a) {
    setStatus(a.error ? a.error : ("saved: " + a.bytes + " Byte"));
    loadFiles();
  }).catch(function (f) {
    setStatus("Error: " + f);
  });
}

function runFile() {
  var code = editorText();
  api("/api/exec", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code: code })
  }).then(function (a) {
    setStatus("ausgefuehrt");
    show("--- " + el("e-path").value + " ---\n" + a.output + "\n");
    zustand();
  }).catch(function (f) {
    setStatus("Error: " + f);
  });
}

function deleteFile() {
  var p = el("e-path").value;
  if (!confirm("Delete: " + p + " ?")) {
    return;
  }
  api("/api/file", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: p })
  }).then(function (a) {
    setStatus(a.error ? a.error : "deleted");
    loadFiles();
  });
}

function zeilenInfo() {
  if (editor) {
    var k = editor.getCursor();
    el("e-cursor").textContent = "Line " + (k.line + 1) + ", column " + (k.ch + 1);
    el("e-info").textContent = editor.lineCount() + " lines, "
      + editor.getValue().length + " characters";
    return;
  }
  var t = el("code");
  var bis = t.value.slice(0, t.selectionStart);
  var zeilen = bis.split("\n");
  el("e-cursor").textContent = "Line " + zeilen.length + ", column " + (zeilen[zeilen.length - 1].length + 1);
  el("e-info").textContent = t.value.length + " characters, " + t.value.split("\n").length + " lines";
}

function editorTasten() {
  var t = el("code");
  t.addEventListener("keyup", zeilenInfo);
  t.addEventListener("click", zeilenInfo);
  t.addEventListener("keydown", function (e) {
    if (e.key === "Tab") {
      e.preventDefault();
      var a = t.selectionStart;
      var b = t.selectionEnd;
      t.value = t.value.slice(0, a) + "    " + t.value.slice(b);
      t.selectionStart = a + 4;
      t.selectionEnd = a + 4;
    }
    if ((e.ctrlKey || e.metaKey) && (e.key === "s" || e.key === "S")) {
      e.preventDefault();
      saveFile();
    }
  });
}

// ---------------------------------------------------------------- Files

function loadFiles() {
  api("/api/files?path=" + encodeURIComponent(currentPath)).then(function (a) {
    if (a.error) {
      el("f-rows").innerHTML = '<tr><td colspan="3">' + a.error + "</td></tr>";
      return;
    }
    el("f-path").textContent = a.path;
    if (a.memory && a.memory.free !== undefined) {
      el("f-free").textContent = "free: " + Math.round(a.memory.free / 1024) + " KB of "
        + Math.round(a.memory.total / 1024) + " KB";
    }
    var zeilen = "";
    for (var i = 0; i < a.entries.length; i++) {
      var e = a.entries[i];
      var target = (a.path === "/" ? "" : a.path) + "/" + e.name;
      var p = encodeURIComponent(target);
      var actions = "";
      if (e.dir) {
        actions += '<button class="btn" onclick="openFolder(\'' + target + '\')">Open</button>';
      } else {
        actions += '<button class="btn" onclick="editFile(\'' + target + '\')">Edit</button>'
            + '<a class="btn" href="/api/file?download=1&path=' + p + '">Download</a>';
      }
      actions += '<button class="btn" onclick="renameEntry(\'' + target + '\')">Rename</button>'
           + '<button class="btn" onclick="weg(\'' + target + '\')">Delete</button>';
      zeilen += "<tr><td>" + (e.dir ? "&#128193; " : "") + e.name + "</td>"
              + '<td class="n">' + (e.dir ? "" : e.size) + "</td>"
              + '<td class="act">' + actions + "</td></tr>";
    }
    el("f-rows").innerHTML = zeilen || '<tr><td colspan="3">(leer)</td></tr>';
  }).catch(function (f) {
    el("f-rows").innerHTML = '<tr><td colspan="3">' + f + "</td></tr>";
  });
}

function openFolder(p) {
  currentPath = p;
  loadFiles();
}

function goUp() {
  var t = currentPath.split("/").filter(function (x) { return x; });
  t.pop();
  currentPath = "/" + t.join("/");
  loadFiles();
}

function editFile(p) {
  el("e-path").value = p;
  openFile();
  document.querySelector('nav button[data-tab="editor"]').click();
}

function weg(p) {
  if (!confirm("Delete: " + p + " ?")) {
    return;
  }
  api("/api/file", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: p })
  }).then(function (a) {
    if (a.error) {
      alert(a.error);
    }
    loadFiles();
  });
}

function renameEntry(p) {
  var neu = prompt("Neuer Name:", p);
  if (!neu || neu === p) {
    return;
  }
  api("/api/rename", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ old: p, new: neu })
  }).then(function (a) {
    if (a.error) {
      alert(a.error);
    }
    loadFiles();
  });
}

function uploadFile() {
  var f = el("upload").files[0];
  if (!f) {
    alert("no file selected");
    return;
  }
  var target = (currentPath === "/" ? "" : currentPath) + "/" + f.name;
  var reader = new FileReader();
  reader.onload = function () {
    api("/api/file?path=" + encodeURIComponent(target), {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: reader.result
    }).then(function (a) {
      if (a.error) {
        alert(a.error);
      }
      loadFiles();
    });
  };
  reader.readAsArrayBuffer(f);
}

function newFile() {
  var n = prompt("Name of the new file:", "neu.py");
  if (!n) {
    return;
  }
  var target = (currentPath === "/" ? "" : currentPath) + "/" + n;
  api("/api/file?path=" + encodeURIComponent(target), {
    method: "POST",
    headers: { "Content-Type": "text/plain" },
    body: "# " + n + "\n"
  }).then(function () {
    editFile(target);
  });
}

function newFolder() {
  var n = prompt("Name of the new folder:", "daten");
  if (!n) {
    return;
  }
  api("/api/mkdir", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: (currentPath === "/" ? "" : currentPath) + "/" + n })
  }).then(function (a) {
    if (a.error) {
      alert(a.error);
    }
    loadFiles();
  });
}

// ---------------------------------------------------------------- Configuration

function loadConfig() {
  api("/api/config").then(function (a) {
    var c = a.config || {};
    var display = c.display || {};
    el("c-ssid").value = c.ssid || "";
    el("c-pass").value = "";
    el("c-pass").placeholder = c.password_gesetzt ? "leave unchanged" : "no password stored";
    el("c-host").value = c.hostname || "";
    el("c-bri").value = display.brightness !== undefined ? display.brightness : 70;
    el("c-bri-val").textContent = el("c-bri").value + " %";
    ladeAuswahl(c);
  });
}

// Board profiles and applications for the two selection lists. Profiles come with
// their pins; a board's values are applied by the setup page.
function ladeAuswahl(c) {
  var board = el("c-board");
  if (!board.options.length) {
    api("/api/profiles").then(function (a) {
      board.innerHTML = (a.profiles || []).map(function (p) {
        return '<option value="' + p.short + '">' + p.name + "</option>";
      }).join("");
      board.value = c.board || "";
    });
  } else {
    board.value = c.board || "";
  }
  var app = el("c-app");
  if (!app.options.length) {
    api("/api/apps").then(function (a) {
      var list = (a.apps || []).map(function (entry) {
        return '<option value="' + entry.name + '">' + (entry.title || entry.name) + "</option>";
      });
      app.innerHTML = list.join("") || '<option value="launcher">launcher</option>';
      app.value = c.app || a.running || "launcher";
    }).catch(function () {
      app.innerHTML = '<option value="launcher">launcher</option>';
    });
  } else {
    app.value = c.app || "launcher";
  }
}

// Switch the running application without a restart: the request is serviced in the
// LVGL thread by the main loop.
function appJetzt() {
  var name = el("c-app").value;
  api("/api/app", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: name })
  }).then(function (a) {
    el("c-status").textContent = a.error ? a.error : ("switched to " + a.requested);
  });
}

function saveConfig() {
  api("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ssid: el("c-ssid").value,
      password: el("c-pass").value,
      hostname: el("c-host").value,
      board: el("c-board").value,
      app: el("c-app").value,
      configured: true,
      display: { brightness: parseInt(el("c-bri").value, 10) }
    })
  }).then(function (a) {
    el("c-status").textContent = a.error ? a.error : "saved (restart needed for WiFi/hostname)";
    loadConfig();
  });
}

function applyBrightness() {
  var w = parseInt(el("c-bri").value, 10);
  var code = "import display_config\n"
           + "d = display_config.LAST_DISPLAY\n"
           + "d.set_backlight(" + w + ")\n"
           + "print('brightness set')";
  api("/api/exec", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code: code })
  }).then(function (a) {
    el("c-status").textContent = "applied";
    show(a.output + "\n");
  });
}

// ---------------------------------------------------------------- Zustand

function zustand() {
  api("/api/state").then(function (a) {
    el("p-ip").textContent = "IP " + (a.ip || "?");
    el("p-heap").textContent = "Heap " + (a.heap ? Math.round(a.heap / 1024) + " KB" : "?");
    el("p-up").textContent = "Laufzeit " + (a.uptime_s ? Math.round(a.uptime_s) + " s" : "?");
    if (a.memory && a.memory.free !== undefined) {
      el("p-fs").textContent = "free " + Math.round(a.memory.free / 1024) + " KB";
    } else {
      el("p-fs").textContent = "";
    }
    el("c-info").textContent = JSON.stringify(a, null, 1);
    el("p-ip").className = "pill " + (a.ip ? "ok" : "bad");
  }).catch(function () {
    el("p-ip").className = "pill bad";
  });
}

// ---------------------------------------------------------------- Start

function start() {
  reiterEinrichten();
  editorEinrichten();
  el("cmd").addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      sendCommand();
    }
    if (e.key === "ArrowUp" && history.length) {
      historyPos = Math.max(0, historyPos - 1);
      this.value = history[historyPos] || "";
    }
    if (e.key === "ArrowDown") {
      historyPos = Math.min(history.length, historyPos + 1);
      this.value = history[historyPos] || "";
    }
  });
  el("c-bri").addEventListener("input", function () {
    el("c-bri-val").textContent = this.value + " %";
  });
  loadConfig();
  loadFiles();
  zustand();
  setInterval(zustand, 5000);
}

window.addEventListener("load", start);
