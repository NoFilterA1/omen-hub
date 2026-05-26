"""Keyboard page: backlight color, effects, live preview."""

import sys
from pathlib import Path
from threading import Event

from PyQt6.QtCore import Qt, QThread, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QSlider, QCheckBox
)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.rgb import write_color, PRESETS, is_available
from core.theme import get_accent_color
from core import settings as _settings
from gui.i18n import t as _t
from gui.widgets import ColorSwatch, KeyboardPreview, InlineColorPicker


def _scale_color(hex_color: str, brightness: float) -> str:
    r = int(int(hex_color[0:2], 16) * brightness)
    g = int(int(hex_color[2:4], 16) * brightness)
    b = int(int(hex_color[4:6], 16) * brightness)
    return f"{r:02x}{g:02x}{b:02x}"


class RainbowThread(QThread):
    def __init__(self, speed_slider=None, brightness_slider=None):
        super().__init__()
        self._speed  = speed_slider
        self._bright = brightness_slider
        self._stop   = Event()

    def run(self):
        from PyQt6.QtGui import QColor
        hue = 0
        while not self._stop.is_set():
            bright_val = int(255 * (self._bright.value() / 100.0)) if self._bright else 255
            col = QColor.fromHsv(int(hue) % 360, 255, bright_val).name()[1:]
            try:
                write_color(col)
            except OSError:
                break
            delay = 0.02 + (1.0 - self._speed.value() / 100.0) * 0.08 if self._speed else 0.05
            hue = (hue + 1) % 360
            self._stop.wait(delay)

    def stop(self):
        self._stop.set()
        self.wait()


class FlashThread(QThread):
    def __init__(self, colors: list[str], delay_ms: int = 150, brightness_slider=None):
        super().__init__()
        self._colors = colors
        self._delay  = delay_ms / 1000.0
        self._bright = brightness_slider
        self._stop   = Event()

    def run(self):
        idx = 0
        while not self._stop.is_set():
            b = (self._bright.value() / 100.0) if self._bright else 1.0
            try:
                write_color(_scale_color(self._colors[idx % len(self._colors)], b))
            except OSError:
                break
            idx += 1
            self._stop.wait(self._delay)

    def stop(self):
        self._stop.set()
        self.wait()


EFFECTS = ["static", "rainbow", "police", "newyear"]


class KeyboardPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread: QThread | None = None
        kb = _settings.load().get("keyboard", {})
        self._current_color = kb.get("color", "00cc66")
        self._active_effect = kb.get("effect", "static")
        self._saved_brightness = kb.get("brightness", 100)
        self._saved_speed      = kb.get("speed", 30)
        self._write_timer = QTimer(self)
        self._write_timer.setSingleShot(True)
        self._write_timer.setInterval(80)
        self._write_timer.timeout.connect(self._flush_write)
        self._pending_write: str | None = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(0, 0, 0, 0)

        if not is_available():
            warn = QLabel(_t("rgb_unavailable"))
            warn.setStyleSheet("color:#ff6655;font-size:12px;")
            warn.setAlignment(Qt.AlignmentFlag.AlignCenter)
            root.addWidget(warn)
            root.addStretch()
            return

        # Preview
        prev_card = QFrame()
        prev_card.setObjectName("card")
        pl = QVBoxLayout(prev_card)
        pl.setContentsMargins(12, 10, 12, 10)
        pl.setSpacing(4)
        hdr0 = QLabel(_t("preview"))
        hdr0.setObjectName("h")
        pl.addWidget(hdr0)
        self._preview = KeyboardPreview()
        self._preview.set_color(self._current_color)
        pl.addWidget(self._preview)
        root.addWidget(prev_card)

        # Color
        color_card = QFrame()
        color_card.setObjectName("card")
        cl = QVBoxLayout(color_card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(8)
        hdr1 = QLabel(_t("color"))
        hdr1.setObjectName("h")
        cl.addWidget(hdr1)

        sw_row = QHBoxLayout()
        sw_row.setSpacing(8)
        for name, hexc in PRESETS.items():
            sw = ColorSwatch(hexc)
            sw.setToolTip(name)
            sw.clicked.connect(lambda _, c=hexc: self._apply_swatch(c))
            sw_row.addWidget(sw)
        accent = get_accent_color()
        if accent:
            sw_theme = ColorSwatch(accent)
            sw_theme.setToolTip("Theme Color")
            sw_theme.clicked.connect(lambda: self._apply_swatch(accent))
            sw_row.addWidget(sw_theme)
        sw_row.addStretch()
        cl.addLayout(sw_row)

        self._picker = InlineColorPicker(self._current_color)
        self._picker.color_changed.connect(self._apply_static)
        cl.addWidget(self._picker)
        root.addWidget(color_card)

        # Effects
        fx_card = QFrame()
        fx_card.setObjectName("card")
        fl = QVBoxLayout(fx_card)
        fl.setContentsMargins(12, 10, 12, 10)
        fl.setSpacing(8)
        hdr2 = QLabel(_t("effects"))
        hdr2.setObjectName("h")
        fl.addWidget(hdr2)

        fx_row = QHBoxLayout()
        fx_row.setSpacing(8)
        self._fx_btns: dict[str, QPushButton] = {}
        for key in EFFECTS:
            btn = QPushButton(_t(f"fx_{key}"))
            btn.setCheckable(True)
            btn.setStyleSheet(self._fx_btn_style(False))
            btn.clicked.connect(lambda _, k=key: self._activate_effect(k))
            self._fx_btns[key] = btn
            fx_row.addWidget(btn)
        fx_row.addStretch()
        fl.addLayout(fx_row)

        sliders = QHBoxLayout()
        sliders.setSpacing(20)
        for attr, label_key, lo, hi, default in [
            ("_speed_slider",      "speed",      0,  100, 30),
            ("_brightness_slider", "brightness", 5, 100, 100),
        ]:
            col = QVBoxLayout()
            col.setSpacing(2)
            _sl = QLabel(_t(label_key)); _sl.setObjectName("h")
            col.addWidget(_sl)
            s = QSlider(Qt.Orientation.Horizontal)
            s.setRange(lo, hi)
            s.setValue(default)
            s.setFixedWidth(120)
            setattr(self, attr, s)
            col.addWidget(s)
            sliders.addLayout(col)
        self._brightness_slider.valueChanged.connect(self._on_brightness_changed)
        sliders.addStretch()
        fl.addLayout(sliders)
        root.addWidget(fx_card)

        # Follow mode
        follow_card = QFrame()
        follow_card.setObjectName("card")
        fol = QHBoxLayout(follow_card)
        fol.setContentsMargins(12, 8, 12, 8)
        self._follow_cb = QCheckBox(_t("follow_mode"))
        self._follow_cb.setChecked(True)
        fol.addWidget(self._follow_cb)
        fol.addStretch()
        root.addWidget(follow_card)
        root.addStretch()

        # Restore saved state
        self._brightness_slider.setValue(self._saved_brightness)
        self._speed_slider.setValue(self._saved_speed)
        self._picker.set_color(self._current_color)
        self._preview.set_color(self._current_color)
        self._activate_effect(self._active_effect)

    def _brightness(self) -> float:
        return self._brightness_slider.value() / 100.0

    def _write(self, hex_color: str) -> None:
        scaled = _scale_color(hex_color, self._brightness())
        self._preview.set_color(scaled)
        self._pending_write = scaled
        self._write_timer.start()

    def _flush_write(self) -> None:
        if self._pending_write is not None:
            try:
                write_color(self._pending_write)
            except (PermissionError, OSError):
                pass
            self._pending_write = None

    def _save_settings(self) -> None:
        _settings.save_section("keyboard", {
            "color":      self._current_color,
            "effect":     self._active_effect,
            "brightness": self._brightness_slider.value(),
            "speed":      self._speed_slider.value(),
        })

    def _apply_static(self, hex_color: str) -> None:
        self._stop_thread()
        self._current_color = hex_color
        self._write(hex_color)
        self._set_fx_active("static")
        self._save_settings()

    def _apply_swatch(self, hex_color: str) -> None:
        self._picker.set_color(hex_color)
        self._apply_static(hex_color)

    def _on_brightness_changed(self) -> None:
        if self._active_effect == "static":
            self._write(self._current_color)
        self._save_settings()

    def _activate_effect(self, key: str) -> None:
        self._stop_thread()
        self._set_fx_active(key)
        if key == "static":
            self._write(self._current_color)
        elif key == "rainbow":
            self._thread = RainbowThread(self._speed_slider, self._brightness_slider)
            self._thread.start()
        elif key == "police":
            self._thread = FlashThread(["ff0000", "0000ff"], 100, self._brightness_slider)
            self._thread.start()
        elif key == "newyear":
            self._thread = FlashThread(["ff0000", "00cc00"], 500, self._brightness_slider)
            self._thread.start()
        self._save_settings()

    def _stop_thread(self) -> None:
        if self._thread:
            self._thread.stop()
            self._thread = None

    def _set_fx_active(self, key: str) -> None:
        self._active_effect = key
        for k, btn in self._fx_btns.items():
            btn.setChecked(k == key)
            btn.setStyleSheet(self._fx_btn_style(k == key))

    def apply_mode_color(self, mode: str, hex_color: str) -> None:
        if self._follow_cb.isChecked() and self._active_effect == "static":
            self._current_color = hex_color
            self._write(hex_color)
            self._picker.set_color(hex_color)
            self._save_settings()

    def closeEvent(self, event):
        self._stop_thread()
        super().closeEvent(event)

    @staticmethod
    def _btn_style() -> str:
        return ("QPushButton{background:#2a2a2e;color:#ccc;border:1px solid #444;"
                "border-radius:6px;padding:4px 12px;font-size:12px;}"
                "QPushButton:hover{border-color:#888;color:#fff;}")

    @staticmethod
    def _fx_btn_style(active: bool) -> str:
        if active:
            return ("QPushButton{background:#3a3a4a;color:#fff;"
                    "border:1px solid #6666cc;border-radius:6px;"
                    "padding:4px 12px;font-size:12px;}")
        return ("QPushButton{background:#2a2a2e;color:#aaa;"
                "border:1px solid #444;border-radius:6px;"
                "padding:4px 12px;font-size:12px;}"
                "QPushButton:hover{border-color:#777;color:#ddd;}")
