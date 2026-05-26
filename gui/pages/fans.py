"""Fans page: interactive fan curve editor with per-mode curves."""

import sys
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QSlider
)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.fan import DEFAULT_MODES
from gui import theme
from gui.i18n import t as _t
from gui.widgets import FanCurveEditor

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.toml"

_MODES = [("silent", "silent"), ("balanced", "balanced"), ("performance", "performance")]


def _load_curves() -> dict[str, dict]:
    result = {}
    for name, mode in DEFAULT_MODES.items():
        result[name] = {
            "temp_curve":  list(mode.temp_curve),
            "speed_curve": [int(s) for s in mode.speed_curve],
            "idle_speed":  int(mode.idle_speed),
        }
    try:
        import tomlkit
        doc = tomlkit.parse(CONFIG_PATH.read_text())
        for name, vals in doc.get("fan", {}).get("modes", {}).items():
            if name in result and "temp_curve" in vals and "speed_curve" in vals:
                result[name]["temp_curve"]  = list(vals["temp_curve"])
                result[name]["speed_curve"] = [int(s) for s in vals["speed_curve"]]
                result[name]["idle_speed"]  = int(vals.get("idle_speed", 0))
    except Exception:
        pass
    return result


def _reload_daemon() -> None:
    try:
        from gui.ipc import send_command
        send_command({"action": "reload_config"}, timeout=2.0)
    except Exception:
        pass


def _save_curves(curves: dict[str, dict]) -> bool:
    try:
        import tomlkit
        doc = tomlkit.parse(CONFIG_PATH.read_text())
        for name, data in curves.items():
            sec = doc["fan"]["modes"][name]
            tc = tomlkit.array()
            tc.extend(data["temp_curve"])
            sc = tomlkit.array()
            sc.extend(data["speed_curve"])
            sec["temp_curve"]  = tc
            sec["speed_curve"] = sc
            sec["idle_speed"]  = data["idle_speed"]
        CONFIG_PATH.write_text(tomlkit.dumps(doc))
        return True
    except Exception:
        return False


class FansPage(QWidget):
    saved = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._curves   = _load_curves()
        self._defaults = _load_curves()
        self._current  = "balanced"
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(0, 0, 0, 0)

        # ── Curve card ────────────────────────────────────────────────────
        curve_card = QFrame()
        curve_card.setObjectName("card")
        cl = QVBoxLayout(curve_card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(8)

        hdr = QLabel(_t("fan_curve"))
        hdr.setObjectName("h")
        cl.addWidget(hdr)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(6)
        self._mode_btns: dict[str, QPushButton] = {}
        for key, i18n_key in _MODES:
            btn = QPushButton(_t(i18n_key))
            btn.setFlat(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(True)
            self._apply_mode_btn_style(btn, False)
            btn.clicked.connect(lambda _, k=key: self._switch(k))
            self._mode_btns[key] = btn
            mode_row.addWidget(btn)
        mode_row.addStretch()
        cl.addLayout(mode_row)

        self._editor = FanCurveEditor()
        self._editor.curve_changed.connect(self._on_curve_changed)
        cl.addWidget(self._editor)

        hint = QLabel(_t("fan_curve_hint"))
        hint.setObjectName("note")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(hint)

        root.addWidget(curve_card)

        # ── Idle speed card ───────────────────────────────────────────────
        idle_card = QFrame()
        idle_card.setObjectName("card")
        il = QHBoxLayout(idle_card)
        il.setContentsMargins(12, 8, 12, 8)
        il.setSpacing(10)

        idle_lbl = QLabel(_t("idle_speed"))
        idle_lbl.setObjectName("h")
        il.addWidget(idle_lbl)

        self._idle_sl = QSlider(Qt.Orientation.Horizontal)
        self._idle_sl.setRange(0, 50)
        self._idle_sl.setFixedWidth(130)
        self._idle_sl.valueChanged.connect(self._on_idle_changed)
        il.addWidget(self._idle_sl)

        self._idle_val = QLabel("0%")
        self._idle_val.setObjectName("val")
        self._idle_val.setMinimumWidth(28)
        il.addWidget(self._idle_val)
        il.addStretch()

        root.addWidget(idle_card)

        # ── Action row ────────────────────────────────────────────────────
        act_row = QHBoxLayout()
        act_row.setSpacing(8)

        btn_reset = QPushButton(_t("reset_defaults"))
        btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reset.clicked.connect(self._reset)
        act_row.addWidget(btn_reset)

        btn_save = QPushButton(_t("save"))
        btn_save.setObjectName("primary")
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.clicked.connect(self._save)
        act_row.addWidget(btn_save)

        self._status_lbl = QLabel("")
        self._status_lbl.setObjectName("val")
        act_row.addWidget(self._status_lbl)
        act_row.addStretch()
        root.addLayout(act_row)

        root.addStretch()
        self._switch("balanced")

    # ── Internal ─────────────────────────────────────────────────────────────

    def _switch(self, key: str) -> None:
        self._current = key
        for k, btn in self._mode_btns.items():
            active = k == key
            btn.setChecked(active)
            self._apply_mode_btn_style(btn, active)
        data = self._curves[key]
        self._editor.set_curve(data["temp_curve"], data["speed_curve"], data["idle_speed"])
        self._idle_sl.blockSignals(True)
        self._idle_sl.setValue(data["idle_speed"])
        self._idle_sl.blockSignals(False)
        self._idle_val.setText(f"{data['idle_speed']}%")
        self._status_lbl.setText("")
        self._status_lbl.setStyleSheet("")

    def _on_curve_changed(self, temps: list, speeds: list) -> None:
        self._curves[self._current]["temp_curve"]  = temps
        self._curves[self._current]["speed_curve"] = speeds
        self._status_lbl.setText(_t("unsaved_changes"))
        self._status_lbl.setStyleSheet("color:#cc8833;font-size:11px;")

    def _on_idle_changed(self, val: int) -> None:
        self._idle_val.setText(f"{val}%")
        self._curves[self._current]["idle_speed"] = val
        self._editor.set_idle_speed(val)
        self._status_lbl.setText(_t("unsaved_changes"))
        self._status_lbl.setStyleSheet("color:#cc8833;font-size:11px;")

    def _reset(self) -> None:
        for key in self._curves:
            self._curves[key] = {
                "temp_curve":  list(self._defaults[key]["temp_curve"]),
                "speed_curve": list(self._defaults[key]["speed_curve"]),
                "idle_speed":  self._defaults[key]["idle_speed"],
            }
        self._switch(self._current)
        self._status_lbl.setText(_t("reset_to_defaults_hint"))
        self._status_lbl.setStyleSheet("color:#cc8833;font-size:11px;")

    def _save(self) -> None:
        ok = _save_curves(self._curves)
        if not ok:
            self._status_lbl.setText(_t("save_failed"))
            self._status_lbl.setStyleSheet("color:#ff6655;font-size:11px;")
            return

        self.saved.emit()
        _reload_daemon()
        self._status_lbl.setText(f"{_t('saved')}  ✓")
        self._status_lbl.setStyleSheet("color:#44cc88;font-size:11px;")

    # ── Style helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _apply_mode_btn_style(btn: QPushButton, active: bool) -> None:
        ac = theme.color("accent")
        if active:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {ac};
                    border: none;
                    border-bottom: 2px solid {ac};
                    border-radius: 0;
                    font-size: 12px;
                    font-weight: bold;
                    padding: 4px 12px;
                }}
            """)
        else:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {theme.color('text_mute')};
                    border: none;
                    border-bottom: 2px solid transparent;
                    border-radius: 0;
                    font-size: 12px;
                    padding: 4px 12px;
                }}
                QPushButton:hover {{
                    color: {theme.color('text_dim')};
                }}
            """)
