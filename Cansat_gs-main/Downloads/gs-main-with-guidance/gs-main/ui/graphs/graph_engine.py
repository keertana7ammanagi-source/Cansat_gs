"""
Interactive Graph Engine – Live plotting with axis selection, pause/resume, export.
"""
import csv
import os
from datetime import datetime

from PyQt5 import QtWidgets, QtCore
import pyqtgraph as pg
from pyqtgraph.exporters import ImageExporter

from core.telemetry.constants import FIELD_NAMES
from utils.logger import get_logger

logger = get_logger(__name__)


class GraphEngine(QtWidgets.QWidget):
    """
    A widget that displays a live plot with user-selectable X and Y axes.
    """
    def __init__(self, parent=None, buffer_size=300):
        super().__init__(parent)
        self.buffer_size = buffer_size
        self.paused = False
        self.data = {field: [] for field in FIELD_NAMES}
        self.x_field = "TIME_STAMPING"
        self.y_field = "ALTITUDE"
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(8)

        # Controls: X/Y selectors, buttons
        controls = QtWidgets.QHBoxLayout()
        controls.setSpacing(12)

        controls.addWidget(QtWidgets.QLabel("X-axis:"))
        self.x_combo = QtWidgets.QComboBox()
        self.x_combo.setMinimumWidth(150)
        self.x_combo.addItems(FIELD_NAMES)
        self.x_combo.setCurrentText(self.x_field)
        self.x_combo.currentTextChanged.connect(self._on_x_changed)
        controls.addWidget(self.x_combo)

        controls.addWidget(QtWidgets.QLabel("Y-axis:"))
        self.y_combo = QtWidgets.QComboBox()
        self.y_combo.setMinimumWidth(150)
        self.y_combo.addItems(FIELD_NAMES)
        self.y_combo.setCurrentText(self.y_field)
        self.y_combo.currentTextChanged.connect(self._on_y_changed)
        controls.addWidget(self.y_combo)

        self.pause_btn = QtWidgets.QPushButton("Pause")
        self.pause_btn.setCheckable(True)
        self.pause_btn.toggled.connect(self._toggle_pause)
        controls.addWidget(self.pause_btn)

        self.export_png_btn = QtWidgets.QPushButton("Export PNG")
        self.export_png_btn.clicked.connect(self._export_png)
        controls.addWidget(self.export_png_btn)

        self.export_csv_btn = QtWidgets.QPushButton("Export CSV")
        self.export_csv_btn.clicked.connect(self._export_csv)
        controls.addWidget(self.export_csv_btn)

        self.reset_btn = QtWidgets.QPushButton("Reset View")
        self.reset_btn.clicked.connect(self._reset_view)
        controls.addWidget(self.reset_btn)

        controls.addStretch()
        layout.addLayout(controls)

        # Plot widget
        self.plot_widget = pg.PlotWidget(title="Live Telemetry")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self.plot_widget.setBackground('#101a24')
        self.plot_widget.getAxis('left').setTextPen('w')
        self.plot_widget.getAxis('bottom').setTextPen('w')
        self.plot_widget.setLabel('left', '', color='#88aacc')
        self.plot_widget.setLabel('bottom', '', color='#88aacc')
        self.curve = self.plot_widget.plot(pen='y', width=1, symbol='o', symbolSize=4, symbolBrush='y', name='Data')
        layout.addWidget(self.plot_widget)

        # Status label
        self.status_label = QtWidgets.QLabel("Live | Points: 0")
        self.status_label.setStyleSheet("color: #6a8aaa; font-size: 12px;")
        layout.addWidget(self.status_label)

        # Store current data for export
        self.current_x_data = []
        self.current_y_data = []

        # Stylesheet for dropdowns
        self.setStyleSheet("""
            QComboBox {
                background: #1a2632;
                color: #c0d0e0;
                border: 1px solid #2a4a5a;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 13px;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left: 1px solid #2a4a5a;
            }
            QComboBox QAbstractItemView {
                background-color: #2a3a4a;
                color: #d0dce8;
                selection-background-color: #3a6a8a;
                selection-color: #ffffff;
                border: 1px solid #2a4a5a;
                font-size: 13px;
            }
            QComboBox QAbstractItemView::item {
                padding: 4px 8px;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #3a6a8a;
                color: #ffffff;
            }
        """)

    def _on_x_changed(self, new_x):
        self.x_field = new_x
        self._update_plot()

    def _on_y_changed(self, new_y):
        self.y_field = new_y
        self._update_plot()

    def _toggle_pause(self, checked):
        self.paused = checked
        self.pause_btn.setText("Resume" if checked else "Pause")
        self.status_label.setText("Paused" if checked else "Live")

    def update(self, packet):
        if self.paused:
            return

        for field in FIELD_NAMES:
            value = packet.get(field)
            if value is not None:
                self.data[field].append(value)
                if len(self.data[field]) > self.buffer_size:
                    self.data[field].pop(0)

        self._update_plot()

    def _update_plot(self):
        x_values = self.data.get(self.x_field, [])
        y_values = self.data.get(self.y_field, [])

        if self.x_field == "TIME_STAMPING":
            x_data = list(range(len(y_values)))
        else:
            try:
                x_data = [float(v) if v is not None else 0.0 for v in x_values]
            except (ValueError, TypeError):
                x_data = list(range(len(y_values)))
                logger.warning(f"Cannot convert {self.x_field} to float; using index.")

        try:
            y_data = [float(v) if v is not None else 0.0 for v in y_values]
        except (ValueError, TypeError):
            y_data = [0.0] * len(y_values)
            logger.warning(f"Cannot convert {self.y_field} to float; using zeros.")

        self.current_x_data = x_data
        self.current_y_data = y_data

        self.curve.setData(x_data, y_data)
        self.plot_widget.setLabel('bottom', self.x_field, color='#88aacc')
        self.plot_widget.setLabel('left', self.y_field, color='#88aacc')
        self.status_label.setText(f"Live | Points: {len(y_data)}")

    def _reset_view(self):
        self.plot_widget.autoRange()

    def _export_png(self):
        if not self.current_x_data:
            QtWidgets.QMessageBox.information(self, "Export PNG", "No data to export.")
            return

        export_dir = os.path.join(os.getcwd(), "data", "exports")
        os.makedirs(export_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"plot_{self.x_field}_vs_{self.y_field}_{timestamp}.png"
        filepath = os.path.join(export_dir, filename)

        try:
            exporter = ImageExporter(self.plot_widget.plotItem)
            exporter.export(filepath)
            logger.info(f"Plot exported to {filepath}")
            QtWidgets.QMessageBox.information(self, "Export PNG", f"Plot saved to:\n{filepath}")
        except Exception as e:
            logger.error(f"PNG export failed: {e}")
            QtWidgets.QMessageBox.critical(self, "Export Error", f"Failed to export PNG:\n{e}")

    def _export_csv(self):
        if not self.current_x_data:
            QtWidgets.QMessageBox.information(self, "Export CSV", "No data to export.")
            return

        export_dir = os.path.join(os.getcwd(), "data", "exports")
        os.makedirs(export_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"data_{self.x_field}_vs_{self.y_field}_{timestamp}.csv"
        filepath = os.path.join(export_dir, filename)

        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([self.x_field, self.y_field])
            for x, y in zip(self.current_x_data, self.current_y_data):
                writer.writerow([x, y])

        logger.info(f"Data exported to {filepath}")
        QtWidgets.QMessageBox.information(self, "Export CSV", f"Data saved to:\n{filepath}")

    def reset(self):
        for field in FIELD_NAMES:
            self.data[field] = []
        self.current_x_data = []
        self.current_y_data = []
        self.curve.clear()
        self.status_label.setText("Live | Points: 0")