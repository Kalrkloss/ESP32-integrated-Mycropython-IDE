# Kann man eine FreeRTOS-Task „in Annex einhängen"?

Frage: Annex basiert auf FreeRTOS — lässt sich nachträglich eine Task einbauen, die die
USB-Wiedergabe macht, und diese in Annex einhängen?

Kurz: **Nein.** Nicht weil FreeRTOS fehlt, sondern weil es in einer fertig geflashten
Firmware keinen Ort gibt, an dem fremder Code landet. Eine Task existiert nur, wenn sie
mit der Firmware **zusammen gelinkt** wurde. Annex hat kein Plugin-, Modul- oder
CSUB-System, über das man zur Laufzeit nativen Code nachlädt — die Dokumentation kennt
ausschließlich eingebaute Kommandos (`MODULE`-Varianten der Firmware sind Compile-Zeit-
Ausprägungen des Autors, kein Nutzer-Erweiterungspunkt).

## Die drei technisch denkbaren Wege — und warum sie hier scheitern

### 1. ELF zur Laufzeit nachladen

Es gibt so etwas tatsächlich: `espressif/elf_loader`
(<https://components.espressif.com/components/espressif/elf_loader/>) lädt auf ESP32/S3
ELF-Dateien bzw. Shared Objects zur Laufzeit und bietet `dlopen`/`dlsym`/`dlclose`.
Damit könnte man prinzipiell eine nachkompilierte `.so` mit einer FreeRTOS-Task starten.

Voraussetzungen, die hier fehlen:

- Die **Firmware** muss ihre Symbole für den Loader bereitstellen. Der ELF-Loader arbeitet
  mit `esp_elf_register_symbol(...)` einer vom Projekt erzeugten Symboltabelle
  (`build/generated/.../esp_elf_example.c`). Annex ist ein fertiges, symbolfreies
  Image — es registriert nichts.
- Deine `.so` müsste gegen Annex' interne Funktionen binden: `xTaskCreate`, die
  USB-Host-API, die BASIC-Kommando-Tabelle, den Sound-/I2S-Code. Deren Adressen stehen
  nirgends. Sie müssten per Disassemblierung/Decompilierung aus dem Binary geholt werden —
  genau das, was die Annex-Lizenz ausdrücklich verbietet.
- ABI-Gleichheit: der Code müsste mit derselben ESP-IDF-Version und denselben
  `sdkconfig`-Optionen gebaut sein wie Annexe Firmware. Beides ist nicht veröffentlicht.

### 2. Binary patchen

Freien Flash suchen, in eine Init-Funktion einen Sprung auf einen Trampoline (Xtensa-
Assembler) patchen, der `xTaskCreate` aufruft. Ergebnis: im besten Fall läuft eine Task.

Was damit **nicht** passiert:

- Keine Anbindung an Annex. Ohne Hook in die Kommando-Tabelle gibt es keine
  BASIC-Kommandos; der Nutzer kann die Wiedergabe nicht aus BASIC steuern.
- Annex' eigene Sound-Engine (`PLAY.*`, `SOUND.*`, I2S + DMA) belegt dieselben
  Peripherie- und DMA-Ressourcen. Zwei konkurrierende Audio-Pfade sind kein Feature,
  sondern ein Fehlerbild.
- Jedes OTA-Update ändert alle Adressen → Patch nach jedem Firmware-Update neu.
- Budget unbekannt: das S3-Image ist 2,87 MB (Bootloader + Partitionstabelle + App),
  freier Platz in der App-Partition und im RAM ist von außen nicht ermittelbar.

### 3. Zweiter Kern / freier OTA-Slot

Der S3 hat zwei Kerne, aber ein Gerät führt **eine** Firmware aus. Ein freier OTA-Slot
wird nicht von selbst gestartet, und es gibt keinen zweiten Kernel, in den man eine
unabhängige Audio-Task legt. Das ist kein Weg.

## Fazit

„Eine Task in Annex einhängen" ist genau die Operation, die **Quellcode voraussetzt**.
Es gibt zwei Wege dorthin:

1. **Der Autor baut es ein** (Weg A). cicciocb hat Task-Ebene, Sound-Engine und
   Kommando-Tabelle; im S3-Build steckt der USB-Host-Stack bereits (Varianten mit
   `HID`/`OTG`, Doku: „USB HID INTERFACE (Mouse, Keyboard, Gamepad) — ESP32-S3 only").
   Für ihn ist ein UAC-Host-Treiber auf Basis von `espressif/usb_host_uac` eine
   überschaubare Ergänzung. Entwurf dafür: [05-feature-request-cicciocb.md](05-feature-request-cicciocb.md)
2. **Eigene Firmware** (Weg B). Dort ist man selbst der Autor: die FreeRTOS-Task für
   USB-Wiedergabe ist trivial, und die BASIC-Kommandoebene hängt man sauber davor.
   Genau dafür existiert dieses Repository — siehe [02-plan.md](02-plan.md).

## Nicht geprüft

- Ob Annex im Inneren doch eine Aufrufstelle für Nutzer-Code hat (aus Handbuch und
  Downloadliste ergibt sich keine; ohne Decompilierung bleibt das eine Annahme).
- Mit welcher ESP-IDF-Version die aktuellen S3-Binaries gebaut sind.
