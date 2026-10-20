"""
Telemetry Dashboard – live telemetry values, GPS, LoRa, and plots.
"""
from PyQt5 import QtWidgets, QtCore
import pyqtgraph as pg

from .base_dashboard import BaseDashboard


class TelemetryDashboard(BaseDashboard):
    def __init__(self, parent=None, buffer_size=300):
        super().__init__(parent)
        self.buffer_size = buffer_size
        self.t_buf = []
        self.alt_buf = []
        self.press_buf = []
        self.temp_buf = []
        self.vel_buf = []
        self.prev_alt = None

        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # Left panel: telemetry values, GPS, LoRa
        left = QtWidgets.QVBoxLayout()
        left.setContentsMargins(4, 4, 4, 4)
        left.setSpacing(8)

        # LIVE TELEMETRY
        tele_box = QtWidgets.QGroupBox("LIVE TELEMETRY")
        tele_layout = QtWidgets.QGridLayout()
        tele_layout.setSpacing(10)  # add this after tele_layout = QtWidgets.QGridLayout()
        self.tel_labels = {}
        fields = [
            ("Altitude", "ALTITUDE", "m", 0),
            ("Vertical Velocity", "VELOCITY", "m/s", 1),
            ("Pressure", "PRESSURE", "hPa", 2),
            ("Temperature", "TEMP", "°C", 3),
            ("Humidity", "HUMIDITY", "%", 4),
            ("Current", "CURRENT", "A", 5),
            ("Power", "POWER", "W", 6),
            ("GPS Sats", "GNSS_SATS", "", 7),
            ("Flight State", "FLIGHT_STATE", "", 8),
            ("Mission Time", "TIME_STAMPING", "", 9),
        ]
        for i, (label, key, unit, row) in enumerate(fields):
            lbl = QtWidgets.QLabel(f"{label}:")
            val = QtWidgets.QLabel("--")
            val.setObjectName("value")
            unit_lbl = QtWidgets.QLabel(unit)
            tele_layout.addWidget(lbl, row, 0)
            tele_layout.addWidget(val, row, 1)
            tele_layout.addWidget(unit_lbl, row, 2)
            self.tel_labels[key] = val
        tele_box.setLayout(tele_layout)
        left.addWidget(tele_box)

        # GPS
        gps_box = QtWidgets.QGroupBox("GPS INFORMATION")
        gps_layout = QtWidgets.QGridLayout()
        gps_layout.setSpacing(10)

        self.gps_labels = {}
        gps_fields = [
            ("Latitude", "GNSS_LATITUDE", "°N"),
            ("Longitude", "GNSS_LONGITUDE", "°E"),
            ("GNSS Altitude", "GNSS_ALTITUDE", "m"),
            ("Satellites", "GNSS_SATS", ""),
            ("HDOP", "HDOP", ""),
            ("Fix Type", "FIX_TYPE", ""),
        ]
        for i, (label, key, unit) in enumerate(gps_fields):
            lbl = QtWidgets.QLabel(f"{label}:")
            val = QtWidgets.QLabel("--")
            val.setObjectName("value")
            unit_lbl = QtWidgets.QLabel(unit)
            gps_layout.addWidget(lbl, i, 0)
            gps_layout.addWidget(val, i, 1)
            gps_layout.addWidget(unit_lbl, i, 2)
            self.gps_labels[key] = val
        self.gps_labels["HDOP"] = QtWidgets.QLabel("--")
        self.gps_labels["FIX_TYPE"] = QtWidgets.QLabel("--")
        gps_box.setLayout(gps_layout)
        left.addWidget(gps_box)

        # LoRa
        lora_box = QtWidgets.QGroupBox("LORA LINK STATUS")
        lora_layout = QtWidgets.QGridLayout()
        lora_layout.setSpacing(10)

        self.lora_labels = {}
        lora_fields = [
            ("Frequency", "868 MHz", 0),
            ("RSSI", "RSSI", 1),
            ("SNR", "SNR", 2),
            ("Spreading Factor", "SF", 3),
            ("Bandwidth", "BW", 4),
            ("Packet Size", "PKT_SIZE", 5),
            ("Packet Loss", "PACKET_LOSS", 6),
            ("Source Rate", "SRC_RATE", 7),
        ]
        for i, (label, key, row) in enumerate(lora_fields):
            lbl = QtWidgets.QLabel(f"{label}:")
            val = QtWidgets.QLabel("--")
            val.setObjectName("value")
            lora_layout.addWidget(lbl, row, 0)
            lora_layout.addWidget(val, row, 1)
            self.lora_labels[key] = val
        lora_box.setLayout(lora_layout)
        left.addWidget(lora_box)

        left.addStretch()
        layout.addLayout(left, 1)

        # Right: 4 plots
        right = QtWidgets.QVBoxLayout()
        right.setContentsMargins(4, 4, 4, 4)   # <-- Now right is defined
        right.setSpacing(8)

        self.plot_alt = pg.PlotWidget(title="Altitude (m)")
        self.plot_press = pg.PlotWidget(title="Pressure (hPa)")
        self.plot_temp = pg.PlotWidget(title="Temperature (°C)")
        self.plot_vel = pg.PlotWidget(title="Relative Velocity (m/s)")
        for p in (self.plot_alt, self.plot_press, self.plot_temp, self.plot_vel):
            p.showGrid(x=True, y=True, alpha=0.2)
            p.setBackground('#101a24')
            p.getAxis('left').setTextPen('w')
            p.getAxis('bottom').setTextPen('w')
            p.setLabel('left', '', color='#88aacc')
            p.setLabel('bottom', 'Time (s)', color='#88aacc')
        self.curve_alt = self.plot_alt.plot(pen='y', name='Alt')
        self.curve_press = self.plot_press.plot(pen='c', name='Press')
        self.curve_temp = self.plot_temp.plot(pen='r', name='Temp')
        self.curve_vel = self.plot_vel.plot(pen='g', name='Vel')

        grid_plots = QtWidgets.QGridLayout()
        grid_plots.addWidget(self.plot_alt, 0, 0)
        grid_plots.addWidget(self.plot_press, 0, 1)
        grid_plots.addWidget(self.plot_temp, 1, 0)
        grid_plots.addWidget(self.plot_vel, 1, 1)
        right.addLayout(grid_plots)

        layout.addLayout(right, 2)

    def update(self, packet):
        # Update telemetry values
        alt = packet.get("ALTITUDE")
        press = packet.get("PRESSURE")
        temp = packet.get("TEMP")
        hum = packet.get("HUMIDITY")
        volts = packet.get("VOLTAGE")
        sats = packet.get("GNSS_SATS")
        state = packet.get("FLIGHT_STATE", "--")
        t = packet.get("TIME_STAMPING", packet.get("TIMESTAMP", "--"))

        vel = None
        if self.prev_alt is not None and alt is not None:
            vel = (alt - self.prev_alt)
        if alt is not None:
            self.prev_alt = alt

        current = packet.get("CURRENT")
        power = packet.get("POWER")
        if current is not None:
            current = float(current) / 1000.0  # telemetry field is mA
        if power is not None:
            power = float(power) / 1000.0  # telemetry field is mW

        def show(value, digits=1):
            return "--" if value is None else f"{float(value):.{digits}f}"

        mapping = {
            "ALTITUDE": show(alt),
            "VELOCITY": show(vel),
            "PRESSURE": show(float(press) / 100.0 if press is not None else None),
            "TEMP": show(temp),
            "HUMIDITY": show(hum),
            "CURRENT": show(current, 3),
            "POWER": show(power, 3),
            "GNSS_SATS": "--" if sats is None else str(sats),
            "FLIGHT_STATE": state,
            "TIME_STAMPING": t,
        }
        for key, val in mapping.items():
            if key in self.tel_labels:
                self.tel_labels[key].setText(val)

        gps_mapping = {
            "GNSS_LATITUDE": show(packet.get('GNSS_LATITUDE'), 6),
            "GNSS_LONGITUDE": show(packet.get('GNSS_LONGITUDE'), 6),
            "GNSS_ALTITUDE": show(packet.get('GNSS_ALTITUDE')),
            "GNSS_SATS": "--" if sats is None else str(sats),
            "HDOP": show(packet.get('GNSS_HDOP'), 2),
            "FIX_TYPE": "--" if packet.get('GNSS_FIX') is None else str(packet.get('GNSS_FIX')),
        }
        for key, val in gps_mapping.items():
            if key in self.gps_labels:
                self.gps_labels[key].setText(val)
        # Link metrics are unknown unless the receiver exposes those fields.
        for key in ("RSSI", "SNR", "SF", "BW", "PKT_SIZE", "PACKET_LOSS", "SRC_RATE"):
            if packet.get(key) is not None:
                self.lora_labels[key].setText(str(packet.get(key)))

        self.vel_buf.append(vel if vel is not None else float("nan"))
        if len(self.vel_buf) > self.buffer_size:
            self.vel_buf.pop(0)

        # Update plots
        self.t_buf.append(self.t_buf[-1] + 1 if self.t_buf else 1)
        self.alt_buf.append(alt if alt is not None else float("nan"))
        self.press_buf.append(float(press) / 100.0 if press is not None else float("nan"))
        self.temp_buf.append(temp if temp is not None else float("nan"))
        for buf in (self.t_buf, self.alt_buf, self.press_buf, self.temp_buf):
            if len(buf) > self.buffer_size:
                del buf[0]

        self.curve_alt.setData(self.t_buf, self.alt_buf)
        self.curve_press.setData(self.t_buf, self.press_buf)
        self.curve_temp.setData(self.t_buf, self.temp_buf)

        if len(self.vel_buf) > 0:
            if len(self.vel_buf) > len(self.t_buf):
                self.vel_buf.pop(0)
            self.curve_vel.setData(self.t_buf, self.vel_buf)

    def reset(self):
        self.t_buf = []
        self.alt_buf = []
        self.press_buf = []
        self.temp_buf = []
        self.vel_buf = []
        self.prev_alt = None
