import sys
from pathlib import Path
from threading import Event

from PyQt6.QtCore import Qt, QThread
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QColorDialog, QSlider, QCheckBox
)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.rgb import write_color, PRESETS, is_available
from core.theme import get_accent_color
from gui.widgets import ColorSwatch


def _scale_color(hex_color: str, brightness: float) -> str:
    """Scale RGB by brightness (0.0–1.0). Brightness is the only way
    to dim the backlight — hp-wmi exposes no separate brightness register."""
    r = int(int(hex_color[0:2], 16) * brightness)
    g = int(int(hex_color[2:4], 16) * brightness)
    b = int(int(hex_color[4:6], 16) * brightness)
    return f"{r:02x}{g:02x}{b:02x}"


# --- Effect threads --------------------------------------------------------

class RainbowThread(QThread):
    def __init__(self, speed_slider=None, brightness_slider=None):
        super().__init__()
        self._speed    = speed_slider
        self._bright   = brightness_slider
        self._stop     = Event()

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
            # slider 0..100 → delay 100ms..20ms, always +1 hue deg
            # at default (30): ~70ms delay → 25s cycle (close to original 50ms/18s feel)
            delay = 0.02 + (1.0 - self._speed.value() / 100.0) * 0.08 if self._speed else 0.05
            hue = (hue + 1) % 360
            self._stop.wait(delay)

    def stop(self):
        self._stop.set()
        self.wait()


class FlashThread(QThread):
    """Alternates between two colors at fixed delay."""
    def __init__(self, colors: list[str], delay_ms: int = 150, brightness_slider=None):
        super().__init__()
        self._colors = colors
        self._delay  = delay_ms / 1000.0
        self._bright = brightness_slider
        self._stop   = Event()

    def run(self):
        idx = 0
        while not self._stop.is_set():
            raw = self._colors[idx % len(self._colors)]
            b = (self._bright.value() / 100.0) if self._bright else 1.0
            try:
                write_color(_scale_color(raw, b))
            except OSError:
                break
            idx += 1
            self._stop.wait(self._delay)

    def stop(self):
        self._stop.set()
        self.wait()


# --- Page ------------------------------------------------------------------

EFFECTS = [
    ("static",   "Static"),
    ("rainbow",  "Rainbow"),
    ("police",   "Police"),
    ("newyear",  "New Year"),
]


class LightingPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread: QThread | None = None
        self._current_color  = "ffffff"
        self._active_effect  = "static"
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(0, 0, 0, 0)

        if not is_available():
            warn = QLabel("RGB not available.\nCheck that hp-omen-wmi-dkms is installed and udev rules are set up.")
            warn.setStyleSheet("color:#ff6655; font-size:12px;")
            warn.setAlignment(Qt.AlignmentFlag.AlignCenter)
            root.addWidget(warn)
            root.addStretch()
            return

        # --- Static color section ---
        color_card = QFrame()
        color_card.setStyleSheet("QFrame { background:#1e1e22; border-radius:12px; }")
        color_layout = QVBoxLayout(color_card)

        color_hdr = QLabel("Color")
        color_hdr.setStyleSheet("color:#888; font-size:11px; font-weight:bold;")
        color_layout.addWidget(color_hdr)

        swatches_row = QHBoxLayout()
        swatches_row.setSpacing(8)
        for name, hexc in PRESETS.items():
            sw = ColorSwatch(hexc)
            sw.setToolTip(name)
            sw.clicked.connect(lambda _, c=hexc: self._apply_static(c))
            swatches_row.addWidget(sw)
        swatches_row.addStretch()
        color_layout.addLayout(swatches_row)

        btns_row = QHBoxLayout()
        btns_row.setSpacing(8)

        btn_pick = QPushButton("Custom…")
        btn_pick.setStyleSheet(self._btn_style())
        btn_pick.clicked.connect(self._pick_custom)
        btns_row.addWidget(btn_pick)

        accent = get_accent_color()
        if accent:
            btn_theme = QPushButton("Apply Theme Color")
            btn_theme.setStyleSheet(self._btn_style())
            btn_theme.clicked.connect(lambda: self._apply_static(accent))
            btns_row.addWidget(btn_theme)

        btns_row.addStretch()
        color_layout.addLayout(btns_row)
        root.addWidget(color_card)

        # --- Effects section ---
        fx_card = QFrame()
        fx_card.setStyleSheet("QFrame { background:#1e1e22; border-radius:12px; }")
        fx_layout = QVBoxLayout(fx_card)

        fx_hdr = QLabel("Effects")
        fx_hdr.setStyleSheet("color:#888; font-size:11px; font-weight:bold;")
        fx_layout.addWidget(fx_hdr)

        fx_row = QHBoxLayout()
        fx_row.setSpacing(8)
        self._fx_buttons: dict[str, QPushButton] = {}
        for key, label in EFFECTS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setStyleSheet(self._fx_btn_style(False))
            btn.clicked.connect(lambda _, k=key: self._activate_effect(k))
            self._fx_buttons[key] = btn
            fx_row.addWidget(btn)
        fx_row.addStretch()
        fx_layout.addLayout(fx_row)

        sliders_row = QHBoxLayout()
        sliders_row.setSpacing(16)

        # Speed slider (rainbow only)
        speed_col = QVBoxLayout()
        speed_col.setSpacing(2)
        speed_col.addWidget(QLabel("Speed", styleSheet="color:#888; font-size:11px;"))
        self._speed_slider = QSlider(Qt.Orientation.Horizontal)
        self._speed_slider.setRange(0, 100)
        self._speed_slider.setValue(30)
        self._speed_slider.setFixedWidth(110)
        speed_col.addWidget(self._speed_slider)
        sliders_row.addLayout(speed_col)

        # Brightness slider
        bright_col = QVBoxLayout()
        bright_col.setSpacing(2)
        bright_col.addWidget(QLabel("Brightness", styleSheet="color:#888; font-size:11px;"))
        self._brightness_slider = QSlider(Qt.Orientation.Horizontal)
        self._brightness_slider.setRange(5, 100)
        self._brightness_slider.setValue(100)
        self._brightness_slider.setFixedWidth(110)
        self._brightness_slider.valueChanged.connect(self._on_brightness_changed)
        bright_col.addWidget(self._brightness_slider)
        sliders_row.addLayout(bright_col)

        sliders_row.addStretch()
        fx_layout.addLayout(sliders_row)
        root.addWidget(fx_card)

        # --- Mode color follow ---
        follow_card = QFrame()
        follow_card.setStyleSheet("QFrame { background:#1e1e22; border-radius:12px; }")
        follow_layout = QHBoxLayout(follow_card)
        self._follow_cb = QCheckBox("Change color with performance mode")
        self._follow_cb.setStyleSheet("color:#ccc; font-size:12px;")
        self._follow_cb.setChecked(True)
        follow_layout.addWidget(self._follow_cb)
        follow_layout.addStretch()
        root.addWidget(follow_card)

        root.addStretch()
        self._set_fx_active("static")

    # ── Helpers ───────────────────────────────────────────────────────────

    def _brightness(self) -> float:
        return self._brightness_slider.value() / 100.0

    def _write(self, hex_color: str) -> None:
        try:
            write_color(_scale_color(hex_color, self._brightness()))
        except (PermissionError, OSError):
            pass

    # ── Color / static ────────────────────────────────────────────────────

    def _apply_static(self, hex_color: str) -> None:
        self._stop_thread()
        self._current_color = hex_color
        self._write(hex_color)
        self._set_fx_active("static")

    def _on_brightness_changed(self) -> None:
        # Live preview for static; threads read the slider themselves.
        if self._active_effect == "static":
            try:
                write_color(_scale_color(self._current_color, self._brightness()))
            except (PermissionError, OSError):
                pass

    def _pick_custom(self) -> None:
        c = QColorDialog.getColor()
        if c.isValid():
            self._apply_static(c.name()[1:])

    # ── Effects ───────────────────────────────────────────────────────────

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

    def _stop_thread(self) -> None:
        if self._thread:
            self._thread.stop()
            self._thread = None

    def _set_fx_active(self, active_key: str) -> None:
        self._active_effect = active_key
        for key, btn in self._fx_buttons.items():
            btn.setChecked(key == active_key)
            btn.setStyleSheet(self._fx_btn_style(key == active_key))

    # ── Called from MainWindow when performance mode changes ──────────────

    def apply_mode_color(self, mode: str, hex_color: str) -> None:
        """Apply mode color only when static effect is active and follow is on.
        Never interrupts a running animation (rainbow, police, etc.)."""
        if self._follow_cb.isChecked() and self._active_effect == "static":
            self._current_color = hex_color
            self._write(hex_color)

    def closeEvent(self, event):
        self._stop_thread()
        super().closeEvent(event)

    # ── Styles ────────────────────────────────────────────────────────────

    @staticmethod
    def _btn_style() -> str:
        return """
            QPushButton {
                background:#2a2a2e; color:#ccc;
                border:1px solid #444; border-radius:6px;
                padding:4px 12px; font-size:12px;
            }
            QPushButton:hover { border-color:#888; color:#fff; }
        """

    @staticmethod
    def _fx_btn_style(active: bool) -> str:
        if active:
            return """
                QPushButton {
                    background:#3a3a4a; color:#ffffff;
                    border:1px solid #6666cc; border-radius:6px;
                    padding:4px 12px; font-size:12px;
                }
            """
        return """
            QPushButton {
                background:#2a2a2e; color:#aaa;
                border:1px solid #444; border-radius:6px;
                padding:4px 12px; font-size:12px;
            }
            QPushButton:hover { border-color:#777; color:#ddd; }
        """
