"""
ui/dashboards/guidance_dashboard.py

Displays the LandingController's decisions. This widget does NOT compute
anything itself -- it only renders whatever MainWindow hands it via
update_guidance(). Keeping the dashboard "dumb" is deliberate: the GUI
should never be responsible for flight-control logic (see write-up).

Drop this next to your other dashboards, e.g.:

    ui/dashboards/
        base_dashboard.py
        telemetry_dashboard.py
        power_dashboard.py
        guidance_dashboard.py   <-- this file

Wire it up in MainWindow the same way as your other dashboards:

    from ui.dashboards.guidance_dashboard import GuidanceDashboard

    self.guidance_dashboard = GuidanceDashboard()
    self.tabs.addTab(wrap_with_scroll(self.guidance_dashboard), "Guidance")
    ...
    # in your telemetry handler, after the LandingController runs:
    self.guidance_dashboard.update_guidance(packet, guidance_result, servo_deg)

If your project's BaseDashboard import path differs, adjust the import
below to match (e.g. `from .base_dashboard import BaseDashboard`).
"""

from PyQt5 import QtCore, QtWidgets, QtGui

from .base_dashboard import BaseDashboard


def _make_row(grid, row, label_text):
    label = QtWidgets.QLabel(label_text)
    label.setStyleSheet("font-weight: bold;")
    value = QtWidgets.QLabel("--")
    value.setAlignment(QtCore.Qt.AlignRight)
    grid.addWidget(label, row, 0)
    grid.addWidget(value, row, 1)
    return value


class GuidanceDashboard(BaseDashboard):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QtWidgets.QVBoxLayout(self)

        box = QtWidgets.QGroupBox("PRECISION LANDING")
        grid = QtWidgets.QGridLayout(box)

        self.val_altitude = _make_row(grid, 0, "Altitude")
        self.val_distance = _make_row(grid, 1, "Target Distance")
        self.val_xtrack = _make_row(grid, 2, "Cross Track Error")
        self.val_xtrack_side = _make_row(grid, 3, "Correction Side")
        self.val_wind_speed = _make_row(grid, 4, "Wind / Drift Speed")
        self.val_wind_dir = _make_row(grid, 5, "Wind / Drift Direction")
        self.val_flight_state = _make_row(grid, 6, "Flight State")
        self.val_command = _make_row(grid, 7, "Current Command")
        self.val_servo = _make_row(grid, 8, "Servo Position")
        self.val_status = _make_row(grid, 9, "Guidance Status")
        self.val_reason = _make_row(grid, 10, "Reason")

        layout.addWidget(box)

        # --- Target entry ---
        target_box = QtWidgets.QGroupBox("LANDING TARGET")
        target_grid = QtWidgets.QGridLayout(target_box)

        target_grid.addWidget(QtWidgets.QLabel("Latitude"), 0, 0)
        self.target_lat_input = QtWidgets.QLineEdit()
        target_grid.addWidget(self.target_lat_input, 0, 1)

        target_grid.addWidget(QtWidgets.QLabel("Longitude"), 1, 0)
        self.target_lon_input = QtWidgets.QLineEdit()
        target_grid.addWidget(self.target_lon_input, 1, 1)

        self.set_target_btn = QtWidgets.QPushButton("SET TARGET")
        target_grid.addWidget(self.set_target_btn, 2, 0, 1, 2)

        layout.addWidget(target_box)

        # --- Mode / override ---
        mode_box = QtWidgets.QGroupBox("MODE")
        mode_layout = QtWidgets.QHBoxLayout(mode_box)

        self.auto_btn = QtWidgets.QPushButton("AUTO")
        self.auto_btn.setCheckable(True)
        self.auto_btn.setChecked(True)

        self.manual_btn = QtWidgets.QPushButton("MANUAL")
        self.manual_btn.setCheckable(True)

        mode_group = QtWidgets.QButtonGroup(self)
        mode_group.addButton(self.auto_btn)
        mode_group.addButton(self.manual_btn)
        mode_group.setExclusive(True)

        mode_layout.addWidget(self.auto_btn)
        mode_layout.addWidget(self.manual_btn)
        layout.addWidget(mode_box)

        override_box = QtWidgets.QGroupBox("MANUAL OVERRIDE")
        override_layout = QtWidgets.QHBoxLayout(override_box)

        self.manual_glide_left_btn = QtWidgets.QPushButton("GLIDE LEFT")
        self.manual_hover_btn = QtWidgets.QPushButton("HOVER")
        self.manual_glide_right_btn = QtWidgets.QPushButton("GLIDE RIGHT")

        for btn in (
            self.manual_glide_left_btn,
            self.manual_hover_btn,
            self.manual_glide_right_btn,
        ):
            btn.setEnabled(False)  # only usable in MANUAL mode
            override_layout.addWidget(btn)

        layout.addWidget(override_box)

        self.manual_btn.toggled.connect(self._on_mode_toggled)

        layout.addStretch()

        self._flash_timer = QtCore.QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._clear_command_flash)

    # ------------------------------------------------------------------

    def _on_mode_toggled(self, manual_checked):
        for btn in (
            self.manual_glide_left_btn,
            self.manual_hover_btn,
            self.manual_glide_right_btn,
        ):
            btn.setEnabled(manual_checked)

    def update(self, packet):
        """
        BaseDashboard's expected hook. Left as a no-op/basic display
        since guidance needs the controller's decision too -- MainWindow
        should call update_guidance() (below) instead, right after
        running the LandingController. This override just keeps the
        widget consistent with BaseDashboard's interface.
        """
        alt = packet.get("ALTITUDE", 0.0)
        self.val_altitude.setText(f"{alt:.1f} m")
        state = packet.get("FLIGHT_STATE", "--")
        self.val_flight_state.setText(str(state))

    def update_guidance(self, packet, guidance_result, servo_deg=None):
        """
        packet:           the TelemetryPacket (for altitude/flight state)
        guidance_result:  the dict returned by LandingController.update()
        servo_deg:        optional last commanded servo angle, if known
        """
        alt = packet.get("ALTITUDE", 0.0)
        state = packet.get("FLIGHT_STATE", "--")

        self.val_altitude.setText(f"{alt:.1f} m")
        self.val_flight_state.setText(str(state))
        self.val_distance.setText(f"{guidance_result['distance_m']:.1f} m")
        self.val_xtrack.setText(f"{guidance_result['cross_track_m']:.1f} m")

        sign = guidance_result["cross_track_sign"]
        side = "RIGHT of path" if sign > 0 else ("LEFT of path" if sign < 0 else "on path")
        self.val_xtrack_side.setText(side)

        command = guidance_result["command"]
        self.val_command.setText(command)
        self.val_reason.setText(guidance_result.get("reason", ""))

        if servo_deg is not None:
            self.val_servo.setText(f"{servo_deg}°")

        if guidance_result["transmit"]:
            self.val_status.setText("ACTIVE — command sent")
            self.val_command.setStyleSheet("font-weight: bold; color: #2ecc71;")
            self._flash_timer.start(1500)
        else:
            self.val_status.setText("ACTIVE — holding" if command != "HOVER" else "ACTIVE")

    def update_wind(self, speed_m_s, direction_deg):
        self.val_wind_speed.setText(f"{speed_m_s:.1f} m/s")
        self.val_wind_dir.setText(f"{direction_deg:.0f}°")

    def _clear_command_flash(self):
        self.val_command.setStyleSheet("")

    def reset(self):
        for label in (
            self.val_altitude, self.val_distance, self.val_xtrack,
            self.val_xtrack_side, self.val_wind_speed, self.val_wind_dir,
            self.val_flight_state, self.val_command, self.val_servo,
            self.val_status, self.val_reason,
        ):
            label.setText("--")
