from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
)

from gui.widgets import ModeButton

MODES = [
    ("silent",      "Silent"),
    ("balanced",    "Balanced"),
    ("performance", "Performance"),
]

MODE_DESC = {
    "silent":      "Quiet fans. GPU 30W. CPU power-saver.\nTemperature may rise under heavy load.",
    "balanced":    "Moderate fans. GPU 80W. CPU balanced.\nGood for everyday use.",
    "performance": "Aggressive fans. GPU 115W. CPU max.\nBest for gaming.",
}


class PerformancePage(QWidget):
    mode_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_mode: str | None = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(0, 0, 0, 0)

        # Mode buttons
        btn_card = QFrame()
        btn_card.setStyleSheet("QFrame { background:#1e1e22; border-radius:12px; }")
        btn_layout = QVBoxLayout(btn_card)

        header = QLabel("Performance Mode")
        header.setStyleSheet("color:#888; font-size:11px; font-weight:bold;")
        btn_layout.addWidget(header)

        btns_row = QHBoxLayout()
        btns_row.setSpacing(10)
        self._buttons: dict[str, ModeButton] = {}
        for mode_key, mode_label in MODES:
            btn = ModeButton(mode_key, mode_label)
            btn.clicked.connect(lambda _, m=mode_key: self.mode_requested.emit(m))
            self._buttons[mode_key] = btn
            btns_row.addWidget(btn)
        btn_layout.addLayout(btns_row)

        # Description label
        self._desc = QLabel("")
        self._desc.setStyleSheet("color:#aaa; font-size:12px;")
        self._desc.setWordWrap(True)
        self._desc.setAlignment(Qt.AlignmentFlag.AlignLeft)
        btn_layout.addWidget(self._desc)

        root.addWidget(btn_card)
        root.addStretch()

    def set_active_mode(self, mode: str) -> None:
        if mode == self._current_mode:
            return
        self._current_mode = mode
        for key, btn in self._buttons.items():
            btn.setActive(key == mode)
        self._desc.setText(MODE_DESC.get(mode, ""))
