#!/usr/bin/env python3
"""
OMEN Hub GUI — main entry point.
PyQt6, works on any desktop environment.
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSlot, QLockFile
from PyQt6.QtGui import QIcon, QColor, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QStackedWidget, QSystemTrayIcon, QMenu,
    QFrame, QSizePolicy
)

from core.rgb import MODE_COLORS
from gui import theme
from gui.i18n import t as _t
from gui.ipc import StatusPoller
from gui.pages.info import InfoPage
from gui.pages.fans import FansPage
from gui.pages.system import SystemPage
from gui.pages.keyboard import KeyboardPage
from gui.pages.settings import SettingsPage

APP_NAME = "OMEN Hub"

# Visual order of the nav bar. System is first by request, but the app still
# lands on Control Center (info) at startup — see _switch_page("info") below.
NAV_PAGES = [
    ("system",   "nav_system",   "◈"),
    ("info",     "nav_info",     "⊞"),
    ("fans",     "nav_fans",     "⟳"),
    ("keyboard", "nav_keyboard", "◉"),
    ("settings", "nav_settings", "⚙"),
]


def _make_tray_icon(color: str = "#00cc66") -> QIcon:
    pm = QPixmap(22, 22)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(2, 2, 18, 18)
    p.end()
    return QIcon(pm)


class NavTab(QPushButton):
    _accent = "5566ff"  # updated globally when accent changes

    def __init__(self, icon: str, label: str):
        super().__init__(f"{icon}  {label}")
        self.setCheckable(True)
        self.setFixedHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh()

    def setChecked(self, v: bool):
        super().setChecked(v)
        self._refresh()

    def _refresh(self):
        ac = theme.shade(NavTab._accent)
        if self.isChecked():
            self.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {theme.color('text')};
                    border: none;
                    border-bottom: 2px solid {ac};
                    padding: 0 9px;
                    font-size: 11px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {theme.color('text_mute')};
                    border: none;
                    border-bottom: 2px solid transparent;
                    padding: 0 9px;
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    color: {theme.color('text_dim')};
                }}
            """)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(560, 460)
        self.resize(820, 560)
        self.setStyleSheet(theme.stylesheet())

        self._current_mode = "balanced"
        self._pending_mode: str | None = None
        self._pending_mode_until: float = 0.0

        from core.settings import get_accent
        NavTab._accent = get_accent()

        self._build_ui()
        self._build_tray()
        self._start_polling()

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header bar: title + tabs + status
        header = QFrame()
        self._header = header
        header.setFixedHeight(44)
        header.setStyleSheet(
            f"QFrame {{ background: {theme.color('bg')}; "
            f"border-bottom: 1px solid {theme.color('border')}; }}"
        )
        hl = QHBoxLayout(header)
        hl.setContentsMargins(14, 0, 14, 0)
        hl.setSpacing(0)

        self._title = QLabel(APP_NAME)
        self._title.setStyleSheet(
            f"color:{theme.shade(NavTab._accent)}; font-size:13px; font-weight:bold; margin-right:8px;"
        )
        hl.addWidget(self._title)

        self._nav_buttons: dict[str, NavTab] = {}
        for key, label_key, icon in NAV_PAGES:
            btn = NavTab(icon, _t(label_key))
            btn.clicked.connect(lambda _, k=key: self._switch_page(k))
            self._nav_buttons[key] = btn
            hl.addWidget(btn)

        hl.addStretch()

        self._status_bar = QLabel(_t("connecting"))
        self._status_bar.setStyleSheet(f"color:{theme.color('text_mute')}; font-size:10px;")
        hl.addWidget(self._status_bar)

        root.addWidget(header)

        # Content area
        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(14, 12, 14, 12)
        cl.setSpacing(8)

        self._stack = QStackedWidget()
        self._info = InfoPage()
        self._info.mode_requested.connect(self._request_mode)
        self._fans = FansPage()
        self._fans.saved.connect(self._info.reload_modes)
        self._system = SystemPage()
        self._keyboard = KeyboardPage()
        self._settings = SettingsPage()
        self._settings.colors_changed.connect(self._on_mode_colors_changed)
        self._settings.accent_changed.connect(self._on_accent_changed)
        self._settings.theme_changed.connect(self._schedule_reload)
        self._settings.language_changed.connect(self._schedule_reload)

        self._stack.addWidget(self._info)
        self._stack.addWidget(self._fans)
        self._stack.addWidget(self._system)
        self._stack.addWidget(self._keyboard)
        self._stack.addWidget(self._settings)
        cl.addWidget(self._stack)

        root.addWidget(content, 1)
        self._switch_page("info")

    def _build_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(_make_tray_icon(), self)
        menu = QMenu()
        menu.addAction("Show", self.show)
        menu.addSeparator()
        menu.addAction("Silent",      lambda: self._request_mode("silent"))
        menu.addAction("Balanced",    lambda: self._request_mode("balanced"))
        menu.addAction("Performance", lambda: self._request_mode("performance"))
        menu.addSeparator()
        menu.addAction("Quit", QApplication.quit)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._tray_clicked)
        self._tray.show()

    # ── Navigation ────────────────────────────────────────────────────────

    def _switch_page(self, key: str):
        idx = {"info": 0, "fans": 1, "system": 2, "keyboard": 3, "settings": 4}[key]
        self._page_key = key
        self._stack.setCurrentIndex(idx)
        for k, btn in self._nav_buttons.items():
            btn.setChecked(k == key)

    def _schedule_reload(self):
        # Defer so we don't delete the emitting settings widget mid-signal.
        QTimer.singleShot(0, self._reload_ui)

    def _reload_ui(self):
        page = getattr(self, "_page_key", "settings")
        self.setStyleSheet(theme.stylesheet())
        NavTab._accent = self._settings_accent()
        self._build_ui()
        self._switch_page(page)

    @staticmethod
    def _settings_accent() -> str:
        from core.settings import get_accent
        return get_accent()

    # ── Mode change ───────────────────────────────────────────────────────

    def _request_mode(self, mode: str):
        import threading

        self._current_mode = mode
        self._pending_mode = mode
        self._pending_mode_until = time.monotonic() + 5.0
        self._info.set_active_mode(mode)
        color = MODE_COLORS.get(mode, "ffffff")
        self._keyboard.apply_mode_color(mode, color)
        self._status_bar.setText(f"Mode → {mode}")
        if hasattr(self, "_tray"):
            self._tray.setIcon(_make_tray_icon(f"#{color}"))

        def _apply_mode(m: str) -> None:
            from core.power import apply_profile
            from gui.ipc import send_command
            apply_profile(m)
            send_command({"action": "set_mode", "mode": m})

        threading.Thread(target=_apply_mode, args=(mode,), daemon=True).start()

    # ── Status polling ────────────────────────────────────────────────────

    def _start_polling(self):
        self._poll_thread = QThread(self)
        self._poller = StatusPoller()
        self._poller.moveToThread(self._poll_thread)
        self._poller.status_updated.connect(self._on_status)
        self._poller.daemon_offline.connect(self._on_offline)
        self._poll_thread.start()

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(2000)
        self._poll_timer.timeout.connect(self._poller.poll)
        self._poll_timer.start()
        QTimer.singleShot(400, self._poller.poll)

    @staticmethod
    def _fmt_temp(t: int) -> str:
        from core.settings import use_fahrenheit
        return f"{int(t * 9 / 5 + 32)}°F" if use_fahrenheit() else f"{t}°C"

    @pyqtSlot(dict)
    def _on_status(self, data: dict):
        if time.monotonic() < self._pending_mode_until and self._pending_mode:
            data = {**data, "mode": self._pending_mode}
        else:
            self._pending_mode = None
            self._current_mode = data.get("mode", self._current_mode)

        self._info.update_from_daemon(data)
        mode = data.get("mode", self._current_mode)
        self._status_bar.setText(
            f"CPU {self._fmt_temp(data['cpu_temp'])}  ·  "
            f"GPU {self._fmt_temp(data['gpu_temp'])}  ·  "
            f"Fan {data['fan1_pct']}% / {data['fan2_pct']}%  ·  [{mode}]"
        )

    def _on_accent_changed(self, hex_color: str) -> None:
        NavTab._accent = hex_color
        self._title.setStyleSheet(
            f"color:{theme.shade(hex_color)}; font-size:13px; font-weight:bold; margin-right:8px;"
        )
        for btn in self._nav_buttons.values():
            btn._refresh()

    def _on_mode_colors_changed(self) -> None:
        self._info.refresh_mode_colors()
        color = MODE_COLORS.get(self._current_mode, "ffffff")
        self._keyboard.apply_mode_color(self._current_mode, color)
        if hasattr(self, "_tray"):
            self._tray.setIcon(_make_tray_icon(f"#{color}"))

    @pyqtSlot()
    def _on_offline(self):
        from gui.pages.overview import _detect_fan_controller
        self._info.set_offline()
        controller = _detect_fan_controller()
        msg = _t("daemon_offline")
        if controller == "old daemon":
            self._status_bar.setText(f"⚠  {msg}  ·  fans: old daemon active")
        else:
            self._status_bar.setText(f"⚠  {msg}  ·  fans: {controller}")

    # ── Tray ──────────────────────────────────────────────────────────────

    def _tray_clicked(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible() and not self.isMinimized():
                self.hide()
            else:
                self.show(); self.raise_(); self.activateWindow()

    def _cleanup_threads(self):
        self._poll_timer.stop()
        if self._poll_thread.isRunning():
            self._poll_thread.quit()
            self._poll_thread.wait(1000)

    def closeEvent(self, event):
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.hide(); event.ignore()
        else:
            self._cleanup_threads(); event.accept()


# ── Entry ─────────────────────────────────────────────────────────────────

def main():
    if os.environ.get("WAYLAND_DISPLAY"):
        os.environ.setdefault("QT_QPA_PLATFORM", "wayland")

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    lock = QLockFile("/tmp/omen-hub-gui.lock")
    if not lock.tryLock(100):
        sys.exit(0)

    window = MainWindow()
    window.show()
    app.aboutToQuit.connect(window._cleanup_threads)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
