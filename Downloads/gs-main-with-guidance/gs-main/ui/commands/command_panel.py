"""
Command Panel – Mission control buttons.

Only buttons for commands the flight firmware (firmware/flight_transmitter.ino
handleCommand()) actually understands. The panel used to also send
CAL_IMU, CAL_PRES, RESET_GPS, BEACON_ON, BEACON_OFF, RESET_TIME, LOG_ON,
LOG_OFF and GEN_REPORT -- none of which the firmware recognizes, and none
of which had any local handling either, so they silently did nothing.
Logging always runs whenever a valid packet is received (see
core/data/csv_logger.py); use the "Reports" tab to generate the PDF/CSV
mission report.

Precision-landing guidance commands (HOVER / GLIDE_LEFT / GLIDE_RIGHT)
live on the "Guidance" tab (ui/dashboards/guidance_dashboard.py), not
here, so they aren't duplicated.
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

        note = QtWidgets.QLabel(
            "Guidance commands (Hover / Glide) are on the Guidance tab.\n"
            "Mission reports are generated on the Reports tab."
        )
        note.setStyleSheet("font-size: 11px; color: #6a8aaa;")
        layout.addWidget(note)

        # Grid of buttons
        grid = QtWidgets.QGridLayout()
        grid.setSpacing(10)

        # Define buttons: (text, command, row, col)
        # Every command here MUST have a matching branch in
        # firmware/flight_transmitter.ino's handleCommand().
        buttons = [
            ("Start Telemetry", CMD_TELEMETRY_ON, 0, 0),
            ("Stop Telemetry", CMD_TELEMETRY_OFF, 0, 1),
            ("Calibrate (Gyro/Baro/Accel)", CMD_CALIBRATE, 1, 0),
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