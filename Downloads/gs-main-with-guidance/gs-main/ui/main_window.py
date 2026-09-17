"""
Main Window – The central application window with tabs.
All dashboards, graph engine, command panel, simulation, and reports integrated.
"""
import sys
import os
import time
from datetime import datetime

from PyQt5 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg

from config.config_loader import Config
from core.telemetry.constants import (
    TEAM_ID, CMD_TELEMETRY_ON, CMD_TELEMETRY_OFF, CMD_CALIBRATE
)
from core.telemetry.packet import parse_packet, add_legacy_aliases, PacketParseError
from core.telemetry.packet_sequencer import PacketSequencer
from core.data.csv_logger import CSVLogger
from core.data.image_archive import ImageArchive
from core.hardware.serial_link import SerialLink, list_available_ports

# AI imports
from core.ai.fingerprint import EnvironmentalFingerprintEngine
from core.ai.trend_predictor import AtmosphericTrendPredictor
from core.ai.wind_drift import StabilityMonitor, WindEstimator, estimate_landing_drift
from core.ai.recovery_health import RecoveryHealthMonitor
from core.ai.fault_detection import FaultDetector

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
from ui.graphs import GraphEngine

# Command Panel
from ui.commands import CommandPanel

# Simulation Tab
from ui.simulation_tab import SimulationTab

# Report Generator (updated)
from ui.reports import ReportGenerator

from utils.logger import get_logger

logger = get_logger(__name__)

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


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"ANTRS Ground Station v1.2 — {TEAM_ID}")
        self.resize(1600, 1000)
        self.setMinimumSize(1400, 900)
        self.setStyleSheet(STYLESHEET)

        self.cfg = Config()
        self.buffer_size = self.cfg.get('ui.graph_buffer_size', 300)

        # Backend
        self.serial_link = None
        self.csv_logger = CSVLogger()
        self.image_archive = ImageArchive()
        self.sequencer = PacketSequencer()
        self.fp_engine = EnvironmentalFingerprintEngine()
        self.trend_predictor = AtmosphericTrendPredictor()
        self.stability_monitor = StabilityMonitor()
        self.wind_estimator = WindEstimator()
        self.recovery_health = RecoveryHealthMonitor()
        self.fault_detector = FaultDetector()

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
        self.guidance_dashboard = GuidanceDashboard()

        # Command panel (pass send_command callback)
        self.command_panel = CommandPanel(send_command_callback=self._send_cmd)

        # Simulation tab (pass callback to inject packets)
        self.simulation_tab = SimulationTab(packet_callback=self._inject_packet)

        # Add tabs
        self.tabs.addTab(wrap_with_scroll(self.mission_dashboard), "Mission")
        self.tabs.addTab(wrap_with_scroll(self.telemetry_dashboard), "Telemetry")
        self.tabs.addTab(wrap_with_scroll(self.power_dashboard), "Power")
        self.tabs.addTab(wrap_with_scroll(self.recovery_dashboard), "Recovery")
        self.tabs.addTab(wrap_with_scroll(self.flight_dashboard), "Flight")
        self.tabs.addTab(wrap_with_scroll(self.sensor_dashboard), "Sensors")
        self.tabs.addTab(wrap_with_scroll(self.graph_engine), "Graphs")
        self.tabs.addTab(wrap_with_scroll(self.guidance_dashboard), "Guidance")
        self.tabs.addTab(wrap_with_scroll(self.command_panel), "Commands")
        self.tabs.addTab(wrap_with_scroll(self.simulation_tab), "Simulation")

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

        self.tabs.addTab(reports_tab, "Reports")

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

    def _toggle_connect(self):
        if self.serial_link is None:
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
                logger.info(f"Connected to {dev}")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", str(e))
                logger.error(f"Connection error: {e}")
                self.serial_link = None
        else:
            self.serial_link.disconnect()
            self.serial_link = None
            self.connect_btn.setText("Connect")
            self.status_label.setText("STATUS: DISCONNECTED")
            self.status_label.setStyleSheet("color: #e06050; font-weight: bold; font-size: 16px;")
            logger.info("Disconnected")

    def _send_cmd(self, cmd):
        if self.serial_link and self.serial_link.is_connected():
            self.serial_link.send_command(cmd)
            self.bottom_status.setText(f"Command sent: {cmd}")
            logger.info(f"Command sent: {cmd}")
        else:
            QtWidgets.QMessageBox.warning(self, "Not connected", "Connect to the ground station first.")

    def _poll_serial(self):
        if not self.serial_link or not self.serial_link.is_connected():
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

        # Forward packet to all dashboards
        self.mission_dashboard.update(packet)
        self.telemetry_dashboard.update(packet)
        self.power_dashboard.update(packet)
        self.recovery_dashboard.update(packet)
        self.flight_dashboard.update(packet)
        self.sensor_dashboard.update(packet)
        self.graph_engine.update(packet)

        # Update AI
        self._update_ai(packet)

        # Update guidance (precision landing)
        self._update_guidance(packet)

        self.bottom_status.setText(f"Packet #{packet.get('PACKET_COUNT', '?')}")

    def _inject_packet(self, raw_line):
        """
        Called by the simulation engine to inject a packet directly.
        """
        self._handle_line(raw_line)
        self.bottom_status.setText(f"Simulation: Packet #{self.sequencer.total_received}")

    # ---------- AI Update (FIXED) ----------
    def _update_ai(self, packet):
        fp = self.fp_engine.update(packet)
        fingerprint = fp.get('class_label', '--')

        wind_str = "Wind: --"
        landing_str = "Landing: --"
        wind_data = {}
        state = packet.get("FLIGHT_STATE")

        # Only estimate wind during descent states (5 and 6)
        try:
            state_int = int(state)
        except (ValueError, TypeError):
            state_int = -1

        if state_int in (5, 6):  # DESCENT, SECONDARY_DEPLOY
            wind = self.wind_estimator.update(packet)
            if wind.get("available"):
                wind_str = f"{wind['wind_speed_mps']:.1f} m/s @ {wind['wind_direction_deg']:.0f}°"
                wind_data = wind
                drift = estimate_landing_drift(
                    packet.get("GNSS_LATITUDE"), packet.get("GNSS_LONGITUDE"),
                    packet.get("ALTITUDE"), 3.0,
                    wind["wind_speed_mps"], wind["wind_direction_deg"]
                )
                if drift.get("available"):
                    time_left = drift['time_to_land_seconds']
                    mins = int(time_left // 60)
                    secs = int(time_left % 60)
                    landing_str = f"~{mins}m {secs}s"

        stab = self.stability_monitor.update(packet)
        stability = self.stability_monitor.stability_index_percent()

        rec = self.recovery_health.update(packet)
        recovery = rec['status']

        loss = self.sequencer.loss_rate_percent()
        fault = self.fault_detector.update(packet, loss)
        faults = fault['status']

        self.mission_dashboard.update_ai(fingerprint, wind_str, landing_str, stability, recovery, faults)

        self._ai_data = {
            'fingerprint': fingerprint,
            'wind': wind_data,
            'landing': landing_str,
            'stability': stability,
            'recovery': recovery,
            'faults': faults,
            'trend': self.trend_predictor.prediction,
            'power': {
                'voltage': packet.get("VOLTAGE", 0.0),
                'capacity': 0,
            }
        }

        logger.debug(f"Fingerprint: {fingerprint}, Stability: {stability}%, Faults: {faults}")

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
                ai_data['power']['capacity'] = cap

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
        self.csv_logger.close()
        if self.serial_link:
            self.serial_link.disconnect()
        logger.info("Application closed.")
        event.accept()
