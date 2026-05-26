"""System page: static hardware information + GPU mode switching."""

import glob
import subprocess
import sys
import threading
from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGridLayout, QPushButton,
    QMessageBox
)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.sensors import read_system_info
from gui.i18n import t as _t
import gui.theme as _theme


def _read_uptime() -> str:
    try:
        secs = float(open("/proc/uptime").read().split()[0])
        h, m = int(secs // 3600), int((secs % 3600) // 60)
        return f"{h}h {m}m" if h else f"{m}m"
    except OSError:
        return "—"


def _read_battery() -> str:
    for path in glob.glob("/sys/class/power_supply/BAT*/"):
        try:
            cap    = open(path + "capacity").read().strip()
            status = open(path + "status").read().strip()
            return f"{cap}%  ({status})"
        except OSError:
            continue
    return "—"


def _supergfxctl_mode() -> str | None:
    """Return current GPU mode string, or None if supergfxctl unavailable."""
    try:
        out = subprocess.run(
            ["supergfxctl", "-g"],
            capture_output=True, text=True, timeout=2,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def _supergfxctl_set(mode: str) -> tuple[bool, str]:
    """Switch GPU mode via PolicyKit (graphical auth, works without a tty).

    A GUI has no controlling terminal, so plain `sudo` can't prompt and the
    switch silently fails. pkexec pops a graphical auth dialog instead; if it's
    missing we fall back to non-interactive sudo (in case a NOPASSWD rule exists).
    """
    try:
        out = subprocess.run(
            ["pkexec", "supergfxctl", "-m", mode],
            capture_output=True, text=True, timeout=60,
        )
        if out.returncode == 0:
            return True, ""
        if out.returncode == 126:
            return False, "authorization cancelled"
        if out.returncode == 127:
            return False, "PolicyKit not configured (install polkit + auth agent)"
        return False, (out.stderr or out.stdout).strip() or f"pkexec exit {out.returncode}"
    except FileNotFoundError:
        # pkexec absent — try a passwordless sudo rule, else explain.
        try:
            out = subprocess.run(
                ["sudo", "-n", "supergfxctl", "-m", mode],
                capture_output=True, text=True, timeout=10,
            )
            if out.returncode == 0:
                return True, ""
            return False, ("need a PolicyKit agent or a sudoers NOPASSWD rule "
                           "for supergfxctl")
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
            return False, str(e)
    except (subprocess.TimeoutExpired, OSError) as e:
        return False, str(e)


def _card(title: str = "") -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("card")
    cl = QVBoxLayout(f)
    cl.setContentsMargins(16, 12, 16, 14)
    cl.setSpacing(8)
    if title:
        hdr = QLabel(title)
        hdr.setObjectName("h")
        cl.addWidget(hdr)
    return f, cl


def _row(grid: QGridLayout, idx: int, label: str, value: str) -> None:
    lbl = QLabel(label)
    lbl.setObjectName("valdim")
    lbl.setMinimumWidth(90)
    val = QLabel(value)
    val.setObjectName("val")
    val.setWordWrap(True)
    grid.addWidget(lbl, idx, 0)
    grid.addWidget(val, idx, 1)


def _gpu_btn_style(active: bool) -> str:
    """Flat underline-accent style for GPU mode buttons; no flood fill."""
    ac = _theme.color("accent")
    dim = _theme.color("text_mute")
    text = _theme.color("text_dim")
    if active:
        return (
            f"QPushButton{{background:transparent;color:{ac};"
            f"border:none;border-bottom:2px solid {ac};"
            f"border-radius:0px;padding:4px 14px;font-size:12px;font-weight:bold;}}"
        )
    return (
        f"QPushButton{{background:transparent;color:{dim};"
        f"border:none;border-bottom:2px solid transparent;"
        f"border-radius:0px;padding:4px 14px;font-size:12px;}}"
        f"QPushButton:hover{{color:{text};border-bottom:2px solid {dim};}}"
    )


class SystemPage(QWidget):
    _gpu_result = pyqtSignal(str, bool, str)  # mode, ok, err

    def __init__(self, parent=None):
        super().__init__(parent)
        self._info = read_system_info()
        self._gpu_mode = _supergfxctl_mode()
        self._gpu_result.connect(self._on_gpu_switch_done)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(0, 0, 0, 0)

        # Hardware card
        hw_card, hw_layout = _card(_t("hw_hardware"))
        grid = QGridLayout()
        grid.setSpacing(7)
        grid.setColumnStretch(1, 1)

        hw_rows = [
            (_t("hw_product"),  self._info.get("product", "—")),
            (_t("hw_cpu"),      self._info.get("cpu", "—")),
            (_t("hw_gpu"),      self._info.get("gpu", "—")),
            (_t("hw_ram"),      self._info.get("ram", "—")),
            (_t("hw_disk"),     self._info.get("disk", "—")),
            (_t("hw_uptime"),   _read_uptime()),
            (_t("hw_battery"),  _read_battery()),
        ]
        for i, (lbl, val) in enumerate(hw_rows):
            _row(grid, i, lbl, val)

        hw_layout.addLayout(grid)
        root.addWidget(hw_card)

        # GPU Mode card (only when supergfxctl is available)
        if self._gpu_mode is not None:
            gm_card, gm_layout = _card(_t("gpu_mode"))

            cur_row = QHBoxLayout()
            cur_row.setSpacing(6)
            self._gpu_mode_lbl = QLabel(f"{_t('gpu_active')}  {self._gpu_mode}")
            self._gpu_mode_lbl.setObjectName("val")
            cur_row.addWidget(self._gpu_mode_lbl)
            cur_row.addStretch()
            gm_layout.addLayout(cur_row)

            btn_row = QHBoxLayout()
            btn_row.setSpacing(6)
            self._gpu_btns: dict[str, QPushButton] = {}
            for mode_key, mode_val in (
                ("mux_hybrid", "Hybrid"),
                ("mux_integrated", "Integrated"),
            ):
                active = self._gpu_mode == mode_val
                btn = QPushButton(_t(mode_key))
                btn.setEnabled(not active)
                btn.setStyleSheet(_gpu_btn_style(active))
                btn.clicked.connect(lambda _, m=mode_val: self._switch_gpu(m))
                self._gpu_btns[mode_val] = btn
                btn_row.addWidget(btn)
            btn_row.addStretch()
            gm_layout.addLayout(btn_row)

            warn = QLabel(_t("gpu_logout_warn"))
            warn.setObjectName("note")
            gm_layout.addWidget(warn)

            self._gpu_status = QLabel("")
            self._gpu_status.setObjectName("note")
            gm_layout.addWidget(self._gpu_status)

            root.addWidget(gm_card)

        # Software card
        sw_card, sw_layout = _card(_t("hw_software"))
        sgrid = QGridLayout()
        sgrid.setSpacing(7)
        sgrid.setColumnStretch(1, 1)

        sw_rows = [
            (_t("hw_os"),     self._info.get("os", "—")),
            (_t("hw_kernel"), self._info.get("kernel", "—")),
            (_t("hw_arch"),   self._info.get("arch", "—")),
        ]
        for i, (lbl, val) in enumerate(sw_rows):
            _row(sgrid, i, lbl, val)

        sw_layout.addLayout(sgrid)
        root.addWidget(sw_card)

        root.addStretch()

    def _switch_gpu(self, mode: str) -> None:
        msg = QMessageBox(self)
        msg.setWindowTitle(_t("gpu_switch_title"))
        msg.setText(_t("gpu_switch_body").format(mode=f"<b>{mode}</b>"))
        msg.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        if msg.exec() != QMessageBox.StandardButton.Ok:
            return

        for btn in self._gpu_btns.values():
            btn.setEnabled(False)
        # dynamic status — intentionally inline (grey "in-progress" color)
        self._gpu_status.setText(_t("gpu_switching"))
        self._gpu_status.setStyleSheet("color:#888;font-size:10px;")

        def _run():
            ok, err = _supergfxctl_set(mode)
            self._gpu_result.emit(mode, ok, err)

        threading.Thread(target=_run, daemon=True).start()

    def _on_gpu_switch_done(self, mode: str, ok: bool, err: str) -> None:
        if ok:
            self._gpu_mode = mode
            self._gpu_mode_lbl.setText(
                f"{_t('gpu_active')}  {mode}  ({_t('gpu_logout')})"
            )
            # dynamic status — intentionally inline (success green)
            self._gpu_status.setText(_t("gpu_done"))
            self._gpu_status.setStyleSheet("color:#44cc88;font-size:10px;")
        else:
            # dynamic status — intentionally inline (error red)
            self._gpu_status.setText(f"{_t('gpu_failed')}: {err or _t('gpu_unknown_error')}")
            self._gpu_status.setStyleSheet("color:#ff6655;font-size:10px;")
        for m, btn in self._gpu_btns.items():
            active = self._gpu_mode == m
            btn.setEnabled(not active)
            btn.setStyleSheet(_gpu_btn_style(active))
