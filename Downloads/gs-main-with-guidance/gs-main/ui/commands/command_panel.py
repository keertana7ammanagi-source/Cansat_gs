"""
Command Panel – Mission control buttons.
"""
from PyQt5 import QtWidgets, QtCore

from core.telemetry.constants import (
    CMD_TELEMETRY_ON, CMD_TELEMETRY_OFF, CMD_CALIBRATE
)
from utils.logger import get_logger

logger = get_logger(__name__)


class CommandPanel(QtWidgets.QWidget):
    def __init__(self, parent=None, send_command_callback=None):
        super().__init__(parent)
        self.send_command = send_command_callback
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(12)

        title = QtWidgets.QLabel("COMMAND PANEL")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #88aacc;")
        layout.addWidget(title)

        # Grid of buttons
        grid = QtWidgets.QGridLayout()
        grid.setSpacing(10)

        # Define buttons: (text, command, row, col)
        buttons = [
            ("Start Telemetry", CMD_TELEMETRY_ON, 0, 0),
            ("Stop Telemetry", CMD_TELEMETRY_OFF, 0, 1),
            ("Calibrate IMU", "CAL_IMU", 1, 0),
            ("Calibrate Pressure", "CAL_PRES", 1, 1),
            ("Reset GPS", "RESET_GPS", 2, 0),
            ("Beacon ON", "BEACON_ON", 2, 1),
            ("Beacon OFF", "BEACON_OFF", 3, 0),
            ("Reset Mission Time", "RESET_TIME", 3, 1),
            ("Start Logging", "LOG_ON", 4, 0),
            ("Stop Logging", "LOG_OFF", 4, 1),
            ("Generate Report", "GEN_REPORT", 5, 0),
        ]

        for text, cmd, row, col in buttons:
            btn = QtWidgets.QPushButton(text)
            btn.setStyleSheet("font-size: 14px; padding: 10px; min-width: 120px;")
            btn.clicked.connect(lambda checked, c=cmd: self._on_command(c))
            grid.addWidget(btn, row, col)

        layout.addLayout(grid)

        # Status log area (optional)
        self.log_text = QtWidgets.QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(100)
        self.log_text.setStyleSheet("background: #0a1016; color: #8ac0d0; font-family: monospace;")
        self.log_text.append("Command log:")
        layout.addWidget(self.log_text)

        layout.addStretch()

    def _on_command(self, cmd):
        if self.send_command:
            self.send_command(cmd)
            self.log_text.append(f"> Sent: {cmd}")
            logger.info(f"Command sent: {cmd}")
        else:
            QtWidgets.QMessageBox.warning(self, "No callback", "No command handler set.")