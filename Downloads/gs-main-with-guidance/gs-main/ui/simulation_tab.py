"""
Simulation Control Tab – Start/stop synthetic simulation or replay CSV.
"""
import os
from PyQt5 import QtWidgets, QtCore

from simulation.simulation_engine import SimulationEngine
from utils.logger import get_logger

logger = get_logger(__name__)


class SimulationTab(QtWidgets.QWidget):
    """
    Provides controls for simulation and replay.
    """
    def __init__(self, parent=None, packet_callback=None):
        super().__init__(parent)
        self.packet_callback = packet_callback
        self.engine = SimulationEngine()
        self.engine.packet_ready.connect(self._on_packet)
        self.engine.status_updated.connect(self._on_status)

        self._build_ui()
        self._update_ui_state(False)

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(15)

        title = QtWidgets.QLabel("SIMULATION & REPLAY CONTROL")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #88aacc;")
        layout.addWidget(title)

        # Buttons row
        btn_layout = QtWidgets.QHBoxLayout()
        self.synth_btn = QtWidgets.QPushButton("Start Synthetic")
        self.synth_btn.clicked.connect(self._start_synthetic)
        btn_layout.addWidget(self.synth_btn)

        self.replay_btn = QtWidgets.QPushButton("Load CSV & Replay")
        self.replay_btn.clicked.connect(self._load_replay)
        btn_layout.addWidget(self.replay_btn)

        self.pause_btn = QtWidgets.QPushButton("Pause")
        self.pause_btn.setCheckable(True)
        self.pause_btn.toggled.connect(self._toggle_pause)
        btn_layout.addWidget(self.pause_btn)

        self.stop_btn = QtWidgets.QPushButton("Stop")
        self.stop_btn.clicked.connect(self._stop)
        btn_layout.addWidget(self.stop_btn)

        layout.addLayout(btn_layout)

        # Speed control
        speed_layout = QtWidgets.QHBoxLayout()
        speed_layout.addWidget(QtWidgets.QLabel("Speed:"))
        self.speed_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.speed_slider.setMinimum(1)
        self.speed_slider.setMaximum(10)
        self.speed_slider.setValue(1)
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        speed_layout.addWidget(self.speed_slider)
        self.speed_label = QtWidgets.QLabel("1.0x")
        speed_layout.addWidget(self.speed_label)
        layout.addLayout(speed_layout)

        # Status
        self.status_label = QtWidgets.QLabel("Ready")
        self.status_label.setStyleSheet("color: #6a8aaa; font-size: 14px;")
        layout.addWidget(self.status_label)

        # Log area
        self.log_text = QtWidgets.QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.setStyleSheet("background: #0a1016; color: #8ac0d0; font-family: monospace;")
        layout.addWidget(self.log_text)

        layout.addStretch()

    def _update_ui_state(self, is_running):
        self.synth_btn.setEnabled(not is_running)
        self.replay_btn.setEnabled(not is_running)
        self.pause_btn.setEnabled(is_running)
        self.stop_btn.setEnabled(is_running)
        self.speed_slider.setEnabled(is_running)

    def _start_synthetic(self):
        self.log_text.append("Starting synthetic simulation...")
        self.engine.start_synthetic()
        self._update_ui_state(True)

    def _load_replay(self):
        filepath, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select CSV file for replay", "", "CSV Files (*.csv)"
        )
        if filepath:
            self.log_text.append(f"Loading replay: {os.path.basename(filepath)}")
            self.engine.start_replay(filepath)
            self._update_ui_state(True)

    def _toggle_pause(self, checked):
        self.engine.pause()
        self.log_text.append("Paused" if checked else "Resumed")

    def _stop(self):
        self.engine.stop()
        self._update_ui_state(False)
        self.log_text.append("Stopped.")

    def _on_speed_changed(self, value):
        speed = value / 2.0  # 0.5x to 5.0x
        self.speed_label.setText(f"{speed:.1f}x")
        self.engine.set_speed(speed)

    def _on_packet(self, raw_line):
        if self.packet_callback:
            self.packet_callback(raw_line)
        else:
            # If no callback, just log
            self.log_text.append(f"Packet: {raw_line[:80]}...")

    def _on_status(self, msg):
        self.status_label.setText(msg)
        self.log_text.append(f"Status: {msg}")

    def closeEvent(self, event):
        self.engine.stop()
        event.accept()