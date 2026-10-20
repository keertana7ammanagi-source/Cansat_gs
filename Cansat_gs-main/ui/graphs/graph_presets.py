"""
Multi-field live graph grid — one small live plot per telemetry field,
all visible at once, satisfying rule 6.1.x ("Teams shall plot each
telemetry data field in real-time during flight").

This complements GraphEngine (graph_engine.py), which is a single large
plot with user-selectable X/Y axes — better for closely inspecting one
field, but only shows one at a time. This widget shows every field
simultaneously, grouped for readability.
"""
from PyQt5 import QtWidgets
import pyqtgraph as pg

from core.telemetry.constants import FIELD_NAMES

# Fields that aren't a numeric time-series (identifiers and GNSS time string).
_EXCLUDED = {"TEAM_ID", "GNSS_TIME", "ACCELEROMETER_DATA"}

# Grouped for a sensible reading order. Anything in FIELD_NAMES that
# isn't explicitly placed here automatically falls into "Other", so a
# newly added field never silently disappears from this view.
PRESET_GROUPS = {
    "Flight Environment": ["ALTITUDE", "PRESSURE", "TEMP", "VOLTAGE"],
    "GNSS": ["GNSS_LATITUDE", "GNSS_LONGITUDE", "GNSS_ALTITUDE", "GNSS_SATS", "GNSS_HDOP", "GNSS_FIX"],
    "Attitude & Motion": [
        "ROLL", "PITCH", "YAW", "GYRO_X", "GYRO_Y", "GYRO_Z",
        "MAG_X", "MAG_Y", "MAG_Z", "VERTICAL_SPEED", "GNSS_GROUND_SPEED", "GNSS_COURSE",
        "ACCEL_X", "ACCEL_Y", "ACCEL_Z",
    ],
    "Power": ["CURRENT", "POWER"],
    "Environmental": ["HUMIDITY", "UV_INDEX", "LIGHT_LUX"],
    "Mission": ["PACKET_COUNT", "FLIGHT_SOFTWARE_STATE"],
    "Derived & Payload": ["TIMESTAMP", "REL_ALTITUDE", "HALL_RPM"],
}

# Display-only conversions. The logged wire values remain in their source
# units (Pa, mA, mW), while plot axes use the requested human-readable units.
PLOT_DIVISORS = {"PRESSURE": 100.0, "CURRENT": 1000.0, "POWER": 1000.0}
PLOT_UNITS = {
    "ALTITUDE": "m", "PRESSURE": "hPa", "TEMP": "°C", "VOLTAGE": "V",
    "GNSS_LATITUDE": "°", "GNSS_LONGITUDE": "°", "GNSS_ALTITUDE": "m",
    "GNSS_SATS": "sat", "GNSS_HDOP": "", "GNSS_FIX": "", "ROLL": "°",
    "PITCH": "°", "YAW": "°", "GYRO_X": "deg/s", "GYRO_Y": "deg/s",
    "GYRO_Z": "deg/s", "ACCEL_X": "m/s²", "ACCEL_Y": "m/s²",
    "ACCEL_Z": "m/s²", "MAG_X": "µT", "MAG_Y": "µT", "MAG_Z": "µT",
    "CURRENT": "A", "POWER": "W", "HUMIDITY": "%", "UV_INDEX": "index",
    "LIGHT_LUX": "lx", "HALL_RPM": "rpm", "VERTICAL_SPEED": "m/s",
    "GNSS_GROUND_SPEED": "m/s", "GNSS_COURSE": "°", "TIMESTAMP": "s",
    "REL_ALTITUDE": "m", "PACKET_COUNT": "packet",
    "FLIGHT_SOFTWARE_STATE": "state",
}


def plottable_fields():
    """All numeric schema fields, excluding identifiers and the GNSS time string."""
    return [f for f in FIELD_NAMES if f not in _EXCLUDED]


def ordered_groups():
    """PRESET_GROUPS plus an 'Other' bucket for anything not explicitly grouped."""
    grouped = {f for fields in PRESET_GROUPS.values() for f in fields}
    groups = dict(PRESET_GROUPS)
    leftover = [f for f in plottable_fields() if f not in grouped]
    if leftover:
        groups["Other"] = leftover
    return groups


class MultiFieldGraphGrid(QtWidgets.QWidget):
    """A small live plot per telemetry field, grouped under section headers."""

    def __init__(self, parent=None, buffer_size=300, columns=3):
        super().__init__(parent)
        self.buffer_size = buffer_size
        self.columns = columns
        self.data = {field: [] for field in plottable_fields()}
        self.curves = {}
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(14)

        header = QtWidgets.QLabel("ALL FIELDS  |  Live Overview")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #88aacc;")
        layout.addWidget(header)

        for group_name, fields in ordered_groups().items():
            section = QtWidgets.QLabel(group_name)
            section.setStyleSheet("font-size: 14px; font-weight: bold; color: #88aacc;")
            layout.addWidget(section)

            grid = QtWidgets.QGridLayout()
            grid.setSpacing(8)
            for i, field in enumerate(fields):
                row, col = divmod(i, self.columns)
                unit = PLOT_UNITS.get(field, "")
                plot = pg.PlotWidget(title=f"{field} ({unit})" if unit else field)
                plot.setBackground('#101a24')
                plot.showGrid(x=True, y=True, alpha=0.15)
                plot.setMinimumHeight(140)
                plot.getAxis('left').setTextPen('w')
                plot.getAxis('bottom').setTextPen('w')
                curve = plot.plot(pen='y')
                self.curves[field] = curve
                grid.addWidget(plot, row, col)
            layout.addLayout(grid)

        layout.addStretch()

    def update(self, packet):
        for field in self.data:
            value = packet.get(field)
            if value is None:
                continue
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            value /= PLOT_DIVISORS.get(field, 1.0)
            buf = self.data[field]
            buf.append(value)
            if len(buf) > self.buffer_size:
                buf.pop(0)
            curve = self.curves.get(field)
            if curve is not None:
                curve.setData(buf)

    def reset(self):
        for field in self.data:
            self.data[field] = []
            curve = self.curves.get(field)
            if curve is not None:
                curve.clear()
