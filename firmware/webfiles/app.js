// ESP32-Debug: Bedienlogik der Weboberflaeche.
// Klassisches Skript (keine Module): die Funktionen sind global, weil die
// Schaltflaechen in index.html sie per onclick="..." aufrufen.

var verlauf = [];
var vpos = 0;
var aktuellerPfad = "/";

function el(id) {
  return document.getElementById(id);
}

// ---------------------------------------------------------------- Editor

var editor = null;

function editorEinrichten() {
  if (typeof CodeMirror === "undefined") {
    // Ersatzweg: fehlen die Editor-Dateien auf dem Geraet, bleibt das einfache Textfeld
    editorTasten();
    setStatus("CodeMirror nicht geladen -- einfaches Textfeld");
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
      "Ctrl-S": speichern,
      "Cmd-S": speichern,
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

function suchen() {
  if (editor) {
    editor.execCommand("find");
  } else {
    alert("Suchen: Strg-F im Textfeld (kein Editor geladen)");
  }
}

function zeige(text) {
  var o = el("out");
  o.textContent += text;
  o.scrollTop = o.scrollHeight;
}

function api(pfad, optionen, art) {
  art = art || "json";
  return fetch(pfad, optionen).then(function (a) {
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
        // CodeMirror wird im versteckten Reiter erzeugt und muss beim Sichtbarwerden
        // neu zeichnen (sonst fehlen Zeilennummern und Hervorhebung).
        editor.refresh();
      }
    });
  }
}

// ---------------------------------------------------------------- Konsole

function senden() {
  var feld = el("cmd");
  var code = feld.value;
  if (!code.trim()) {
    return;
  }
  verlauf.push(code);
  vpos = verlauf.length;
  zeige(">>> " + code + "\n");
  feld.value = "";
  el("repl-status").textContent = "laeuft ...";
  api("/api/exec", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code: code })
  }).then(function (a) {
    zeige(a.output + "\n");
    el("repl-status").textContent = "";
    zustand();
  }).catch(function (f) {
    zeige("Fehler: " + f + "\n");
    el("repl-status").textContent = "";
  });
}

function logHolen() {
  api("/api/log", {}, "text").then(function (t) {
    zeige(t + "\n");
  });
}

function leeren() {
  el("out").textContent = "";
}

function shot() {
  var scale = parseInt(el("shot-scale").value, 10) || 4;
  el("prev-status").textContent = "lade ...";
  fetch("/screen.raw?scale=" + scale, { cache: "no-store" }).then(function (r) {
    if (!r.ok) {
      throw new Error("HTTP " + r.status);
    }
    var mass = (r.headers.get("X-Screen") || "").split("x");
    return r.arrayBuffer().then(function (puffer) {
      return { puffer: puffer, breite: parseInt(mass[0], 10), hoehe: parseInt(mass[1], 10) };
    });
  }).then(function (a) {
    if (!a.breite || !a.hoehe) {
      throw new Error("Massangabe fehlt");
    }
    var leinwand = el("prev");
    leinwand.width = a.breite;
    leinwand.height = a.hoehe;
    var kontext = leinwand.getContext("2d");
    var bild = kontext.createImageData(a.breite, a.hoehe);
    var roh = new Uint8Array(a.puffer);
    var ziel = bild.data;
    for (var i = 0, p = 0; i + 1 < roh.length; i += 2, p += 4) {
      var v = roh[i] | (roh[i + 1] << 8);          // RGB565, niederwertiges Byte zuerst
      ziel[p] = ((v >> 11) & 0x1F) << 3;
      ziel[p + 1] = ((v >> 5) & 0x3F) << 2;
      ziel[p + 2] = (v & 0x1F) << 3;
      ziel[p + 3] = 255;
    }
    kontext.putImageData(bild, 0, 0);
    el("prev-status").textContent = a.breite + " x " + a.hoehe + " (1/" + scale + ")";
  }).catch(function (f) {
    el("prev-status").textContent = "Fehler: " + f;
  });
}

function neuStart() {
  if (!confirm("Board wirklich neu starten?")) {
    return;
  }
  api("/api/reset", { method: "POST" }).then(function () {
    zeige("Neustart ausgeloest.\n");
  });
}

// ---------------------------------------------------------------- Editor

function setStatus(text) {
  el("e-status").textContent = text;
}

function laden() {
  var p = el("e-path").value;
  setStatus("oeffne ...");
  api("/api/file?path=" + encodeURIComponent(p)).then(function (a) {
    if (a.error) {
      setStatus(a.error);
      return;
    }
    if (a.binary) {
      setStatus("Binaerdatei (" + a.size + " Byte) -- nur Download");
      return;
    }
    editorSet(a.data);
    setStatus("geoeffnet: " + a.data.length + " Zeichen");
    zeilenInfo();
  }).catch(function (f) {
    setStatus("Fehler: " + f);
  });
}

function speichern() {
  var p = el("e-path").value;
  setStatus("speichere ...");
  api("/api/file?path=" + encodeURIComponent(p), {
    method: "POST",
    headers: { "Content-Type": "text/plain" },
    body: editorText()
  }).then(function (a) {
    setStatus(a.error ? a.error : ("gespeichert: " + a.bytes + " Byte"));
    dateienLaden();
  }).catch(function (f) {
    setStatus("Fehler: " + f);
  });
}

function ausfuehren() {
  var code = editorText();
  api("/api/exec", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code: code })
  }).then(function (a) {
    setStatus("ausgefuehrt");
    zeige("--- " + el("e-path").value + " ---\n" + a.output + "\n");
    zustand();
  }).catch(function (f) {
    setStatus("Fehler: " + f);
  });
}

function loeschen() {
  var p = el("e-path").value;
  if (!confirm("Loeschen: " + p + " ?")) {
    return;
  }
  api("/api/file", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: p })
  }).then(function (a) {
    setStatus(a.error ? a.error : "geloescht");
    dateienLaden();
  });
}

function zeilenInfo() {
  if (editor) {
    var k = editor.getCursor();
    el("e-cursor").textContent = "Zeile " + (k.line + 1) + ", Spalte " + (k.ch + 1);
    el("e-info").textContent = editor.lineCount() + " Zeilen, "
      + editor.getValue().length + " Zeichen";
    return;
  }
  var t = el("code");
  var bis = t.value.slice(0, t.selectionStart);
  var zeilen = bis.split("\n");
  el("e-cursor").textContent = "Zeile " + zeilen.length + ", Spalte " + (zeilen[zeilen.length - 1].length + 1);
  el("e-info").textContent = t.value.length + " Zeichen, " + t.value.split("\n").length + " Zeilen";
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
      speichern();
    }
  });
}

// ---------------------------------------------------------------- Dateien

function dateienLaden() {
  api("/api/files?path=" + encodeURIComponent(aktuellerPfad)).then(function (a) {
    if (a.error) {
      el("f-rows").innerHTML = '<tr><td colspan="3">' + a.error + "</td></tr>";
      return;
    }
    el("f-path").textContent = a.path;
    if (a.speicher && a.speicher.frei !== undefined) {
      el("f-free").textContent = "frei: " + Math.round(a.speicher.frei / 1024) + " KB von "
        + Math.round(a.speicher.gesamt / 1024) + " KB";
    }
    var zeilen = "";
    for (var i = 0; i < a.entries.length; i++) {
      var e = a.entries[i];
      var ziel = (a.path === "/" ? "" : a.path) + "/" + e.name;
      var p = encodeURIComponent(ziel);
      var akt = "";
      if (e.dir) {
        akt += '<button class="btn" onclick="ordnerOeffnen(\'' + ziel + '\')">Oeffnen</button>';
      } else {
        akt += '<button class="btn" onclick="bearbeiten(\'' + ziel + '\')">Bearbeiten</button>'
            + '<a class="btn" href="/api/file?download=1&path=' + p + '">Download</a>';
      }
      akt += '<button class="btn" onclick="umbenennen(\'' + ziel + '\')">Umbenennen</button>'
           + '<button class="btn" onclick="weg(\'' + ziel + '\')">Loeschen</button>';
      zeilen += "<tr><td>" + (e.dir ? "&#128193; " : "") + e.name + "</td>"
              + '<td class="n">' + (e.dir ? "" : e.size) + "</td>"
              + '<td class="act">' + akt + "</td></tr>";
    }
    el("f-rows").innerHTML = zeilen || '<tr><td colspan="3">(leer)</td></tr>';
  }).catch(function (f) {
    el("f-rows").innerHTML = '<tr><td colspan="3">' + f + "</td></tr>";
  });
}

function ordnerOeffnen(p) {
  aktuellerPfad = p;
  dateienLaden();
}

function hoch() {
  var t = aktuellerPfad.split("/").filter(function (x) { return x; });
  t.pop();
  aktuellerPfad = "/" + t.join("/");
  dateienLaden();
}

function bearbeiten(p) {
  el("e-path").value = p;
  laden();
  document.querySelector('nav button[data-tab="editor"]').click();
}

function weg(p) {
  if (!confirm("Loeschen: " + p + " ?")) {
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
    dateienLaden();
  });
}

function umbenennen(p) {
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
    dateienLaden();
  });
}

function hochladen() {
  var f = el("upload").files[0];
  if (!f) {
    alert("keine Datei gewaehlt");
    return;
  }
  var ziel = (aktuellerPfad === "/" ? "" : aktuellerPfad) + "/" + f.name;
  var leser = new FileReader();
  leser.onload = function () {
    api("/api/file?path=" + encodeURIComponent(ziel), {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: leser.result
    }).then(function (a) {
      if (a.error) {
        alert(a.error);
      }
      dateienLaden();
    });
  };
  leser.readAsArrayBuffer(f);
}

function neueDatei() {
  var n = prompt("Name der neuen Datei:", "neu.py");
  if (!n) {
    return;
  }
  var ziel = (aktuellerPfad === "/" ? "" : aktuellerPfad) + "/" + n;
  api("/api/file?path=" + encodeURIComponent(ziel), {
    method: "POST",
    headers: { "Content-Type": "text/plain" },
    body: "# " + n + "\n"
  }).then(function () {
    bearbeiten(ziel);
  });
}

function neuerOrdner() {
  var n = prompt("Name des neuen Ordners:", "daten");
  if (!n) {
    return;
  }
  api("/api/mkdir", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: (aktuellerPfad === "/" ? "" : aktuellerPfad) + "/" + n })
  }).then(function (a) {
    if (a.error) {
      alert(a.error);
    }
    dateienLaden();
  });
}

// ---------------------------------------------------------------- Konfiguration

function cfgLaden() {
  api("/api/config").then(function (a) {
    var c = a.config || {};
    el("c-ssid").value = c.ssid || "";
    el("c-pass").value = "";
    el("c-pass").placeholder = c.password_gesetzt ? "unveraendert lassen" : "kein Passwort gesetzt";
    el("c-host").value = c.hostname || "";
    el("c-bri").value = c.brightness !== undefined ? c.brightness : 70;
    el("c-bl").value = c.backlight ? "1" : "0";
    el("c-bri-val").textContent = el("c-bri").value + " %";
  });
}

function cfgSpeichern() {
  api("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ssid: el("c-ssid").value,
      password: el("c-pass").value,
      hostname: el("c-host").value,
      brightness: parseInt(el("c-bri").value, 10),
      backlight: el("c-bl").value === "1"
    })
  }).then(function (a) {
    el("c-status").textContent = a.error ? a.error : "gespeichert (Neustart fuer WLAN/Hostname)";
    cfgLaden();
  });
}

function briJetzt() {
  var w = parseInt(el("c-bri").value, 10);
  var an = el("c-bl").value === "1";
  var code = "import display_config\n"
           + "d = display_config.LAST_DISPLAY\n"
           + "d.set_backlight(" + (an ? w : 0) + ")\n"
           + "print('Helligkeit gesetzt')";
  api("/api/exec", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code: code })
  }).then(function (a) {
    el("c-status").textContent = "angewendet";
    zeige(a.output + "\n");
  });
}

// ---------------------------------------------------------------- Zustand

function zustand() {
  api("/api/state").then(function (a) {
    el("p-ip").textContent = "IP " + (a.ip || "?");
    el("p-heap").textContent = "Heap " + (a.heap ? Math.round(a.heap / 1024) + " KB" : "?");
    el("p-up").textContent = "Laufzeit " + (a.uptime_s ? Math.round(a.uptime_s) + " s" : "?");
    if (a.speicher && a.speicher.frei !== undefined) {
      el("p-fs").textContent = "frei " + Math.round(a.speicher.frei / 1024) + " KB";
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
      senden();
    }
    if (e.key === "ArrowUp" && verlauf.length) {
      vpos = Math.max(0, vpos - 1);
      this.value = verlauf[vpos] || "";
    }
    if (e.key === "ArrowDown") {
      vpos = Math.min(verlauf.length, vpos + 1);
      this.value = verlauf[vpos] || "";
    }
  });
  el("c-bri").addEventListener("input", function () {
    el("c-bri-val").textContent = this.value + " %";
  });
  cfgLaden();
  dateienLaden();
  zustand();
  setInterval(zustand, 5000);
}

window.addEventListener("load", start);
