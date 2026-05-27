"""Settings page: appearance, RGB mode colors, about."""

import sys
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton,
    QCheckBox, QScrollArea, QComboBox
)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import core.rgb as _rgb
from core import settings as _settings
from gui.i18n import t as _t, available as available_languages
from gui.widgets import ColorPickerDialog

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.toml"

_MODES = ["silent", "balanced", "performance"]


def _load_mode_colors() -> dict[str, str]:
    try:
        import tomlkit
        doc = tomlkit.parse(CONFIG_PATH.read_text())
        return dict(doc["rgb"]["mode_colors"])
    except Exception:
        return dict(_rgb.MODE_COLORS)


def _save_mode_colors(colors: dict[str, str]) -> bool:
    try:
        import tomlkit
        doc = tomlkit.parse(CONFIG_PATH.read_text())
        for mode, color in colors.items():
            doc["rgb"]["mode_colors"][mode] = color
        CONFIG_PATH.write_text(tomlkit.dumps(doc))
        _rgb.MODE_COLORS.update(colors)
        return True
    except Exception:
        return False


def _card(title: str = "") -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("card")
    cl = QVBoxLayout(f)
    cl.setContentsMargins(16, 12, 16, 14)
    cl.setSpacing(10)
    if title:
        hdr = QLabel(title)
        hdr.setObjectName("h")
        cl.addWidget(hdr)
    return f, cl


class _ColorRow(QWidget):
    """One mode label + clickable color swatch."""
    picked = pyqtSignal(str, str)  # mode, hex

    def __init__(self, mode: str, label: str, hex_color: str, parent=None):
        super().__init__(parent)
        self._mode = mode
        self._color = hex_color
        hl = QHBoxLayout(self)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(10)
        lbl = QLabel(label)
        lbl.setObjectName("dim")
        lbl.setMinimumWidth(90)
        hl.addWidget(lbl)
        self._swatch = QPushButton()
        self._swatch.setFixedSize(32, 22)
        self._swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self._swatch.clicked.connect(self._pick)
        self._refresh()
        hl.addWidget(self._swatch)
        self._hex_lbl = QLabel(f"#{hex_color}")
        self._hex_lbl.setStyleSheet("color:#555;font-size:11px;font-family:monospace;")
        hl.addWidget(self._hex_lbl)
        hl.addStretch()

    def set_color(self, hex_color: str) -> None:
        self._color = hex_color
        self._refresh()
        self._hex_lbl.setText(f"#{hex_color}")

    def _refresh(self) -> None:
        self._swatch.setStyleSheet(
            f"QPushButton{{background:#{self._color};border:2px solid #444;"
            f"border-radius:4px;}}"
            f"QPushButton:hover{{border-color:#aaa;}}"
        )
        self._swatch.style().unpolish(self._swatch)
        self._swatch.style().polish(self._swatch)
        self._swatch.update()

    def _pick(self) -> None:
        dlg = ColorPickerDialog(self._color, self)
        if dlg.exec():
            self._color = dlg.selected_hex()
            self._refresh()
            self._hex_lbl.setText(f"#{self._color}")
            self.picked.emit(self._mode, self._color)


class SettingsPage(QWidget):
    colors_changed = pyqtSignal()
    accent_changed = pyqtSignal(str)  # hex without #
    theme_changed = pyqtSignal()
    language_changed = pyqtSignal()
    fan_unit_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._colors = _load_mode_colors()
        self._build()

    def _build(self):
        # Wrap in scroll area so it doesn't clip on small windows
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setSpacing(10)
        root.setContentsMargins(0, 0, 4, 0)
        scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        # ── Appearance ────────────────────────────────────────────────────
        ap_card, ap_layout = _card(_t("appearance"))

        temp_row = QHBoxLayout()
        temp_lbl = QLabel(_t("temperature_unit"))
        temp_lbl.setObjectName("dim")
        temp_row.addWidget(temp_lbl)
        temp_row.addStretch()
        self._temp_f = QCheckBox(_t("fahrenheit"))
        self._temp_f.setChecked(_settings.use_fahrenheit())
        self._temp_f.toggled.connect(lambda v: _settings.set_temp_unit(v))
        temp_row.addWidget(self._temp_f)
        ap_layout.addLayout(temp_row)

        self._fan_unit_cb = self._combo_row(
            ap_layout, _t("fan_unit"),
            [(_t("fan_unit_pct"), "pct"), (_t("fan_unit_rpm"), "rpm")],
            _settings.get_fan_unit(), self._on_fan_unit,
        )

        self._accent_row = _ColorRow("accent", _t("accent_color"), _settings.get_accent())
        self._accent_row.picked.connect(self._on_accent_picked)
        ap_layout.addWidget(self._accent_row)

        self._theme_cb = self._combo_row(
            ap_layout, _t("theme"),
            [(_t("theme_dark"), "dark"), (_t("theme_light"), "light")],
            _settings.get_theme(), self._on_theme,
        )
        self._lang_cb = self._combo_row(
            ap_layout, _t("language"),
            available_languages(),
            _settings.get_language(), self._on_language,
        )

        root.addWidget(ap_card)

        # ── RGB Mode Colors ───────────────────────────────────────────────
        rgb_card, rgb_layout = _card(_t("rgb_mode_colors"))
        note = QLabel(_t("rgb_mode_note"))
        note.setObjectName("note")
        note.setWordWrap(True)
        rgb_layout.addWidget(note)

        self._rows: dict[str, _ColorRow] = {}
        for mode in _MODES:
            row = _ColorRow(mode, _t(mode), self._colors.get(mode, "ffffff"))
            row.picked.connect(self._on_color_picked)
            self._rows[mode] = row
            rgb_layout.addWidget(row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_save = QPushButton(_t("save"))
        btn_save.setObjectName("primary")
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.clicked.connect(self._save)
        btn_row.addWidget(btn_save)
        self._status = QLabel("")
        self._status.setObjectName("val")
        btn_row.addWidget(self._status)
        btn_row.addStretch()
        rgb_layout.addLayout(btn_row)

        root.addWidget(rgb_card)

        # ── About ─────────────────────────────────────────────────────────
        about_card, about_layout = _card(_t("about"))

        try:
            product = open("/sys/class/dmi/id/product_name").read().strip()
        except OSError:
            product = "HP OMEN"

        rows = [
            (_t("version"),  "1.0.0-dev"),
            (_t("device"),   product),
            (_t("project"),  "OMEN Hub for Linux"),
        ]
        for label, value in rows:
            hl = QHBoxLayout()
            l = QLabel(label)
            l.setObjectName("valdim")
            l.setMinimumWidth(70)
            v = QLabel(value)
            v.setObjectName("val")
            hl.addWidget(l)
            hl.addWidget(v)
            hl.addStretch()
            about_layout.addLayout(hl)

        root.addWidget(about_card)
        root.addStretch()

    def _combo_row(self, layout, label_text, items, current, handler) -> QComboBox:
        row = QHBoxLayout()
        lbl = QLabel(label_text)
        lbl.setObjectName("dim")
        row.addWidget(lbl)
        row.addStretch()
        cb = QComboBox()
        for text, data in items:
            cb.addItem(text, data)
        idx = next((i for i in range(cb.count()) if cb.itemData(i) == current), 0)
        cb.setCurrentIndex(idx)
        cb.currentIndexChanged.connect(lambda _i, c=cb: handler(c.currentData()))
        row.addWidget(cb)
        layout.addLayout(row)
        return cb

    def _on_theme(self, value: str) -> None:
        _settings.set_theme(value)
        self.theme_changed.emit()

    def _on_language(self, value: str) -> None:
        _settings.set_language(value)
        self.language_changed.emit()

    def _on_fan_unit(self, value: str) -> None:
        _settings.set_fan_unit(value)
        self.fan_unit_changed.emit()

    def _on_accent_picked(self, _mode: str, hex_color: str) -> None:
        _settings.set_accent(hex_color)
        self.accent_changed.emit(hex_color)

    def _on_color_picked(self, mode: str, hex_color: str) -> None:
        self._colors[mode] = hex_color
        self._status.setText(_t("unsaved_changes"))
        self._status.setStyleSheet("color:#cc8833;font-size:11px;")

    def _save(self) -> None:
        ok = _save_mode_colors(self._colors)
        if ok:
            self._status.setText(f"{_t('saved')}  ✓")
            self._status.setStyleSheet("color:#44cc88;font-size:11px;")
            self.colors_changed.emit()
        else:
            self._status.setText(_t("save_failed"))
            self._status.setStyleSheet("color:#ff6655;font-size:11px;")
