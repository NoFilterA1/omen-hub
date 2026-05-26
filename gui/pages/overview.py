"""
Overview page: sensors, mode selector, system load bars, live fan curve.
"""

import os
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.sensors import (read_cpu_temp, read_gpu_temp, read_fan_rpms,
                           read_cpu_load, read_cpu_freq,
                           read_ram_usage, read_gpu_stats)
from core.fan import modes_from_config, DEFAULT_MODES
from gui import theme
from gui.i18n import t as _t
from gui.widgets import TempGauge, FanWidget, ModeButton, UsageBar, FanCurveChart

OLD_DAEMON_PID = "/tmp/omen-fand.PID"
NEW_DAEMON_SOCK = "/tmp/omen-hub.sock"

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config.toml"


def _load_fan_modes() -> dict:
    try:
        import tomlkit
        return modes_from_config(tomlkit.loads(_CONFIG_PATH.read_text()))
    except Exception:
        return dict(DEFAULT_MODES)


def _detect_fan_controller() -> str:
    if os.path.exists(NEW_DAEMON_SOCK):
        return "omen-hub"
    if os.path.exists(OLD_DAEMON_PID):
        try:
            pid = int(open(OLD_DAEMON_PID).read().strip())
            os.kill(pid, 0)
            return "old daemon"
        except PermissionError:
            return "old daemon"
        except (OSError, ValueError):
            pass
    return "BIOS"


MODES = [
    ("silent",      "silent"),
    ("balanced",    "balanced"),
    ("performance", "performance"),
]

_MODE_DESC_KEYS = {
    "silent":      "desc_silent",
    "balanced":    "desc_balanced",
    "performance": "desc_performance",
}


def _card() -> QFrame:
    f = QFrame()
    f.setObjectName("card")
    return f


class OverviewPage(QWidget):
    mode_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_mode = "balanced"
        self._daemon_online = False
        self._fan_modes = _load_fan_modes()
        self._build()

        self._local_timer = QTimer(self)
        self._local_timer.setInterval(2000)
        self._local_timer.timeout.connect(self._local_poll)
        self._local_timer.start()

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(0, 0, 0, 0)

        # ── Sensors ───────────────────────────────────────────────────────────
        sensors_card = _card()
        sl = QHBoxLayout(sensors_card)
        sl.setSpacing(0)
        sl.setContentsMargins(12, 10, 12, 10)

        self.cpu_gauge = TempGauge("CPU")
        self.gpu_gauge = TempGauge("GPU")
        self.fan1_widget = FanWidget("Fan 1")
        self.fan2_widget = FanWidget("Fan 2")

        sl.addStretch(1)
        sl.addWidget(self.cpu_gauge)
        sl.addSpacing(16)
        sl.addWidget(self.fan1_widget)
        sl.addWidget(self.fan2_widget)
        sl.addSpacing(16)
        sl.addWidget(self.gpu_gauge)
        sl.addStretch(1)
        root.addWidget(sensors_card)

        # ── Performance mode ──────────────────────────────────────────────────
        mode_card = _card()
        ml = QVBoxLayout(mode_card)
        ml.setContentsMargins(12, 10, 12, 10)
        ml.setSpacing(8)

        hdr = QLabel(_t("performance_mode"))
        hdr.setObjectName("h")
        ml.addWidget(hdr)

        btns_row = QHBoxLayout()
        btns_row.setSpacing(8)
        self._mode_buttons: dict[str, ModeButton] = {}
        for key, i18n_key in MODES:
            btn = ModeButton(key, _t(i18n_key))
            btn.clicked.connect(lambda _, m=key: self.mode_requested.emit(m))
            self._mode_buttons[key] = btn
            btns_row.addWidget(btn)
        ml.addLayout(btns_row)

        self._mode_desc = QLabel(_t("desc_balanced"))
        self._mode_desc.setObjectName("valdim")
        ml.addWidget(self._mode_desc)
        root.addWidget(mode_card)

        # ── System load ───────────────────────────────────────────────────────
        load_card = _card()
        ll = QVBoxLayout(load_card)
        ll.setContentsMargins(14, 10, 14, 10)
        ll.setSpacing(5)

        hdr2 = QLabel(_t("system"))
        hdr2.setObjectName("h")
        ll.addWidget(hdr2)

        self._cpu_bar = UsageBar("CPU", "#5566ff")
        self._gpu_bar = UsageBar("GPU", "#00cc66")
        self._ram_bar = UsageBar("RAM", "#ff9900")
        ll.addWidget(self._cpu_bar)
        ll.addWidget(self._gpu_bar)
        ll.addWidget(self._ram_bar)
        root.addWidget(load_card)

        # ── Fan curve ─────────────────────────────────────────────────────────
        curve_card = _card()
        cl = QVBoxLayout(curve_card)
        cl.setContentsMargins(14, 10, 14, 8)
        cl.setSpacing(4)

        chdr = QHBoxLayout()
        hdr3 = QLabel(_t("fan_curve"))
        hdr3.setObjectName("h")
        chdr.addWidget(hdr3)
        chdr.addStretch()
        self._fan_ctrl_lbl = QLabel(f"{_t('control')}: —")
        self._fan_ctrl_lbl.setObjectName("note")
        chdr.addWidget(self._fan_ctrl_lbl)
        cl.addLayout(chdr)

        self._fan_curve = FanCurveChart()
        cl.addWidget(self._fan_curve, 1)
        root.addWidget(curve_card, 1)

        self._update_fan_curve("balanced")

    # ── Daemon status update ──────────────────────────────────────────────────

    def update_from_daemon(self, data: dict) -> None:
        self._daemon_online = True
        cpu = data.get("cpu_temp", 0)
        gpu = data.get("gpu_temp", 0)
        self.cpu_gauge.setValue(cpu)
        self.gpu_gauge.setValue(gpu)

        f1 = data.get("fan1_pct", 0)
        f2 = data.get("fan2_pct", 0)
        self._fan_curve.set_current(max(cpu, gpu), (f1 + f2) / 2)

        ctrl = ("BIOS (idle)" if max(cpu, gpu) < 50 else "BIOS") \
               if data.get("bios_owns_fans") else "omen-hub"
        self._fan_ctrl_lbl.setText(f"{_t('control')}: {ctrl}")

        self._update_mode_ui(data.get("mode", "balanced"))

    def set_offline(self) -> None:
        self._daemon_online = False
        self._fan_ctrl_lbl.setText(f"{_t('control')}: {_detect_fan_controller()}")

    def set_active_mode(self, mode: str) -> None:
        self._update_mode_ui(mode)

    def _update_mode_ui(self, mode: str) -> None:
        if mode == self._current_mode:
            return
        self._current_mode = mode
        for key, btn in self._mode_buttons.items():
            btn.setActive(key == mode)
        self._mode_desc.setText(_t(_MODE_DESC_KEYS.get(mode, "desc_balanced")))
        self._update_fan_curve(mode)

    def _update_fan_curve(self, mode: str) -> None:
        fm = self._fan_modes.get(mode)
        if fm:
            self._fan_curve.set_curve(mode, fm.temp_curve, fm.speed_curve, fm.idle_speed)

    # ── Local sensor poll (always active) ────────────────────────────────────

    def _local_poll(self) -> None:
        cpu = read_cpu_temp()
        gpu = read_gpu_temp()
        fan1, fan2 = read_fan_rpms()

        self.cpu_gauge.setValue(cpu)
        self.gpu_gauge.setValue(gpu)
        self.fan1_widget.setRpm(fan1)
        self.fan2_widget.setRpm(fan2)

        # CPU load + freq
        cpu_load = read_cpu_load()
        cpu_freq = read_cpu_freq()
        self._cpu_bar.update_value(cpu_load,
                                   f"{cpu_freq / 1000:.1f} GHz" if cpu_freq else "")

        # GPU load + freq + power
        gs = read_gpu_stats()
        gpu_info = "  ".join(filter(None, [
            f"{gs['freq_mhz']} MHz" if gs["freq_mhz"] else "",
            f"{gs['power_w']:.0f} W" if gs["power_w"] else "",
        ]))
        self._gpu_bar.update_value(gs["load"], gpu_info)

        # RAM
        used, total = read_ram_usage()
        ram_pct = int(used / total * 100) if total else 0
        self._ram_bar.update_value(ram_pct, f"{used:.1f} / {total:.0f} GB")

        if not self._daemon_online:
            self._fan_ctrl_lbl.setText(f"{_t('control')}: {_detect_fan_controller()}")
