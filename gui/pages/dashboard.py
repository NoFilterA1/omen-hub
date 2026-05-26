from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGridLayout
)

from gui.widgets import TempGauge, FanRpmDisplay


def _card(parent=None) -> QFrame:
    f = QFrame(parent)
    f.setStyleSheet("""
        QFrame {
            background: #1e1e22;
            border-radius: 12px;
            padding: 4px;
        }
    """)
    return f


class DashboardPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(0, 0, 0, 0)

        # --- Temp gauges row ---
        temp_card = _card()
        temp_layout = QVBoxLayout(temp_card)

        title = QLabel("Temperatures")
        title.setStyleSheet("color:#888; font-size:11px; font-weight:bold;")
        temp_layout.addWidget(title)

        gauges_row = QHBoxLayout()
        gauges_row.setSpacing(20)

        self.cpu_gauge = TempGauge("CPU")
        self.gpu_gauge = TempGauge("GPU")
        gauges_row.addStretch()
        gauges_row.addWidget(self.cpu_gauge)
        gauges_row.addWidget(self.gpu_gauge)
        gauges_row.addStretch()
        temp_layout.addLayout(gauges_row)

        self.fan_display = FanRpmDisplay()
        self.fan_display.setMinimumHeight(44)
        temp_layout.addWidget(self.fan_display)

        root.addWidget(temp_card)

        # --- Status row ---
        status_card = _card()
        status_layout = QGridLayout(status_card)
        status_layout.setSpacing(8)

        lbl_style = "color:#888; font-size:11px;"
        val_style = "color:#ddd; font-size:13px; font-weight:bold;"

        for col, text in enumerate(["Mode", "Control", "Fan 1 %", "Fan 2 %"]):
            l = QLabel(text)
            l.setStyleSheet(lbl_style)
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status_layout.addWidget(l, 0, col)

        self.lbl_mode    = QLabel("—")
        self.lbl_control = QLabel("—")
        self.lbl_fan1    = QLabel("—")
        self.lbl_fan2    = QLabel("—")

        for col, lbl in enumerate([self.lbl_mode, self.lbl_control,
                                   self.lbl_fan1, self.lbl_fan2]):
            lbl.setStyleSheet(val_style)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status_layout.addWidget(lbl, 1, col)

        root.addWidget(status_card)
        root.addStretch()

    def update_status(self, data: dict) -> None:
        self.cpu_gauge.setValue(data.get("cpu_temp", 0))
        self.gpu_gauge.setValue(data.get("gpu_temp", 0))
        self.lbl_fan1.setText(f"{data.get('fan1_pct', 0)}%")
        self.lbl_fan2.setText(f"{data.get('fan2_pct', 0)}%")
        self.lbl_mode.setText(data.get("mode", "—").capitalize())
        self.lbl_control.setText("BIOS" if data.get("bios_owns_fans") else "omen-hub")

    def show_offline(self) -> None:
        self.cpu_gauge.setValue(0)
        self.gpu_gauge.setValue(0)
        self.lbl_mode.setText("offline")
        self.lbl_control.setText("—")
        self.lbl_fan1.setText("—")
        self.lbl_fan2.setText("—")
