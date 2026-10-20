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

        header = QtWidgets.QLabel("MISSION DASHBOARD  |  AI Insights & Summary")
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

        # AI insights
        ai_box = QtWidgets.QGroupBox("AI Insights")
        ai_layout = QtWidgets.QVBoxLayout()
        self.ai_labels = {}
        ai_items = [
            ("Fingerprint", "Fingerprint: --"),
            ("Wind", "Wind: --"),
            ("Landing", "Landing: --"),
            ("Stability", "Stability: --%"),
            ("Recovery Health", "Recovery: --"),
            ("Faults", "Faults: --"),
        ]
        for key, default in ai_items:
            lbl = QtWidgets.QLabel(default)
            lbl.setStyleSheet("color: #8ac0d0; font-size: 14px;")
            ai_layout.addWidget(lbl)
            self.ai_labels[key] = lbl
        ai_box.setLayout(ai_layout)
        layout.addWidget(ai_box)

        layout.addStretch()

    def update(self, packet):
        # Update mission status
        self.mission_fields["TIME_STAMPING"].setText(packet.get("TIME_STAMPING", "--"))
        self.mission_fields["FLIGHT_STATE"].setText(packet.get("FLIGHT_STATE", "--"))
        self.mission_fields["ALTITUDE"].setText(f"{packet.get('ALTITUDE', 0.0):.1f} m")
        self.mission_fields["VELOCITY"].setText(f"{packet.get('VELOCITY', 0.0):.1f} m/s")
        self.mission_fields["PACKET_COUNT"].setText(str(packet.get("PACKET_COUNT", 0)))
        # Packet loss will be updated separately
        self.mission_fields["PACKET_LOSS"].setText("-- %")

    def update_ai(self, fingerprint, wind, landing, stability, recovery, faults):
        self.ai_labels["Fingerprint"].setText(f"Fingerprint: {fingerprint}")
        self.ai_labels["Wind"].setText(f"Wind: {wind}")
        self.ai_labels["Landing"].setText(f"Landing: {landing}")
        self.ai_labels["Stability"].setText(f"Stability: {stability}%")
        self.ai_labels["Recovery Health"].setText(f"Recovery: {recovery}")
        self.ai_labels["Faults"].setText(f"Faults: {faults}")

    def reset(self):
        for lbl in self.mission_fields.values():
            lbl.setText("--")
        for lbl in self.ai_labels.values():
            lbl.setText("--")