"""
Multi-field live graph grid — one small live plot per telemetry field,
all visible at once, satisfying rule 6.1.vi ("Teams shall plot each
telemetry data field in real-time during flight").

This complements GraphEngine (graph_engine.py), which is a single large
plot with user-selectable X/Y axes — better for closely inspecting one
field, but only shows one at a time. This widget shows every field
simultaneously, grouped for readability.
"""
from PyQt5 import QtWidgets
import pyqtgraph as pg

from core.telemetry.constants import FIELD_NAMES

# Fields that aren't a numeric time-series (identifiers/strings/packed data).
_EXCLUDED = {"TEAM_ID", "GNSS_TIME", "ACCELEROMETER_DATA"}

# Derived fields added by packet.py's add_legacy_aliases() (split out of
# ACCELEROMETER_DATA), not present in FIELD_NAMES itself.
_DERIVED_FIELDS = ["ACCEL_X", "ACCEL_Y", "ACCEL_Z"]

# Grouped for a sensible reading order. Anything in FIELD_NAMES that
# isn't explicitly placed here automatically falls into "Other", so a
# newly added field never silently disappears from this view.
PRESET_GROUPS = {
    "Flight Environment": ["ALTITUDE", "PRESSURE", "TEMP", "VOLTAGE"],
    "GNSS": ["GNSS_LATITUDE", "GNSS_LONGITUDE", "GNSS_ALTITUDE", "GNSS_SATS"],
    "Attitude & Motion": [
        "ROLL", "PITCH", "YAW", "GYRO_SPIN_RATE",
        "ACCEL_X", "ACCEL_Y", "ACCEL_Z",
    ],
    "Power": ["CURRENT", "POWER"],
    "Environmental": ["HUM", "UV", "LUX"],
    "Mission": ["PACKET_COUNT", "FLIGHT_SOFTWARE_STATE", "CAM_A_STATUS"],
}


def plottable_fields():
    """FIELD_NAMES plus the derived accelerometer axes, minus non-numeric fields."""
    return [f for f in FIELD_NAMES if f not in _EXCLUDED] + _DERIVED_FIELDS


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
                plot = pg.PlotWidget(title=field)
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