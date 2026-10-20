"""
Main Window – The central application window with tabs.
All dashboards, graph engine, command panel, simulation, and reports integrated.
"""
import sys
import os
import time
import math
import csv
from datetime import datetime

from PyQt5 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg

from config.config_loader import Config
from core.telemetry.constants import (
    TEAM_ID, FIELD_NAMES, CMD_TELEMETRY_ON, CMD_TELEMETRY_OFF, CMD_CALIBRATE
)
from core.telemetry.packet import parse_packet, add_legacy_aliases, PacketParseError
from core.telemetry.packet_sequencer import PacketSequencer
from core.data.csv_logger import CSVLogger
from core.data.image_archive import ImageArchive
from core.hardware.serial_link import SerialLink, list_available_ports


# Guidance (precision landing)
from guidance.landing_controller import LandingController
from guidance.wind_estimator import WindEstimator as GuidanceWindEstimator

# Dashboards
from ui.dashboards import (
    TelemetryDashboard,
    PowerDashboard,
    RecoveryDashboard,
    FlightDashboard,
    SensorDashboard,
    MissionDashboard,
    GuidanceDashboard,
)

# Graph Engine
from ui.graphs import GraphEngine, MultiFieldGraphGrid

# Command Panel
from ui.commands import CommandPanel

# Simulation Tab
from ui.simulation_tab import SimulationTab

# Report Generator (updated)
from ui.reports import ReportGenerator

from utils.logger import get_logger

logger = get_logger(__name__)


class AnalyticsWorker(QtCore.QObject):
    request = QtCore.pyqtSignal(dict)
    finished = QtCore.pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.request.connect(self.process, QtCore.Qt.QueuedConnection)
        self._accel = []

    @QtCore.pyqtSlot(dict)
    def process(self, fields):
        """Small dependency-free analytics pass isolated from the serial/UI thread."""
        try:
            self._process(fields)
        except Exception as exc:
            self.finished.emit({"error": str(exc), "fingerprint": "Unavailable",
                                "environment": "Unavailable", "stability_variance": 0,
                                "trend_100m_lower": None})

    def _process(self, fields):
        uv = fields.get("UV", fields.get("UV_INDEX"))
        temp = fields.get("TEMP")
        press = fields.get("PRESSURE")
        if uv is None:
            fingerprint = "UV unavailable"
        elif float(uv) >= 6:
            fingerprint = "High UV (rule-based)"
        elif float(uv) >= 3:
            fingerprint = "Moderate UV (rule-based)"
        else:
            fingerprint = "Low UV (rule-based)"
        self._accel.append(tuple(float(fields.get(k) or 0) for k in ("ACCEL_X", "ACCEL_Y", "ACCEL_Z")))
        self._accel = self._accel[-10:]
        variance = 0.0
        if len(self._accel) > 1:
            values = [math.sqrt(sum(v * v for v in row)) for row in self._accel]
            mean = sum(values) / len(values)
            variance = sum((v-mean)**2 for v in values) / len(values)
        trend = float(temp) + 0.65 if temp is not None else None
        env = ("Type C (High UV / Altitude)" if uv is not None and float(uv) > 6 else
               "Type B (Mid-Altitude Transition)" if temp is not None and press is not None and float(temp) < 20 and float(press) < 95000 else
               "Type A (Nominal)")
        self.finished.emit({"fingerprint": fingerprint, "environment": env,
                             "stability_variance": variance, "anomaly": len(self._accel) == 10 and variance > 3.0,
                             "sample_count": len(self._accel),
                             "trend_100m_lower": trend})


class TelemetryFieldTable(QtWidgets.QWidget):
    """Live value card for every field in the current 37-column CSV schema."""
    UNITS = {
        "TIMESTAMP": "s", "ALTITUDE": "m", "PRESSURE": "hPa", "TEMP": "°C",
        "VOLTAGE": "V", "GNSS_LATITUDE": "°", "GNSS_LONGITUDE": "°",
        "GNSS_ALTITUDE": "m", "GNSS_SATS": "sat", "ACCEL_X": "m/s²",
        "ACCEL_Y": "m/s²", "ACCEL_Z": "m/s²", "GYRO_X": "deg/s",
        "GYRO_Y": "deg/s", "GYRO_Z": "deg/s", "MAG_X": "µT",
        "MAG_Y": "µT", "MAG_Z": "µT", "ROLL": "°", "PITCH": "°",
        "YAW": "°", "LIGHT_LUX": "lx", "UV_INDEX": "index", "HALL_RPM": "rpm",
        "REL_ALTITUDE": "m", "VERTICAL_SPEED": "m/s", "GNSS_GROUND_SPEED": "m/s",
        "GNSS_COURSE": "°", "GNSS_HDOP": "", "GNSS_FIX": "", "HUMIDITY": "%",
        "CURRENT": "A", "POWER": "W",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QGridLayout(self)
        self.values = {}
        for index, name in enumerate(FIELD_NAMES):
            unit = self.UNITS.get(name)
            title = name.replace("_", " ") + (f" ({unit})" if unit else "")
            box = QtWidgets.QGroupBox(title)
            vbox = QtWidgets.QVBoxLayout(box)
            value = QtWidgets.QLabel("--")
            value.setObjectName("value")
            value.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            vbox.addWidget(value)
            layout.addWidget(box, index // 4, index % 4)
            self.values[name] = value

    def update(self, packet):
        for name, label in self.values.items():
            value = packet.get(name)
            if value is None or value == "":
                label.setText("--")
            elif isinstance(value, float):
                if name == "PRESSURE":
                    value = value / 100.0  # wire/CSV pressure is Pa; display is hPa
                elif name == "CURRENT":
                    value = value / 1000.0  # wire/CSV current is mA; display is A
                elif name == "POWER":
                    value = value / 1000.0  # wire/CSV power is mW; display is W
                label.setText(f"{value:.3f}".rstrip("0").rstrip("."))
            else:
                label.setText(str(value))

# ---------- Stylesheet (Large, Bold, Professional) ----------
STYLESHEET = """
QMainWindow {
    background-color: #1e2a38;
}
QTabWidget::pane {
    border: 1px solid #2a3a4a;
    background: #141c26;
}
QTabBar::tab {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #2a3a4a, stop:1 #1a2632);
    color: #8a9aaa;
    padding: 10px 24px;
    margin-right: 4px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: bold;
    font-size: 14px;
    min-width: 80px;
}
QTabBar::tab:selected {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #3a6a8a, stop:1 #2a4a6a);
    color: #ffffff;
}
QGroupBox {
    border: 1px solid #2a3a4a;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 12px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #1a2632, stop:1 #141c26);
    color: #c0d0e0;
    font-size: 14px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 10px;
    color: #6a9ac0;
    font-weight: bold;
    font-size: 16px;
    background: transparent;
}
QLabel {
    color: #d0dce8;
    font-size: 14px;
}
QLabel#value {
    color: #6bc9ff;
    font-weight: bold;
    background-color: rgba(0, 20, 40, 0.6);
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 16px;
}
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #2a4a6a, stop:1 #1a2a3a);
    color: #d0e0f0;
    border: 1px solid #3a5a7a;
    border-radius: 6px;
    padding: 8px 18px;
    font-weight: bold;
    font-size: 14px;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #3a6a8a, stop:1 #2a4a6a);
    border: 1px solid #5a8aaa;
}
QPushButton:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #1a3a5a, stop:1 #0a1a2a);
}
QComboBox {
    background: #1a2632;
    color: #c0d0e0;
    border: 1px solid #2a4a5a;
    border-radius: 4px;
    padding: 6px 12px;
    font-size: 14px;
}
QComboBox:hover {
    border: 1px solid #3a6a8a;
}
QLabel#status_ok {
    color: #60c090;
    font-weight: bold;
    font-size: 16px;
}
QLabel#status_warn {
    color: #f0a030;
    font-weight: bold;
    font-size: 16px;
}
QLabel#status_error {
    color: #e06050;
    font-weight: bold;
    font-size: 16px;
}
"""

OUTDOOR_STYLESHEET = """
QMainWindow, QWidget { background: #ffffff; color: #111827; }
QTabWidget::pane, QGroupBox { background: #ffffff; border: 2px solid #334155; }
QTabBar::tab { background: #e2e8f0; color: #111827; padding: 10px 20px; font-weight: bold; }
QTabBar::tab:selected { background: #facc15; color: #111827; }
QLabel { color: #111827; }
QLabel#value { color: #003b73; background: #e0f2fe; font-weight: bold; }
QPushButton { background: #facc15; color: #111827; border: 2px solid #111827; padding: 9px 16px; font-weight: bold; }
QPushButton:hover { background: #fde68a; }
QComboBox, QTextEdit, QLineEdit { background: #ffffff; color: #111827; border: 2px solid #334155; }
"""


class AttitudeIndicator(QtWidgets.QWidget):
    """Dependency-free projected cube attitude indicator driven by Euler angles."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.roll = self.pitch = self.yaw = 0.0
        self.setMinimumSize(260, 240)

    def update_attitude(self, roll, pitch, yaw):
        self.roll, self.pitch, self.yaw = (float(roll or 0), float(pitch or 0), float(yaw or 0))
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.fillRect(self.rect(), self.palette().window())
        cx, cy = self.width() / 2, self.height() / 2
        painter.setPen(QtGui.QPen(QtGui.QColor("#64748b"), 1))
        painter.drawText(12, 22, f"ROLL {self.roll:.1f}°   PITCH {self.pitch:.1f}°   YAW {self.yaw:.1f}°")
        # Project a cube after yaw/pitch/roll rotations.
        verts = [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]
        r, p, y = [v * 3.14159265 / 180 for v in (self.roll,self.pitch,self.yaw)]
        import math
        projected = []
        for x, yy, z in verts:
            x1, y1 = x*math.cos(y)-yy*math.sin(y), x*math.sin(y)+yy*math.cos(y)
            y2, z2 = y1*math.cos(p)-z*math.sin(p), y1*math.sin(p)+z*math.cos(p)
            x3, z3 = x1*math.cos(r)+z2*math.sin(r), -x1*math.sin(r)+z2*math.cos(r)
            projected.append(QtCore.QPointF(cx+x3*55+z3*18, cy+y2*55-z3*20))
        edges = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
        painter.setPen(QtGui.QPen(QtGui.QColor("#0f6b9a"), 3))
        for a,b in edges:
            painter.drawLine(projected[a], projected[b])
        painter.end()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"ANTRS Ground Station v1.2 — {TEAM_ID}")
        self.resize(1600, 1000)
        self.setMinimumSize(1400, 900)
        self.setStyleSheet(STYLESHEET)
        self._outdoor_theme = False

        self.cfg = Config()
        self.buffer_size = self.cfg.get('ui.graph_buffer_size', 300)

        # Backend
        self.serial_link = None
        self.csv_logger = CSVLogger()
        self.image_archive = ImageArchive()
        self.sequencer = PacketSequencer()
        self._analytics_thread = QtCore.QThread(self)
        self._analytics_worker = AnalyticsWorker()
        self._analytics_worker.moveToThread(self._analytics_thread)
        self._analytics_thread.start()
        self._analytics_pending = False
        self._rf_pressure_profile = []
        self._rf_pressure_index = 0
        self._rf_sim_active = False
        self._rf_sim_timer = QtCore.QTimer(self)
        self._rf_sim_timer.timeout.connect(self._send_next_rf_pressure)

        # Guidance (precision landing) -- reference point is set from the
        # first valid GPS fix (see _handle_line), since the launch
        # coordinates aren't known until telemetry starts flowing.
        self.landing_controller = LandingController(
            start_glide_threshold_m=20.0,
            stop_glide_threshold_m=10.0,
            glide_disable_altitude_m=50.0,
            min_command_interval_s=2.0,
        )
        self.guidance_wind_estimator = None  # created once we know the
                                              # reference point; see
                                              # _handle_line
        self._guidance_reference_set = False
        self._guidance_auto_mode = True

        # Build UI
        self._build_ui()
        self._wire_guidance_ui()
        self._analytics_worker.finished.connect(self._on_analytics_finished)

        # Timers
        self.poll_timer = QtCore.QTimer()
        self.poll_timer.timeout.connect(self._poll_serial)
        self.poll_timer.start(100)


        logger.info("MainWindow initialized.")

    # ---------- UI Construction ----------
    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_layout = QtWidgets.QVBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # Top control bar
        bar = QtWidgets.QHBoxLayout()
        bar.setSpacing(12)
        self.port_combo = QtWidgets.QComboBox()
        self._refresh_ports()
        refresh_btn = QtWidgets.QPushButton("Refresh Ports")
        refresh_btn.clicked.connect(self._refresh_ports)
        self.connect_btn = QtWidgets.QPushButton("Connect")
        self.connect_btn.clicked.connect(self._toggle_connect)
        start_btn = QtWidgets.QPushButton("Start Telemetry")
        start_btn.clicked.connect(lambda: self._send_cmd(CMD_TELEMETRY_ON))
        stop_btn = QtWidgets.QPushButton("Stop Telemetry")
        stop_btn.clicked.connect(lambda: self._send_cmd(CMD_TELEMETRY_OFF))

        self.status_label = QtWidgets.QLabel("STATUS: DISCONNECTED")
        self.status_label.setStyleSheet("color: #e06050; font-weight: bold; font-size: 16px;")

        bar.addWidget(QtWidgets.QLabel("Port:"))
        bar.addWidget(self.port_combo)
        bar.addWidget(refresh_btn)
        bar.addWidget(self.connect_btn)
        bar.addWidget(start_btn)
        bar.addWidget(stop_btn)
        self.simulation_toggle = QtWidgets.QCheckBox("Simulation Mode")
        self.simulation_toggle.toggled.connect(self._toggle_simulation_mode)
        bar.addWidget(self.simulation_toggle)
        self.theme_btn = QtWidgets.QPushButton("Outdoor Light Theme")
        self.theme_btn.clicked.connect(self._toggle_theme)
        bar.addWidget(self.theme_btn)
        bar.addStretch()
        bar.addWidget(self.status_label)
        main_layout.addLayout(bar)

        # Tabs
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setTabPosition(QtWidgets.QTabWidget.North)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setElideMode(QtCore.Qt.ElideNone)
        self.tabs.setStyleSheet("font-size: 14px;")

        def wrap_with_scroll(widget):
            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(widget)
            scroll.setStyleSheet("background: #141c26;")
            return scroll

        # Instantiate all dashboards
        self.mission_dashboard = MissionDashboard()
        self.telemetry_dashboard = TelemetryDashboard(buffer_size=self.buffer_size)
        self.power_dashboard = PowerDashboard(buffer_size=self.buffer_size)
        self.recovery_dashboard = RecoveryDashboard()
        self.flight_dashboard = FlightDashboard()
        self.sensor_dashboard = SensorDashboard()
        self.graph_engine = GraphEngine(buffer_size=self.buffer_size)
        self.multi_field_grid = MultiFieldGraphGrid(buffer_size=self.buffer_size)
        self.guidance_dashboard = GuidanceDashboard()

        # Command panel (pass send_command callback)
        self.command_panel = CommandPanel(send_command_callback=self._send_cmd)

        # Simulation tab (pass callback to inject packets)
        self.simulation_tab = SimulationTab(
            packet_callback=self._inject_packet,
            rf_start_callback=self._start_rf_pressure_profile,
            rf_stop_callback=self._stop_rf_pressure_profile,
        )
        self.simulation_tab.engine.status_updated.connect(self._sync_simulation_toggle)

        self.attitude_indicator = AttitudeIndicator()
        live_page = QtWidgets.QWidget()
        live_layout = QtWidgets.QVBoxLayout(live_page)
        inner_tabs = QtWidgets.QTabWidget()
        live_view = QtWidgets.QWidget()
        live_view_layout = QtWidgets.QHBoxLayout(live_view)
        live_view_layout.addWidget(self.telemetry_dashboard, 3)
        live_view_layout.addWidget(self.attitude_indicator, 1)
        inner_tabs.addTab(wrap_with_scroll(live_view), "Live Telemetry & Attitude")
        self.field_table = TelemetryFieldTable()
        inner_tabs.addTab(wrap_with_scroll(self.field_table), "All 37 Telemetry Values")
        inner_tabs.addTab(wrap_with_scroll(self.mission_dashboard), "Mission")
        inner_tabs.addTab(wrap_with_scroll(self.power_dashboard), "Power")
        inner_tabs.addTab(wrap_with_scroll(self.recovery_dashboard), "Recovery")
        inner_tabs.addTab(wrap_with_scroll(self.flight_dashboard), "Flight")
        inner_tabs.addTab(wrap_with_scroll(self.sensor_dashboard), "Sensors")
        inner_tabs.addTab(wrap_with_scroll(self.graph_engine), "Graphs")
        inner_tabs.addTab(wrap_with_scroll(self.multi_field_grid), "All 37 Fields")
        inner_tabs.addTab(wrap_with_scroll(self.guidance_dashboard), "Guidance")
        inner_tabs.addTab(wrap_with_scroll(self.command_panel), "Commands")
        inner_tabs.addTab(wrap_with_scroll(self.simulation_tab), "Simulation Tools")
        live_layout.addWidget(inner_tabs)
        self.tabs.addTab(live_page, "LIVE TELEMETRY")

        # ---- Reports tab ----
        reports_tab = QtWidgets.QWidget()
        reports_layout = QtWidgets.QVBoxLayout(reports_tab)
        report_label = QtWidgets.QLabel("Generate Mission Report")
        report_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #88aacc;")
        reports_layout.addWidget(report_label)

        self.report_btn = QtWidgets.QPushButton("📄 Generate PDF Report")
        self.report_btn.clicked.connect(self._generate_report)
        self.report_btn.setStyleSheet("font-size: 16px; padding: 12px;")
        reports_layout.addWidget(self.report_btn)

        self.report_status = QtWidgets.QLabel("Ready")
        self.report_status.setStyleSheet("color: #6a8aaa; font-size: 14px;")
        reports_layout.addWidget(self.report_status)
        reports_layout.addStretch()

        analytics_page = QtWidgets.QWidget()
        analytics_layout = QtWidgets.QVBoxLayout(analytics_page)
        analytics_title = QtWidgets.QLabel("OFFLINE ANALYTICS & MISSION REPORTS")
        analytics_title.setStyleSheet("font-size: 20px; font-weight: bold;")
        analytics_layout.addWidget(analytics_title)
        self.analytics_status = QtWidgets.QLabel("Analytics runs in a background worker; live telemetry remains independent.")
        analytics_layout.addWidget(self.analytics_status)
        analytics_summary = QtWidgets.QLabel(
            "Background analysis includes rule-based environmental fingerprinting, a 100 m lapse-rate estimate, "
            "and rolling accelerometer stability variance. Optional trained models remain disabled unless selected."
        )
        analytics_summary.setWordWrap(True)
        analytics_layout.addWidget(analytics_summary)
        analytics_layout.addWidget(reports_tab)
        self.tabs.addTab(analytics_page, "AI ANALYTICS & REPORTS")

        main_layout.addWidget(self.tabs)

        # Bottom status
        self.bottom_status = QtWidgets.QLabel("System Initialized")
        self.bottom_status.setStyleSheet("color: #6a8aaa; padding: 6px; font-size: 14px;")
        main_layout.addWidget(self.bottom_status)

    # ---------- Guidance wiring ----------
    def _wire_guidance_ui(self):
        self.guidance_dashboard.set_target_btn.clicked.connect(
            self._on_set_guidance_target
        )
        self.guidance_dashboard.auto_btn.toggled.connect(
            self._on_guidance_mode_toggled
        )
        self.guidance_dashboard.manual_hover_btn.clicked.connect(
            lambda: self._send_manual_guidance_command("HOVER")
        )
        self.guidance_dashboard.manual_glide_left_btn.clicked.connect(
            lambda: self._send_manual_guidance_command("GLIDE_LEFT")
        )
        self.guidance_dashboard.manual_glide_right_btn.clicked.connect(
            lambda: self._send_manual_guidance_command("GLIDE_RIGHT")
        )

    def _on_set_guidance_target(self):
        try:
            lat = float(self.guidance_dashboard.target_lat_input.text())
            lon = float(self.guidance_dashboard.target_lon_input.text())
        except ValueError:
            QtWidgets.QMessageBox.warning(
                self, "Invalid target",
                "Enter target latitude and longitude as decimal numbers."
            )
            return

        if not self._guidance_reference_set:
            QtWidgets.QMessageBox.warning(
                self, "No GPS fix yet",
                "Wait for at least one telemetry packet with a GPS fix "
                "before setting the landing target (the first fix is "
                "used as the guidance reference point)."
            )
            return

        self.landing_controller.set_target(lat, lon)
        self.landing_controller.arm()
        self.bottom_status.setText(f"Guidance target set: {lat:.5f}, {lon:.5f} — ARMED")
        logger.info(f"Guidance target set to ({lat}, {lon}), controller armed")

    def _on_guidance_mode_toggled(self, auto_checked):
        self._guidance_auto_mode = auto_checked
        if not auto_checked:
            self.landing_controller.disarm()
            self.bottom_status.setText("Guidance: MANUAL mode (auto commands disabled)")
        else:
            self.bottom_status.setText("Guidance: AUTO mode")

    def _send_manual_guidance_command(self, command):
        if self._guidance_auto_mode:
            return  # manual buttons only act in MANUAL mode
        self._send_cmd(command)

    # ---------- Utility Methods ----------
    def _refresh_ports(self):
        self.port_combo.clear()
        for dev, desc in list_available_ports():
            self.port_combo.addItem(f"{dev} ({desc})", userData=dev)
        if self.port_combo.count() == 0:
            self.port_combo.addItem("No ports")

    def _toggle_theme(self):
        self._outdoor_theme = not self._outdoor_theme
        self.setStyleSheet(OUTDOOR_STYLESHEET if self._outdoor_theme else STYLESHEET)
        self.theme_btn.setText("Dark Theme" if self._outdoor_theme else "Outdoor Light Theme")
        # Pyqtgraph widgets maintain their own plot background and axis pens.
        bg, pen = ("#ffffff", "k") if self._outdoor_theme else ("#101a24", "w")
        for widget in (self.graph_engine, self.multi_field_grid):
            for plot in widget.findChildren(pg.PlotWidget):
                plot.setBackground(bg)
                plot.getAxis("left").setTextPen(pen)
                plot.getAxis("bottom").setTextPen(pen)

    def _toggle_simulation_mode(self, enabled):
        if enabled:
            if self.serial_link and self.serial_link.is_connected():
                QtWidgets.QMessageBox.warning(self, "Simulation Mode", "Disconnect the radio before enabling simulation.")
                self.simulation_toggle.blockSignals(True)
                self.simulation_toggle.setChecked(False)
                self.simulation_toggle.blockSignals(False)
                return
            self.simulation_tab._start_synthetic()
            self.bottom_status.setText("Simulation Mode: synthetic telemetry active")
        else:
            self.simulation_tab._stop()
            self.bottom_status.setText("Simulation Mode: off")

    @QtCore.pyqtSlot(str)
    def _sync_simulation_toggle(self, status):
        if not self.simulation_tab.engine.is_running and self.simulation_toggle.isChecked():
            self.simulation_toggle.blockSignals(True)
            self.simulation_toggle.setChecked(False)
            self.simulation_toggle.blockSignals(False)

    @QtCore.pyqtSlot(dict)
    def _on_analytics_finished(self, result):
        self._analytics_pending = False
        if result.get("error"):
            logger.warning("Background analytics failed: %s", result["error"])
        self._ai_data = {
            "fingerprint": result.get("fingerprint", "Unavailable"),
            "environment": result.get("environment", "Unavailable"),
            "stability_variance": result.get("stability_variance"),
            "trend": ({
                "predicted_temperature_100m_lower_c": result["trend_100m_lower"],
                "method": "standard-lapse-rate estimate",
            } if result.get("trend_100m_lower") is not None else None),
            "power": {},
        }
        self.analytics_status.setText(
            "Background analysis: {} | {} | acceleration variance {:.3f} ({}) | 100 m lower temperature {}".format(
                result.get("environment", "--"), result.get("fingerprint", "--"),
                result.get("stability_variance", 0),
                "ANOMALY" if result.get("anomaly") else ("collecting" if result.get("sample_count", 0) < 10 else "no anomaly"),
                "{:.2f} °C".format(result["trend_100m_lower"]) if result.get("trend_100m_lower") is not None else "--",
            )
        )

    def _toggle_connect(self):
        if self.serial_link is None:
            if self.simulation_toggle.isChecked() or self.simulation_tab.engine.is_running:
                QtWidgets.QMessageBox.warning(
                    self, "Simulation Mode", "Turn Simulation Mode off before connecting to the radio."
                )
                return
            dev = self.port_combo.currentData()
            if not dev:
                QtWidgets.QMessageBox.warning(self, "No port", "Select a port.")
                return
            try:
                self.serial_link = SerialLink(dev)
                self.serial_link.connect()
                self.connect_btn.setText("Disconnect")
                self.status_label.setText("STATUS: CONNECTED")
                self.status_label.setStyleSheet("color: #60c090; font-weight: bold; font-size: 16px;")
                self.simulation_tab.allow_start = False
                self.simulation_tab.allow_rf = True
                self.simulation_tab._update_ui_state(self.simulation_tab.engine.is_running)
                logger.info(f"Connected to {dev}")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", str(e))
                logger.error(f"Connection error: {e}")
                self.serial_link = None
        else:
            self._stop_rf_pressure_profile(send_disable=True)
            self.serial_link.disconnect()
            self.serial_link = None
            self.simulation_tab.allow_start = True
            self.simulation_tab.allow_rf = False
            self.simulation_tab._update_ui_state(self.simulation_tab.engine.is_running)
            self.connect_btn.setText("Connect")
            self.status_label.setText("STATUS: DISCONNECTED")
            self.status_label.setStyleSheet("color: #e06050; font-weight: bold; font-size: 16px;")
            logger.info("Disconnected")

    def _send_cmd(self, cmd):
        if self.serial_link and self.serial_link.is_connected():
            if self.serial_link.send_command(cmd):
                self.bottom_status.setText(f"Command sent: {cmd}")
                logger.info(f"Command sent: {cmd}")
                return True
            else:
                self.bottom_status.setText(f"Command failed: serial link lost while sending {cmd}")
                return False
        else:
            QtWidgets.QMessageBox.warning(self, "Not connected", "Connect to the ground station first.")
            return False

    def _start_rf_pressure_profile(self):
        if not self.serial_link or not self.serial_link.is_connected():
            QtWidgets.QMessageBox.warning(self, "Not connected", "Connect the radio before starting RF simulation.")
            return
        filepath, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select pressure profile CSV", "", "CSV Files (*.csv)"
        )
        if not filepath:
            return
        try:
            with open(filepath, "r", newline="", encoding="utf-8-sig") as source:
                reader = csv.DictReader(source)
                if reader.fieldnames and any(name.strip().upper() == "PRESSURE" for name in reader.fieldnames):
                    pressure_key = next(name for name in reader.fieldnames if name.strip().upper() == "PRESSURE")
                    values = [float(row[pressure_key]) for row in reader if row.get(pressure_key)]
                else:
                    source.seek(0)
                    values = [float(row[0]) for row in csv.reader(source) if row and row[0].strip()]
            if not values or any(not math.isfinite(value) or value <= 0 for value in values):
                raise ValueError("CSV must contain positive pressure values in pascals.")
        except (OSError, ValueError, KeyError, csv.Error) as exc:
            QtWidgets.QMessageBox.warning(self, "Invalid pressure profile", str(exc))
            return

        if self.simulation_tab.engine.is_running:
            self.simulation_tab._stop()
        if not self._send_cmd("SIM_ENABLE"):
            return
        self._rf_pressure_profile = values
        self._rf_pressure_index = 0
        self._rf_sim_active = True
        self._send_next_rf_pressure()
        self._rf_sim_timer.start(1000)
        self.bottom_status.setText(f"RF pressure simulation active: {len(values)} samples")

    def _send_next_rf_pressure(self):
        if not self._rf_sim_active:
            return
        if self._rf_pressure_index >= len(self._rf_pressure_profile):
            self._stop_rf_pressure_profile(send_disable=True)
            self.bottom_status.setText("RF pressure simulation complete")
            return
        pressure = self._rf_pressure_profile[self._rf_pressure_index]
        if not self._send_cmd(f"SIMP,{pressure:.1f}"):
            self._stop_rf_pressure_profile(send_disable=False)
            return
        self._rf_pressure_index += 1

    def _stop_rf_pressure_profile(self, send_disable=True):
        was_active = self._rf_sim_active
        self._rf_sim_active = False
        self._rf_sim_timer.stop()
        self._rf_pressure_profile = []
        self._rf_pressure_index = 0
        if send_disable and was_active and self.serial_link and self.serial_link.is_connected():
            self._send_cmd("SIM_DISABLE")

    def _poll_serial(self):
        if not self.serial_link:
            return

        if self.serial_link.is_link_broken():
            # Reader thread died from a real I/O error (e.g. USB cable/
            # receiver physically disconnected), not just a quiet RF link.
            # Distinct from "no telemetry yet" so the operator knows to
            # physically check the connection, not just wait.
            self.status_label.setText("STATUS: LINK LOST")
            self.status_label.setStyleSheet("color: #e06050; font-weight: bold; font-size: 16px;")
            self.connect_btn.setText("Connect")
            self._stop_rf_pressure_profile(send_disable=False)
            self.serial_link.disconnect()
            self.serial_link = None
            self.simulation_tab.allow_start = True
            self.simulation_tab.allow_rf = False
            self.simulation_tab._update_ui_state(self.simulation_tab.engine.is_running)
            logger.error("Serial link lost (unexpected I/O error) -- check USB connection.")
            return

        if not self.serial_link.is_connected():
            return

        for line in self.serial_link.read_available_lines():
            self._handle_line(line)

    def _handle_line(self, line):
        try:
            packet = add_legacy_aliases(parse_packet(line))
        except PacketParseError as e:
            self.bottom_status.setText(f"Parse error: {e}")
            logger.warning(f"Parse error: {e}")
            return

        self.csv_logger.log(packet)

        seq_result = self.sequencer.process(packet)
        if seq_result["missed"]:
            self.bottom_status.setText(
                f"⚠ {seq_result['missed']} packet(s) lost before #{packet.get('PACKET_COUNT', '?')}"
            )
            logger.warning(f"Packet loss detected: {seq_result['missed']} missed")
        elif seq_result["duplicate"]:
            logger.warning(f"Duplicate packet #{packet.get('PACKET_COUNT', '?')} received")
        elif seq_result["out_of_order"]:
            logger.warning(f"Out-of-order packet #{packet.get('PACKET_COUNT', '?')} received")

        # Forward packet to all dashboards
        self.mission_dashboard.update(packet)
        self.telemetry_dashboard.update(packet)
        self.power_dashboard.update(packet)
        self.recovery_dashboard.update(packet)
        self.flight_dashboard.update(packet)
        self.sensor_dashboard.update(packet)
        self.attitude_indicator.update_attitude(packet.get("ROLL", 0), packet.get("PITCH", 0), packet.get("YAW", 0))
        self.field_table.update(packet)
        self.graph_engine.update(packet)
        self.multi_field_grid.update(packet)

        # Optional analysis must never prevent the mandatory telemetry path
        # (CSV logging, dashboard refresh, and guidance) from processing a
        # valid packet. Models and sensor-derived insights are best-effort.
        if not self._analytics_pending:
            self._analytics_pending = True
            self._analytics_worker.request.emit(dict(packet.fields))

        # Update guidance (precision landing)
        try:
            self._update_guidance(packet)
        except Exception as e:
            logger.exception("Guidance display update failed: %s", e)

        if not (seq_result["missed"] or seq_result["duplicate"] or seq_result["out_of_order"]):
            self.bottom_status.setText(f"Packet #{packet.get('PACKET_COUNT', '?')}")

    def _inject_packet(self, raw_line):
        """
        Called by the simulation engine to inject a packet directly.
        """
        self._handle_line(raw_line)
        self.bottom_status.setText(f"Simulation: Packet #{self.sequencer.total_received}")

    # ---------- Guidance Update ----------
    def _update_guidance(self, packet):
        lat = packet.get("GNSS_LATITUDE")
        lon = packet.get("GNSS_LONGITUDE")
        alt = packet.get("ALTITUDE", 0.0)
        state = packet.get("FLIGHT_STATE", "")

        if lat is None or lon is None:
            return  # no GPS fix in this packet -- nothing to do

        # First valid GPS fix becomes the guidance reference point and
        # the origin of the descent line. The operator still has to set
        # a target (lat/lon) in the Guidance tab and press SET TARGET
        # before the controller will arm and actually issue commands.
        if not self._guidance_reference_set:
            self.landing_controller.set_reference(lat, lon)
            self.landing_controller.set_origin(lat, lon)
            self.guidance_wind_estimator = GuidanceWindEstimator(lat, lon)
            self._guidance_reference_set = True
            logger.info(f"Guidance reference point set to ({lat}, {lon})")

        now_s = time.monotonic()
        wind_speed, wind_dir = self.guidance_wind_estimator.update(lat, lon, now_s)
        self.guidance_dashboard.update_wind(wind_speed, wind_dir)

        if not self._guidance_auto_mode:
            # MANUAL mode: still show telemetry/flight-state on the
            # dashboard, but don't run or transmit automatic decisions.
            self.guidance_dashboard.update(packet)
            return

        result = self.landing_controller.update(lat, lon, alt, state, now_s=now_s)
        self.guidance_dashboard.update_guidance(packet, result)

        if result["transmit"]:
            self._send_cmd(result["command"])
            logger.info(
                f"Guidance command sent: {result['command']} "
                f"(xtrack={result['cross_track_m']:.1f}m, {result['reason']})"
            )


    # ---------- Report Generation (UPDATED) ----------
    def _generate_report(self):
        self.report_status.setText("Generating report...")
        self.report_status.setStyleSheet("color: #f0a030; font-size: 14px;")
        QtWidgets.QApplication.processEvents()

        try:
            ai_data = self._ai_data if hasattr(self, '_ai_data') else {}
            if hasattr(self, 'power_dashboard'):
                cap_text = self.power_dashboard.power_capacity.text()
                try:
                    cap = float(cap_text.split(':')[1].strip().replace('%', ''))
                except:
                    cap = 0
                ai_data.setdefault('power', {})['capacity'] = cap

            # --- Optional: specify a video file from SD card ---
            # If you have a video file, set its path here.
            # Example: video_path = "D:/CAN-7USAT-GroundStation/data/video/mission_video.mp4"
            video_path = None
            # If video file exists, use it:
            # if os.path.exists(video_path):
            #     report_gen = ReportGenerator(
            #         csv_filepath=self.csv_logger.filepath,
            #         image_archive=self.image_archive,
            #         ai_data=ai_data,
            #         graph_engine=self.graph_engine,
            #         video_filepath=video_path
            #     )
            # else:
            report_gen = ReportGenerator(
                csv_filepath=self.csv_logger.filepath,
                image_archive=self.image_archive,
                ai_data=ai_data,
                graph_engine=self.graph_engine,
                video_filepath=video_path
            )

            # Generate report – saves to a timestamped folder inside mission_reports/
            output_dir = report_gen.generate()
            pdf_path = os.path.join(output_dir, "Mission_Report.pdf")

            self.report_status.setText(f"✅ Report saved in: {output_dir}")
            self.report_status.setStyleSheet("color: #60c090; font-size: 14px;")
            self.bottom_status.setText(f"Report generated: {output_dir}")

            QtWidgets.QMessageBox.information(
                self,
                "Report",
                f"Mission report exported to:\n{output_dir}\n\n"
                f"Contents:\n"
                f"  - PDF report\n"
                f"  - Full CSV data\n"
                f"  - Video file (if available)\n"
                f"  - README.txt"
            )
        except Exception as e:
            logger.error(f"Report generation error: {e}")
            self.report_status.setText(f"❌ Error: {e}")
            self.report_status.setStyleSheet("color: #e06050; font-size: 14px;")
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to generate report:\n{e}")

    def closeEvent(self, event):
        self._stop_rf_pressure_profile(send_disable=True)
        self.csv_logger.close()
        self.simulation_tab.engine.stop()
        if self.serial_link:
            self.serial_link.disconnect()
        self._analytics_thread.quit()
        self._analytics_thread.wait(1500)
        logger.info("Application closed.")
        event.accept()
