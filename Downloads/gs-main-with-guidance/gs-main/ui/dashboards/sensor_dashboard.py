"""
Sensor Dashboard – overview of all sensors: status, online/offline, health, sample rate.
"""
from PyQt5 import QtWidgets, QtCore

from .base_dashboard import BaseDashboard


class SensorDashboard(BaseDashboard):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(10)

        header = QtWidgets.QLabel("SENSOR DASHBOARD  |  Status & Health")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #88aacc;")
        layout.addWidget(header)

        # Define sensors: (name, key for status, sample rate)
        sensors = [
            ("BMP581 (Pressure)", "BMP581", "1 Hz"),
            ("SHT40 (Temp/Hum)", "SHT40", "1 Hz"),
            ("LTR390 (UV)", "LTR390", "1 Hz"),
            ("VEML7700 (Light)", "VEML7700", "1 Hz"),
            ("GPS/NavIC", "GPS", "1 Hz"),
            ("BNO085 (IMU)", "BNO085", "50 Hz"),
            ("INA219 (Power)", "INA219", "1 Hz"),
            ("Hall Sensor (RPM)", "HALL", "1 Hz"),
            ("DS3231 (RTC)", "RTC", "1 Hz"),
        ]

        grid = QtWidgets.QGridLayout()
        grid.setSpacing(10)
        self.sensor_labels = {}

        for i, (name, key, rate) in enumerate(sensors):
            row = i // 3
            col = i % 3
            group = QtWidgets.QGroupBox(name)
            vbox = QtWidgets.QVBoxLayout(group)
            status = QtWidgets.QLabel("🟢 ONLINE | HEALTHY")
            status.setStyleSheet("font-size: 14px; color: #60c090;")
            sample_rate = QtWidgets.QLabel(f"Sample Rate: {rate}")
            sample_rate.setStyleSheet("font-size: 12px; color: #8a9aaa;")
            vbox.addWidget(status)
            vbox.addWidget(sample_rate)
            grid.addWidget(group, row, col)
            self.sensor_labels[key] = status

        layout.addLayout(grid)
        layout.addStretch()

    def update(self, packet):
        # For now, just set all to healthy; we can detect sensor presence from packet fields.
        # In a full implementation, we'd check if the field exists and has valid data.
        # For demo, set all green.
        for key, lbl in self.sensor_labels.items():
            lbl.setText("🟢 ONLINE | HEALTHY")
            lbl.setStyleSheet("color: #60c090; font-size: 14px;")

    def reset(self):
        pass