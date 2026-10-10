# AXS15231B mit stueckweiserem Flush.
#
# Problem: Der SPI-Bus ist auf max_transfer_sz = SPI_LL_DMA_MAX_BIT_LEN/8 = 32768 Byte
# begrenzt (siehe micropy_updates/esp32/machine_hw_spi.c). Der Standardtreiber schickt
# den kompletten Frame (320*480*2 = 307200 Byte) in EINEM tx_color-Aufruf -- das
# scheitert mit "OSError: 257(lcd_panel_io_tx_color)" (ESP_ERR_NO_MEM). Der Fork-Branch
# feature/spi_bus_fast loest das mit einem eigenen DMA-Bus; hier geht es ohne Rebuild:
# dieselbe Flush-Logik, nur wird der Datenstrom in busgrosse Bloecke zerlegt.
#
# Der erste Block traegt das Kommando (setzt das Schreibfenster), alle weiteren werden
# mit cmd=-1 gesendet (nur Daten, kein neues Kommando) -- das Panel haengt die Daten
# automatisch an. Die Blockgroesse ist ein Vielfaches einer Zeile (320 * 2 = 640 Byte),
# damit kein Block mitten in einer Zeile endet.

import axs15231b
import lvgl as lv


class AXS15231B(axs15231b.AXS15231B):
    """Wie der Originaltreiber, aber mit stueckweisem Full-Frame-Flush.

    Der Klassenname muss `AXS15231B` bleiben: display_driver_framework laedt die
    Init-Sequenz ueber den Klassennamen (`_axs15231b_init`).
    """

    _DEFAULT_CHUNK = 30720  # 48 Zeilen * 640 Byte -- nachgemessen: 30720 geht, 32000 nicht

    def __init__(self, *args, **kwargs):
        chunk = kwargs.pop("chunk_bytes", self._DEFAULT_CHUNK)
        self._chunk_bytes = chunk - (chunk % 640)
        if self._chunk_bytes <= 0:
            raise ValueError("chunk_bytes zu klein")
        super().__init__(*args, **kwargs)

    def _flush_cb(self, _driver, area, color_p):
        x1 = area.x1 + self._offset_x
        x2 = area.x2 + self._offset_x
        y1 = area.y1 + self._offset_y
        y2 = area.y2 + self._offset_y

        size = (
            (x2 - x1 + 1) *
            (y2 - y1 + 1) *
            lv.color_format_get_size(self._color_space)
        )

        cmd = self._set_memory_location(x1, y1, x2, y2)
        view = color_p.__dereference__(size)
        total = len(view)
        last = self._disp_drv.flush_is_last()

        if total <= self._chunk_bytes:
            self._data_bus.tx_color(cmd, view, x1, y1, x2, y2, self._rotation, last)
            return

        pos = 0
        while pos < total:
            part = view[pos:pos + self._chunk_bytes]
            self._data_bus.tx_color(
                cmd if pos == 0 else -1, part, x1, y1, x2, y2, self._rotation, last)
            pos += self._chunk_bytes
