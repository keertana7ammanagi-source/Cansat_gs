"""
Sensor Dashboard – overview of all sensors: status, online/offline, health.

Status for each sensor is derived from the actual fields in the current
24-field telemetry packet (see core/telemetry/constants.py), not
hardcoded. A sensor group turns:
  - GRAY  "NO DATA"      before the first packet ever arrives
  - RED   "NO SIGNAL"     if no packet has arrived in SIGNAL_TIMEOUT_MS
  - RED   "OFFLINE"       if its field(s) are missing from the packet
  - AMBER "OUT OF RANGE"  if its value(s) are outside a plausible range
  - GREEN "ONLINE | HEALTHY" otherwise
"""
from PyQt5 import QtWidgets, QtCore

from .base_dashboard import BaseDashboard

SIGNAL_TIMEOUT_MS = 3000  # telemetry is 1 Hz; 3 missed packets = signal lost

COLOR_OK      = "#60c090"
COLOR_WARN    = "#e0b34d"
COLOR_OFFLINE = "#d9534f"
COLOR_NODATA  = "#8a9aaa"

# Each entry: (display name, dashboard key, [(field, lo, hi), ...])
# lo/hi are plausible physical bounds used only for a sanity check -- not
# calibration limits.
SENSORS = [
    ("BMP581 (Pressure/Alt)", "BMP581", [
        ("PRESSURE", 20000, 110000),
        ("ALTITUDE", -50, 5000),
    ]),
    ("SHT40 (Temp/Humidity)", "SHT40", [
        ("TEMP", -40, 85),
        ("HUM", 0, 100),
    ]),
    ("LTR390 (UV/Lux)", "LTR390", [
        ("UV", 0, 20),
        ("LUX", 0, 100000),
    ]),
    ("GNSS", "GNSS", [
        ("GNSS_SATS", 0, 32),
    ]),
    ("BNO085 (Roll/Pitch/Yaw)", "BNO085", [
        ("ROLL", -180, 180),
        ("PITCH", -180, 180),
        ("YAW", -360, 360),
    ]),
    ("Accelerometer", "ACCEL", [
        ("ACCEL_X", -160, 160),
        ("ACCEL_Y", -160, 160),
        ("ACCEL_Z", -160, 160),
    ]),
    ("INA219 (Power)", "INA219", [
        ("CURRENT", 0, 3000),
        ("POWER", 0, 15000),
    ]),
    ("Hall Sensor (Gyro Spin)", "HALL", [
        ("GYRO_SPIN_RATE", -720, 720),
    ]),
    ("ESP32-CAM A", "CAM_A", [
        ("CAM_A_STATUS", 1, 1),
    ]),
]


class SensorDashboard(BaseDashboard):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._last_packet_time = None

        self._signal_timer = QtCore.QTimer(self)
        self._signal_timer.setInterval(500)
        self._signal_timer.timeout.connect(self._check_signal)
        self._signal_timer.start()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(10)

        header = QtWidgets.QLabel("SENSOR DASHBOARD  |  Status & Health")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #88aacc;")
        layout.addWidget(header)

        grid = QtWidgets.QGridLayout()
        grid.setSpacing(10)
        self.sensor_labels = {}

        for i, (name, key, _fields) in enumerate(SENSORS):
            row = i // 3
            col = i % 3
            group = QtWidgets.QGroupBox(name)
            vbox = QtWidgets.QVBoxLayout(group)
            status = QtWidgets.QLabel("⚪ NO DATA")
            status.setStyleSheet(f"font-size: 14px; color: {COLOR_NODATA};")
            vbox.addWidget(status)
            grid.addWidget(group, row, col)
            self.sensor_labels[key] = status

        layout.addLayout(grid)
        layout.addStretch()

    def _set_status(self, key, symbol, text, color):
        lbl = self.sensor_labels[key]
        lbl.setText(f"{symbol} {text}")
        lbl.setStyleSheet(f"color: {color}; font-size: 14px;")

    def _check_signal(self):
        """If no packet has arrived recently, mark every sensor as lost signal."""
        if self._last_packet_time is None:
            return
        elapsed = self._last_packet_time.msecsTo(QtCore.QTime.currentTime())
        if elapsed > SIGNAL_TIMEOUT_MS or elapsed < 0:
            for _, key, _ in SENSORS:
                self._set_status(key, "🔴", "NO SIGNAL", COLOR_OFFLINE)

    def update(self, packet):
        self._last_packet_time = QtCore.QTime.currentTime()

        for _name, key, fields in SENSORS:
            missing = [f for f, _lo, _hi in fields if packet.get(f) is None]
            if missing:
                self._set_status(key, "🔴", "OFFLINE", COLOR_OFFLINE)
                continue

            out_of_range = []
            for field, lo, hi in fields:
                value = packet.get(field)
                try:
                    if not (lo <= float(value) <= hi):
                        out_of_range.append(field)
                except (TypeError, ValueError):
                    out_of_range.append(field)

            if out_of_range:
                self._set_status(
                    key, "🟡", f"OUT OF RANGE ({', '.join(out_of_range)})", COLOR_WARN
                )
            else:
                self._set_status(key, "🟢", "ONLINE | HEALTHY", COLOR_OK)

    def reset(self):
        self._last_packet_time = None
        for _, key, _fields in SENSORS:
            self._set_status(key, "⚪", "NO DATA", COLOR_NODATA)