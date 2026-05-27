"""Info page: sensor gauges, performance mode, system load bars, fan curve."""

import sys
import threading
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRectF, QPointF
from PyQt6.QtGui import QPainter, QPen
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton, QSplitter,
)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.sensors import (read_cpu_temp, read_gpu_temp, read_fan_rpms,
                           read_cpu_load, read_cpu_freq, read_ram_usage, read_gpu_stats)
from core.fan import modes_from_config, DEFAULT_MODES
from gui import theme
from gui.i18n import t as _t
from gui.widgets import TempGauge, FanWidget, ModeButton, UsageBar, FanCurveChart
from gui.pages.system import _supergfxctl_mode, _supergfxctl_set

_CONFIG = Path(__file__).parent.parent.parent / "config.toml"

MODES = ["silent", "balanced", "performance"]


class _MuxControl(QPushButton):
    """Compact flat tab-style button that shows one GPU MUX mode.

    Active state: accent-colored text + 2 px accent underline.
    Inactive state: muted text + transparent underline (hover -> dim).
    """

    def __init__(self, mode: str, label: str, parent=None):
        super().__init__(label, parent)
        self._mode = mode
        self._active = False
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(_t("gpu_mode") + f": {label}")
        self._refresh()

    def set_active(self, active: bool) -> None:
        if self._active == active:
            return
        self._active = active
        self._refresh()

    def _refresh(self) -> None:
        ac = theme.color("accent")
        if self._active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {ac};
                    border: none;
                    border-bottom: 2px solid {ac};
                    border-radius: 0;
                    font-size: 11px;
                    font-weight: bold;
                    padding: 4px 6px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {theme.color('text_mute')};
                    border: none;
                    border-bottom: 2px solid transparent;
                    border-radius: 0;
                    font-size: 11px;
                    padding: 4px 6px;
                }}
                QPushButton:hover {{
                    color: {theme.color('text_dim')};
                }}
            """)


class _GpuIcon(QWidget):
    """Tiny chip glyph: single chip = integrated, dual chip = hybrid."""

    def __init__(self, dual: bool, parent=None):
        super().__init__(parent)
        self._dual = dual
        self.setFixedSize(34, 20)
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(theme.qcolor("text_mute"), 1.3))
        p.setBrush(Qt.BrushStyle.NoBrush)

        def chip(x: float) -> None:
            p.drawRoundedRect(QRectF(x, 5, 11, 11), 2, 2)
            for i in range(3):
                px = x + 2.5 + i * 3.0
                p.drawLine(QPointF(px, 5), QPointF(px, 2.5))
                p.drawLine(QPointF(px, 16), QPointF(px, 18.5))

        if self._dual:
            chip(6); chip(17)
        else:
            chip(11.5)
        p.end()


def _mux_block(dual: bool, control: "_MuxControl") -> QWidget:
    w = QWidget()
    w.setStyleSheet("background: transparent;")
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(2)
    v.addWidget(_GpuIcon(dual), alignment=Qt.AlignmentFlag.AlignHCenter)
    v.addWidget(control, alignment=Qt.AlignmentFlag.AlignHCenter)
    return w


def _card():
    f = QFrame()
    f.setObjectName("card")
    return f


def _load_modes():
    try:
        import tomlkit
        return modes_from_config(tomlkit.loads(_CONFIG.read_text()))
    except Exception:
        return dict(DEFAULT_MODES)


class InfoPage(QWidget):
    mode_requested = pyqtSignal(str)
    _gpu_result = pyqtSignal(str, bool, str)  # mode, ok, err

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_mode = "balanced"
        self._modes = _load_modes()
        # MUX controls (may remain None if supergfxctl is unavailable)
        self._mux_integrated: _MuxControl | None = None
        self._mux_hybrid: _MuxControl | None = None
        self._mux_hint: QLabel | None = None
        self._mux_current: str | None = None
        self._gpu_result.connect(self._on_gpu_switch_done)
        self._build()
        t = QTimer(self)
        t.setInterval(2000)
        t.timeout.connect(self._poll)
        t.start()

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(6)
        root.setContentsMargins(0, 0, 0, 0)

        # ── Sensors card ──────────────────────────────────────────────────
        sc = _card()
        sc_v = QVBoxLayout(sc)
        sc_v.setContentsMargins(12, 10, 12, 8)
        sc_v.setSpacing(2)

        sl = QHBoxLayout()
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)
        self.cpu_gauge = TempGauge("CPU")
        self.gpu_gauge = TempGauge("GPU")
        self.fan1 = FanWidget("Fan 1")
        self.fan2 = FanWidget("Fan 2")

        # Probe supergfxctl once; build MUX controls only when available
        _initial_mode = _supergfxctl_mode()
        if _initial_mode is not None:
            self._mux_current = _initial_mode
            self._mux_integrated = _MuxControl("Integrated", _t("mux_integrated"))
            self._mux_hybrid = _MuxControl("Hybrid", _t("mux_hybrid"))
            self._mux_integrated.set_active(_initial_mode == "Integrated")
            self._mux_hybrid.set_active(_initial_mode == "Hybrid")
            self._mux_integrated.clicked.connect(
                lambda: self._switch_gpu("Integrated")
            )
            self._mux_hybrid.clicked.connect(
                lambda: self._switch_gpu("Hybrid")
            )

        sl.addStretch(1)
        if self._mux_integrated is not None:
            sl.addWidget(_mux_block(False, self._mux_integrated))
            sl.addSpacing(10)
        sl.addWidget(self.cpu_gauge)
        sl.addSpacing(14)
        sl.addWidget(self.fan1)
        sl.addWidget(self.fan2)
        sl.addSpacing(14)
        sl.addWidget(self.gpu_gauge)
        if self._mux_hybrid is not None:
            sl.addSpacing(10)
            sl.addWidget(_mux_block(True, self._mux_hybrid))
        sl.addStretch(1)
        sc_v.addLayout(sl)

        # ── MUX hint (centered, zero-height when hidden) ──────────────────
        self._mux_hint = QLabel("")
        self._mux_hint.setObjectName("note")
        self._mux_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mux_hint.setVisible(False)
        _hint_w = QWidget()
        _hint_w.setStyleSheet("background: transparent;")
        _hint_wl = QHBoxLayout(_hint_w)
        _hint_wl.setContentsMargins(0, 0, 0, 0)
        _hint_wl.addStretch(1)
        _hint_wl.addWidget(self._mux_hint)
        _hint_wl.addStretch(1)

        # ── Mode card ─────────────────────────────────────────────────────
        mc = _card()
        ml = QVBoxLayout(mc)
        ml.setContentsMargins(12, 10, 12, 10)
        ml.setSpacing(8)
        hdr = QLabel(_t("performance_mode"))
        hdr.setObjectName("h")
        ml.addWidget(hdr)
        row = QHBoxLayout()
        row.setSpacing(8)
        self._btns: dict[str, ModeButton] = {}
        for key in MODES:
            btn = ModeButton(key, _t(key))
            btn.setActive(key == self._current_mode)
            btn.clicked.connect(lambda _, m=key: self.mode_requested.emit(m))
            self._btns[key] = btn
            row.addWidget(btn)
        ml.addLayout(row)
        self._desc = QLabel(_t("desc_balanced"))
        self._desc.setObjectName("valdim")
        self._desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ml.addWidget(self._desc)

        # ── System load card ──────────────────────────────────────────────
        lc = _card()
        ll = QVBoxLayout(lc)
        ll.setContentsMargins(14, 10, 14, 10)
        ll.setSpacing(5)
        hdr2 = QLabel(_t("system"))
        hdr2.setObjectName("h")
        ll.addWidget(hdr2)
        self._cpu_bar = UsageBar("CPU", "#6c8fb0")
        self._gpu_bar = UsageBar("GPU", "#6fae8f")
        self._ram_bar = UsageBar("RAM", "#c2945a")
        ll.addWidget(self._cpu_bar)
        ll.addWidget(self._gpu_bar)
        ll.addWidget(self._ram_bar)

        # ── Fan curve card ────────────────────────────────────────────────
        fc = _card()
        fl = QVBoxLayout(fc)
        fl.setContentsMargins(14, 10, 14, 10)
        fl.setSpacing(6)
        fhdr = QHBoxLayout()
        fhdr_lbl = QLabel(_t("fan_curve"))
        fhdr_lbl.setObjectName("h")
        fhdr.addWidget(fhdr_lbl)
        fhdr.addStretch()
        self._fan_mode_lbl = QLabel("balanced")
        self._fan_mode_lbl.setStyleSheet(f"color:{theme.color('accent')};font-size:10px;")
        fhdr.addWidget(self._fan_mode_lbl)
        self._fan_ctrl_lbl = QLabel("Control: —")
        self._fan_ctrl_lbl.setObjectName("note")
        fhdr.addWidget(self._fan_ctrl_lbl)
        fl.addLayout(fhdr)
        self._chart = FanCurveChart()
        self._chart.setMinimumHeight(100)
        fl.addWidget(self._chart, 1)
        self._fan_status_lbl = QLabel("")
        self._fan_status_lbl.setObjectName("note")
        self._fan_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fl.addWidget(self._fan_status_lbl)

        # ── Splitter: top section (fixed) / fan curve (expandable) ───────
        top = QWidget()
        top.setStyleSheet("background: transparent;")
        top_l = QVBoxLayout(top)
        top_l.setContentsMargins(0, 0, 0, 0)
        top_l.setSpacing(6)
        top_l.addWidget(sc)
        top_l.addWidget(_hint_w)
        top_l.addWidget(mc)
        top_l.addWidget(lc)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(top)
        splitter.addWidget(fc)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStyleSheet(
            "QSplitter::handle { background: transparent; height: 6px; }"
        )
        root.addWidget(splitter, 1)

        self._set_curve("balanced")

    def reload_modes(self) -> None:
        self._modes = _load_modes()
        self._set_curve(self._current_mode)

    def _set_curve(self, mode: str) -> None:
        self._fan_mode_lbl.setText(mode)
        fm = self._modes.get(mode)
        if fm:
            self._chart.set_curve(mode, fm.temp_curve, fm.speed_curve, fm.idle_speed)

    def update_from_daemon(self, data: dict) -> None:
        for btn in self._btns.values():
            btn.setEnabled(True)
        cpu = data.get("cpu_temp", 0)
        gpu = data.get("gpu_temp", 0)
        f1 = data.get("fan1_pct", 0)
        f2 = data.get("fan2_pct", 0)
        self.cpu_gauge.setValue(cpu)
        self.gpu_gauge.setValue(gpu)
        temp = max(cpu, gpu)
        self._chart.set_current(temp, (f1 + f2) / 2)
        ctrl = ("BIOS (idle)" if temp < 50 else "BIOS") \
               if data.get("bios_owns_fans") else "omen-hub"
        self._fan_ctrl_lbl.setText(f"{_t('control')}: {ctrl}")
        mode = data.get("mode", self._current_mode)
        self._update_mode(mode)

    def set_offline(self) -> None:
        for btn in self._btns.values():
            btn.setEnabled(False)

    def refresh_mode_colors(self) -> None:
        for btn in self._btns.values():
            btn.refresh_color()

    def set_active_mode(self, mode: str) -> None:
        self._update_mode(mode)

    def _update_mode(self, mode: str) -> None:
        if mode == self._current_mode:
            return
        self._current_mode = mode
        for k, btn in self._btns.items():
            btn.setActive(k == mode)
        self._desc.setText(_t(f"desc_{mode}"))
        self._set_curve(mode)

    # ── GPU MUX switching ────────────────────────────────────────────────────

    def _switch_gpu(self, mode: str) -> None:
        """Initiate a background GPU mode switch."""
        if self._mux_current == mode:
            return
        # Disable both buttons while switching
        if self._mux_integrated is not None:
            self._mux_integrated.setEnabled(False)
        if self._mux_hybrid is not None:
            self._mux_hybrid.setEnabled(False)
        if self._mux_hint is not None:
            self._mux_hint.setText(_t("gpu_switching"))
            self._mux_hint.setStyleSheet(
                f"color:{theme.color('text_dim')};font-size:11px;padding:4px;"
            )
            self._mux_hint.setVisible(True)

        def _run():
            ok, err = _supergfxctl_set(mode)
            self._gpu_result.emit(mode, ok, err)

        threading.Thread(target=_run, daemon=True).start()

    def _on_gpu_switch_done(self, mode: str, ok: bool, err: str) -> None:
        """Called on the main thread when the background switch finishes."""
        if ok:
            self._mux_current = mode
            if self._mux_hint is not None:
                self._mux_hint.setText("⚠  " + _t("gpu_logout"))
                self._mux_hint.setStyleSheet(
                    "background:#f5a623; color:#1a1208; border-radius:6px;"
                    "padding:5px 12px; font-size:11px; font-weight:bold;"
                )
                self._mux_hint.setVisible(True)
        else:
            if self._mux_hint is not None:
                self._mux_hint.setText("⚠  " + (err or "error"))
                self._mux_hint.setStyleSheet(
                    f"background:{theme.color('danger')}; color:#ffffff;"
                    "border-radius:6px; padding:5px 12px; font-size:11px; font-weight:bold;"
                )
                self._mux_hint.setVisible(True)

        # Re-enable and re-highlight based on current (or newly set) mode
        if self._mux_integrated is not None:
            self._mux_integrated.setEnabled(True)
            self._mux_integrated.set_active(self._mux_current == "Integrated")
        if self._mux_hybrid is not None:
            self._mux_hybrid.setEnabled(True)
            self._mux_hybrid.set_active(self._mux_current == "Hybrid")

    def _poll(self) -> None:
        cpu, gpu = read_cpu_temp(), read_gpu_temp()
        fan1, fan2 = read_fan_rpms()
        self.cpu_gauge.setValue(cpu)
        self.gpu_gauge.setValue(gpu)
        self.fan1.setRpm(fan1)
        self.fan2.setRpm(fan2)
        if fan1 or fan2:
            self._fan_status_lbl.setText(
                f"Fan 1: {fan1} RPM   ·   Fan 2: {fan2} RPM"
            )
        self._chart.set_current(max(cpu, gpu))

        load = read_cpu_load()
        freq = read_cpu_freq()
        self._cpu_bar.update_value(load, f"{freq/1000:.1f} GHz" if freq else "")

        gs = read_gpu_stats()
        info = "  ".join(filter(None, [
            f"{gs['freq_mhz']} MHz" if gs["freq_mhz"] else "",
            f"{gs['power_w']:.0f} W" if gs["power_w"] else "",
        ]))
        self._gpu_bar.update_value(gs["load"], info)

        used, total = read_ram_usage()
        self._ram_bar.update_value(
            int(used / total * 100) if total else 0,
            f"{used:.1f} / {total:.0f} GB"
        )
