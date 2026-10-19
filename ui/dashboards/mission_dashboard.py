"""
Mission Dashboard – high-level summary, AI insights, mission timeline.
"""
from PyQt5 import QtWidgets, QtCore

from .base_dashboard import BaseDashboard


class MissionDashboard(BaseDashboard):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(10)

        header = QtWidgets.QLabel("MISSION DASHBOARD  |  Mission Insights & Summary")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #88aacc;")
        layout.addWidget(header)

        # Mission status
        status_box = QtWidgets.QGroupBox("Mission Status")
        status_layout = QtWidgets.QGridLayout()
        self.mission_fields = {}
        fields = [
            ("Mission Time", "TIME_STAMPING"),
            ("Flight State", "FLIGHT_STATE"),
            ("Altitude", "ALTITUDE"),
            ("Velocity", "VELOCITY"),
            ("Packet Count", "PACKET_COUNT"),
            ("Packet Loss", "PACKET_LOSS"),
        ]
        for i, (label, key) in enumerate(fields):
            lbl = QtWidgets.QLabel(f"{label}:")
            val = QtWidgets.QLabel("--")
            val.setObjectName("value")
            val.setStyleSheet("font-size: 16px; font-weight: bold; color: #6bc9ff;")
            status_layout.addWidget(lbl, i, 0)
            status_layout.addWidget(val, i, 1)
            self.mission_fields[key] = val
        status_box.setLayout(status_layout)
        layout.addWidget(status_box)

        layout.addStretch()

    def update(self, packet):
        # Update mission status
        self.mission_fields["TIME_STAMPING"].setText(str(packet.get("TIME_STAMPING", packet.get("TIMESTAMP", "--")) or "--"))
        self.mission_fields["FLIGHT_STATE"].setText(str(packet.get("FLIGHT_STATE", "--")))
        altitude = packet.get("ALTITUDE")
        vertical_speed = packet.get("VERTICAL_SPEED")
        self.mission_fields["ALTITUDE"].setText("--" if altitude is None else f"{float(altitude):.1f} m")
        self.mission_fields["VELOCITY"].setText("--" if vertical_speed is None else f"{float(vertical_speed):.1f} m/s")
        self.mission_fields["PACKET_COUNT"].setText(str(packet.get("PACKET_COUNT", "--")))
        # Packet loss will be updated separately
        self.mission_fields["PACKET_LOSS"].setText("-- %")

    def reset(self):
        for lbl in self.mission_fields.values():
            lbl.setText("--")
