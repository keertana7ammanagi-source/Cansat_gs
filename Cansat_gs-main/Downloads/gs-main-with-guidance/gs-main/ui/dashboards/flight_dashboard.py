"""
Flight Dashboard – 6-DOF attitude (Roll, Pitch, Yaw), velocity, acceleration, descent rate.
"""
from PyQt5 import QtWidgets, QtCore

from .base_dashboard import BaseDashboard


class FlightDashboard(BaseDashboard):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(10)

        header = QtWidgets.QLabel("FLIGHT DASHBOARD  |  6-DOF Attitude & Dynamics")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #88aacc;")
        layout.addWidget(header)

        grid = QtWidgets.QGridLayout()
        grid.setSpacing(12)

        # Define fields: (label, key, unit, row, col)
        fields = [
            ("Roll", "GYRO_R", "°", 0, 0),
            ("Pitch", "GYRO_P", "°", 0, 1),
            ("Yaw", "GYRO_Y", "°", 0, 2),
            ("Acceleration X", "ACCEL_R", "m/s²", 1, 0),
            ("Acceleration Y", "ACCEL_P", "m/s²", 1, 1),
            ("Acceleration Z", "ACCEL_Y", "m/s²", 1, 2),
            ("Velocity", "VELOCITY", "m/s", 2, 0),
            ("Descent Rate", "DESCENT_RATE", "m/s", 2, 1),
            ("Altitude", "ALTITUDE", "m", 2, 2),
        ]
        self.flight_labels = {}
        for label, key, unit, row, col in fields:
            group = QtWidgets.QGroupBox(label)
            vbox = QtWidgets.QVBoxLayout(group)
            val = QtWidgets.QLabel("--")
            val.setObjectName("value")
            val.setStyleSheet("font-size: 22px; font-weight: bold; color: #6bc9ff;")
            unit_lbl = QtWidgets.QLabel(unit)
            unit_lbl.setStyleSheet("font-size: 14px; color: #8a9aaa;")
            vbox.addWidget(val)
            vbox.addWidget(unit_lbl)
            grid.addWidget(group, row, col)
            self.flight_labels[key] = val

        layout.addLayout(grid)

        # Additional status
        self.state_label = QtWidgets.QLabel("Flight State: --")
        self.state_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #88ddff;")
        layout.addWidget(self.state_label)

        layout.addStretch()

    def update(self, packet):
        # Update values from packet
        mapping = {
            "GYRO_R": packet.get("GYRO_R", 0.0),
            "GYRO_P": packet.get("GYRO_P", 0.0),
            "GYRO_Y": packet.get("GYRO_Y", 0.0),
            "ACCEL_R": packet.get("ACCEL_R", 0.0),
            "ACCEL_P": packet.get("ACCEL_P", 0.0),
            "ACCEL_Y": packet.get("ACCEL_Y", 0.0),
            "VELOCITY": packet.get("VELOCITY", 0.0),
            "DESCENT_RATE": packet.get("DESCENT_RATE", 0.0),  # we may compute from altitude delta
            "ALTITUDE": packet.get("ALTITUDE", 0.0),
        }
        for key, value in mapping.items():
            if key in self.flight_labels:
                self.flight_labels[key].setText(f"{value:.2f}")

        state = packet.get("FLIGHT_STATE", "--")
        self.state_label.setText(f"Flight State: {state}")

    def reset(self):
        for lbl in self.flight_labels.values():
            lbl.setText("--")
        self.state_label.setText("Flight State: --")