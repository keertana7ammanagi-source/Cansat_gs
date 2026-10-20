"""
Anomaly Detection Dashboard – Real-time monitoring of sensor health and anomalies.

Displays:
- Operational Status Banner (MONITORING / POTENTIAL ANOMALY DETECTED / INSUFFICIENT BASELINE SAMPLES / INVALID SENSOR DATA)
- Live Anomaly Alert Table (Timestamp, Sensor, Value, Severity, Type, Reason, Phase, Occurrences)
- Sensor Baselines & Metrics Table (Current Value, Baseline Mean/Median, MAD/Std, Limits, Status)
- Alert timeline / history graph using PyQtGraph with alert markers
- Clear / Reset controls
"""

from PyQt5 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg

from .base_dashboard import BaseDashboard
from core.ai.anomaly_detector import AnomalyDetector, AnomalyEvent
from config.config_loader import Config
from utils.logger import get_logger

logger = get_logger(__name__)

# Color definitions consistent with ANTRS dark theme
COLOR_MONITORING = "#4CAF50"     # Green
COLOR_WARMUP     = "#29B6F6"     # Cyan / Light Blue
COLOR_ANOMALY    = "#FFA726"     # Amber / Orange
COLOR_CRITICAL   = "#EF5350"     # Red
COLOR_TEXT_MUTED = "#8a9aaa"


class AnomalyDashboard(BaseDashboard):
    def __init__(self, parent=None):
        super().__init__(parent)
        cfg = Config()

        # Load parameters from configuration
        win_size = cfg.get("anomaly_detection.window_size", 30)
        min_samp = cfg.get("anomaly_detection.min_samples", 10)
        warn_z = cfg.get("anomaly_detection.warning_z_score", 3.0)
        crit_z = cfg.get("anomaly_detection.critical_z_score", 4.5)
        cooldown = cfg.get("anomaly_detection.cooldown_seconds", 5.0)
        shift_lim = cfg.get("anomaly_detection.persistent_shift_limit", 8)

        self.detector = AnomalyDetector(
            window_size=win_size,
            min_samples=min_samp,
            warning_z_score=warn_z,
            critical_z_score=crit_z,
            cooldown_seconds=cooldown,
            persistent_shift_limit=shift_lim,
        )

        self._plot_times = []
        self._plot_severity = []
        self._max_table_rows = 150

        self._build_ui()

    def _build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(10)

        # Header bar
        header_layout = QtWidgets.QHBoxLayout()
        header_label = QtWidgets.QLabel("OFFLINE ANOMALY DETECTION  |  Sensor Health & Limit Checks")
        header_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #88aacc;")
        header_layout.addWidget(header_label)
        header_layout.addStretch()

        reset_btn = QtWidgets.QPushButton("Reset Baseline")
        reset_btn.setToolTip("Clear baseline history and restart warmup")
        reset_btn.clicked.connect(self.reset)
        clear_btn = QtWidgets.QPushButton("Clear Alert History")
        clear_btn.setToolTip("Clear the alert table and event plot")
        clear_btn.clicked.connect(self._clear_alerts)

        header_layout.addWidget(reset_btn)
        header_layout.addWidget(clear_btn)
        main_layout.addLayout(header_layout)

        # Status Banner
        self.banner = QtWidgets.QFrame()
        self.banner.setFrameShape(QtWidgets.QFrame.StyledPanel)
        banner_layout = QtWidgets.QHBoxLayout(self.banner)
        banner_layout.setContentsMargins(16, 10, 16, 10)

        self.status_icon = QtWidgets.QLabel("🔵")
        self.status_icon.setStyleSheet("font-size: 20px;")
        banner_layout.addWidget(self.status_icon)

        self.status_text = QtWidgets.QLabel("STATUS: INSUFFICIENT BASELINE SAMPLES (Warming Up)")
        self.status_text.setStyleSheet("font-size: 16px; font-weight: bold; color: #29B6F6;")
        banner_layout.addWidget(self.status_text, 1)

        self.status_details = QtWidgets.QLabel("Samples: 0 | Active Alerts: 0 | Window: 30")
        self.status_details.setStyleSheet("font-size: 13px; color: #8a9aaa;")
        banner_layout.addWidget(self.status_details)

        self._apply_banner_style(COLOR_WARMUP)
        main_layout.addWidget(self.banner)

        # Splitter for Tables and Plot
        splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)

        # Top section: Two tabs or side-by-side for Alerts Table & Sensor Metrics
        tables_widget = QtWidgets.QWidget()
        tables_layout = QtWidgets.QHBoxLayout(tables_widget)
        tables_layout.setContentsMargins(0, 0, 0, 0)
        tables_layout.setSpacing(8)

        # Left: Live Alerts Table
        alerts_group = QtWidgets.QGroupBox("Live Anomaly Alerts")
        alerts_layout = QtWidgets.QVBoxLayout(alerts_group)
        self.alerts_table = QtWidgets.QTableWidget()
        self.alerts_table.setColumnCount(8)
        self.alerts_table.setHorizontalHeaderLabels([
            "Time (s)", "Sensor", "Value", "Severity", "Anomaly Type", "Reason", "Flight State", "Repeats"
        ])
        self.alerts_table.horizontalHeader().setStretchLastSection(False)
        self.alerts_table.horizontalHeader().setSectionResizeMode(5, QtWidgets.QHeaderView.Stretch)
        self.alerts_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.alerts_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.alerts_table.setStyleSheet("""
            QTableWidget {
                background-color: #101a24;
                gridline-color: #1f2e3d;
                font-size: 12px;
                color: #e0e8f0;
            }
            QHeaderView::section {
                background-color: #1a2632;
                color: #88aacc;
                font-weight: bold;
                padding: 4px;
                border: 1px solid #1f2e3d;
            }
        """)
        alerts_layout.addWidget(self.alerts_table)
        tables_layout.addWidget(alerts_group, 3)

        # Right: Monitored Sensors Status
        sensors_group = QtWidgets.QGroupBox("Sensor Baselines & Physical Limits")
        sensors_layout = QtWidgets.QVBoxLayout(sensors_group)
        self.sensors_table = QtWidgets.QTableWidget()
        self.sensors_table.setColumnCount(6)
        self.sensors_table.setHorizontalHeaderLabels([
            "Sensor", "Value", "Status", "Samples", "Baseline (Med/MAD)", "Valid Limits"
        ])
        self.sensors_table.horizontalHeader().setStretchLastSection(True)
        self.sensors_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.sensors_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.sensors_table.setStyleSheet("""
            QTableWidget {
                background-color: #101a24;
                gridline-color: #1f2e3d;
                font-size: 12px;
                color: #e0e8f0;
            }
            QHeaderView::section {
                background-color: #1a2632;
                color: #88aacc;
                font-weight: bold;
                padding: 4px;
                border: 1px solid #1f2e3d;
            }
        """)
        sensors_layout.addWidget(self.sensors_table)
        tables_layout.addWidget(sensors_group, 2)

        splitter.addWidget(tables_widget)

        # Bottom section: Alert Event Plot
        plot_group = QtWidgets.QGroupBox("Anomaly Event Timeline (Severity over Mission Time)")
        plot_layout = QtWidgets.QVBoxLayout(plot_group)
        self.plot_widget = pg.PlotWidget(title="Real-Time Anomaly Severity Markers")
        self.plot_widget.setBackground("#101a24")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self.plot_widget.setLabel("left", "Severity (1: Warn, 2: Crit, 3: Quality)", color="#88aacc")
        self.plot_widget.setLabel("bottom", "Mission Elapsed Time (s)", color="#88aacc")
        self.plot_widget.setYRange(0, 4)

        # Scatter plot for anomaly occurrences
        self.scatter_item = pg.ScatterPlotItem(size=10, pen=pg.mkPen(None))
        self.plot_widget.addItem(self.scatter_item)

        plot_layout.addWidget(self.plot_widget)
        splitter.addWidget(plot_group)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter)

        # Initialize sensors table rows
        self._init_sensors_table()

    def _apply_banner_style(self, color_hex: str):
        self.banner.setStyleSheet(f"""
            QFrame {{
                background-color: #141f2c;
                border-left: 6px solid {color_hex};
                border-radius: 4px;
            }}
        """)

    def _init_sensors_table(self):
        summary = self.detector.get_sensor_summary()
        self.sensors_table.setRowCount(len(summary))
        for row, (field, info) in enumerate(summary.items()):
            self.sensors_table.setItem(row, 0, QtWidgets.QTableWidgetItem(field))
            self.sensors_table.setItem(row, 1, QtWidgets.QTableWidgetItem("--"))
            self.sensors_table.setItem(row, 2, QtWidgets.QTableWidgetItem("WARMING UP"))
            self.sensors_table.setItem(row, 3, QtWidgets.QTableWidgetItem(f"0/{info['min_samples']}"))
            self.sensors_table.setItem(row, 4, QtWidgets.QTableWidgetItem("--"))
            lim = info["limits"]
            lim_str = f"[{lim[0]:g}, {lim[1]:g}]" if lim else "None"
            self.sensors_table.setItem(row, 5, QtWidgets.QTableWidgetItem(lim_str))

    def update(self, packet):
        """Called for every validated packet in the telemetry stream."""
        state, new_alerts = self.detector.process_packet(packet)

        # 1. Update Banner
        self._update_banner(state)

        # 2. Add New Alerts to Table & Plot
        for alert in new_alerts:
            self._add_alert_row(alert)
            self._add_plot_marker(alert)

        # 3. Update Sensors Summary Table
        fields = packet.fields if hasattr(packet, "fields") else packet
        self._update_sensors_table(fields)

    def _update_banner(self, state: str):
        total_alerts = len(self.detector.all_alerts)
        total_packets = self.detector._total_packets_processed
        summary_text = f"Packets: {total_packets} | Total Alerts: {total_alerts} | Window: {self.detector.window_size}"
        self.status_details.setText(summary_text)

        if state == AnomalyDetector.STATE_MONITORING:
            self.status_icon.setText("🟢")
            self.status_text.setText("STATUS: MONITORING (All Sensor Baselines Nominal)")
            self.status_text.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {COLOR_MONITORING};")
            self._apply_banner_style(COLOR_MONITORING)
        elif state == AnomalyDetector.STATE_ANOMALY:
            self.status_icon.setText("⚠️")
            self.status_text.setText("STATUS: POTENTIAL ANOMALY DETECTED")
            self.status_text.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {COLOR_ANOMALY};")
            self._apply_banner_style(COLOR_ANOMALY)
        elif state == AnomalyDetector.STATE_WARMING_UP:
            self.status_icon.setText("🔵")
            self.status_text.setText("STATUS: INSUFFICIENT BASELINE SAMPLES (Warming Up)")
            self.status_text.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {COLOR_WARMUP};")
            self._apply_banner_style(COLOR_WARMUP)
        elif state == AnomalyDetector.STATE_INVALID_DATA:
            self.status_icon.setText("🔴")
            self.status_text.setText("STATUS: INVALID SENSOR DATA (Corrupt / NaN / Outlier)")
            self.status_text.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {COLOR_CRITICAL};")
            self._apply_banner_style(COLOR_CRITICAL)

    def _add_alert_row(self, alert: AnomalyEvent):
        # Keep table within max rows
        if self.alerts_table.rowCount() >= self._max_table_rows:
            self.alerts_table.removeRow(self.alerts_table.rowCount() - 1)

        self.alerts_table.insertRow(0)
        items = [
            str(alert.timestamp),
            alert.sensor,
            f"{alert.value:.3f}" if isinstance(alert.value, float) else str(alert.value),
            alert.severity,
            alert.anomaly_type,
            alert.reason,
            str(alert.flight_state),
            str(alert.count),
        ]

        color = COLOR_CRITICAL if alert.severity == "CRITICAL" else COLOR_ANOMALY
        if alert.anomaly_type == "DATA_QUALITY":
            color = "#E040FB"

        for col, text in enumerate(items):
            item = QtWidgets.QTableWidgetItem(text)
            if col in (3, 4):
                item.setForeground(QtGui.QBrush(QtGui.QColor(color)))
                item.setFont(QtGui.QFont("Segoe UI", 9, QtGui.QFont.Bold))
            self.alerts_table.setItem(0, col, item)

    def _add_plot_marker(self, alert: AnomalyEvent):
        try:
            t = float(alert.timestamp)
        except (ValueError, TypeError):
            t = float(len(self._plot_times) + 1)

        sev_map = {"WARNING": 1.0, "CRITICAL": 2.0, "DATA_QUALITY": 3.0}
        sev_val = sev_map.get(alert.severity, sev_map.get(alert.anomaly_type, 1.5))
        brush_color = COLOR_CRITICAL if alert.severity == "CRITICAL" else COLOR_ANOMALY
        if alert.anomaly_type == "DATA_QUALITY":
            brush_color = "#E040FB"

        self._plot_times.append(t)
        self._plot_severity.append(sev_val)

        # Update scatter plot
        spots = [{'pos': (self._plot_times[i], self._plot_severity[i]),
                  'data': 1, 'brush': pg.mkBrush(brush_color), 'size': 9}
                 for i in range(len(self._plot_times))]
        self.scatter_item.setData(spots)

    def _update_sensors_table(self, fields: dict):
        summary = self.detector.get_sensor_summary()
        for row, (field, info) in enumerate(summary.items()):
            current_val = fields.get(field)
            val_str = f"{float(current_val):.2f}" if isinstance(current_val, (int, float)) else (str(current_val) if current_val is not None else "--")
            self.sensors_table.item(row, 1).setText(val_str)

            # Status column
            if not info["warmed_up"]:
                status_text = "WARMING UP"
                status_color = COLOR_WARMUP
            else:
                status_text = "NOMINAL"
                status_color = COLOR_MONITORING
            status_item = self.sensors_table.item(row, 2)
            status_item.setText(status_text)
            status_item.setForeground(QtGui.QBrush(QtGui.QColor(status_color)))

            # Samples count
            self.sensors_table.item(row, 3).setText(f"{info['samples']}/{info['min_samples']}")

            # Baseline info
            if info["samples"] > 0:
                base_str = f"{info['median']:.2f} ± {info['mad']:.2f}"
            else:
                base_str = "--"
            self.sensors_table.item(row, 4).setText(base_str)

    def _clear_alerts(self):
        self.alerts_table.setRowCount(0)
        self._plot_times.clear()
        self._plot_severity.clear()
        self.scatter_item.setData([])

    def reset(self):
        self.detector.reset()
        self._clear_alerts()
        self._update_banner(AnomalyDetector.STATE_WARMING_UP)
        self._init_sensors_table()
        logger.info("AnomalyDashboard baselines and alerts reset.")
