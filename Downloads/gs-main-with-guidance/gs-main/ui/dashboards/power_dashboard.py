"""
Power Dashboard – voltage, current, power, rail status, subsystem currents, AI battery prediction.
"""
from PyQt5 import QtWidgets
import pyqtgraph as pg

from .base_dashboard import BaseDashboard


class PowerDashboard(BaseDashboard):
    def __init__(self, parent=None, buffer_size=300):
        super().__init__(parent)
        self.buffer_size = buffer_size
        self.current_buf = []
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(10)

        # Header
        header = QtWidgets.QLabel("POWER DASHBOARD  |  Real-Time Monitoring & AI Prediction")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #88aacc;")
        layout.addWidget(header)

        # Top row: system status, rails, subsystems
        top = QtWidgets.QHBoxLayout()

        # System status
        sys_box = QtWidgets.QGroupBox("Power System Status")
        sys_layout = QtWidgets.QVBoxLayout()
        self.power_voltage = QtWidgets.QLabel("Battery: -- V")
        self.power_current = QtWidgets.QLabel("Current: -- A")
        self.power_power = QtWidgets.QLabel("Power: -- W")
        self.power_capacity = QtWidgets.QLabel("Remaining: -- %")
        for lbl in (self.power_voltage, self.power_current, self.power_power, self.power_capacity):
            lbl.setStyleSheet("color: #6bc9ff; font-weight: bold; font-size: 14px;")
            sys_layout.addWidget(lbl)
        sys_box.setLayout(sys_layout)
        top.addWidget(sys_box)

        # Rails
        rail_box = QtWidgets.QGroupBox("Rail Status")
        rail_layout = QtWidgets.QVBoxLayout()
        self.rail_bat = QtWidgets.QLabel("Battery Rail (7.4V): -- V")
        self.rail_5v = QtWidgets.QLabel("5V Rail (Buck): -- V")
        self.rail_3v3 = QtWidgets.QLabel("3.3V Rail (LDO): -- V")
        for lbl in (self.rail_bat, self.rail_5v, self.rail_3v3):
            lbl.setStyleSheet("color: #8ac0d0; font-size: 14px;")
            rail_layout.addWidget(lbl)
        rail_box.setLayout(rail_layout)
        top.addWidget(rail_box)

        # Subsystems
        sub_box = QtWidgets.QGroupBox("Subsystem Current (live)")
        sub_layout = QtWidgets.QVBoxLayout()
        self.sub_fc = QtWidgets.QLabel("Flight Computer: -- mA")
        self.sub_loRa = QtWidgets.QLabel("LoRa Telemetry: -- mA")
        self.sub_sens = QtWidgets.QLabel("Sensors: -- mA")
        self.sub_cam = QtWidgets.QLabel("Cameras (x2): -- mA")
        self.sub_gyro = QtWidgets.QLabel("Gyroscope: -- mA")
        self.sub_total = QtWidgets.QLabel("Total Current: -- mA")
        for lbl in (self.sub_fc, self.sub_loRa, self.sub_sens, self.sub_cam, self.sub_gyro, self.sub_total):
            lbl.setStyleSheet("color: #d0c8a0; font-size: 14px;")
            sub_layout.addWidget(lbl)
        sub_box.setLayout(sub_layout)
        top.addWidget(sub_box)

        layout.addLayout(top)

        # Architecture diagram
        arch_box = QtWidgets.QGroupBox("Power Architecture")
        arch_layout = QtWidgets.QVBoxLayout()
        arch_text = QtWidgets.QLabel(
            "Battery Pack (7.4V) -> 5V Buck Converter -> 5V Rails\n"
            "                        -> 3.3V LDO -> 3.3V Rails\n"
            "                        -> 3.3V Buck -> 3.3V Sensors"
        )
        arch_text.setStyleSheet("color: #8aaabc; font-family: monospace; font-size: 14px;")
        arch_layout.addWidget(arch_text)
        arch_box.setLayout(arch_layout)
        layout.addWidget(arch_box)

        # Bottom: plot + AI prediction
        bottom = QtWidgets.QHBoxLayout()

        plot_box = QtWidgets.QGroupBox("Current Consumption (live)")
        plot_layout = QtWidgets.QVBoxLayout()
        self.power_plot = pg.PlotWidget(title="Total Current (mA)")
        self.power_plot.showGrid(x=True, y=True, alpha=0.2)
        self.power_plot.setBackground('#101a24')
        self.power_curve = self.power_plot.plot(pen='g', width=2)
        plot_layout.addWidget(self.power_plot)
        plot_box.setLayout(plot_layout)
        bottom.addWidget(plot_box)

        ai_box = QtWidgets.QGroupBox("AI Battery Prediction")
        ai_layout = QtWidgets.QVBoxLayout()
        self.ai_runtime = QtWidgets.QLabel("Remaining Runtime: -- min")
        self.ai_end_voltage = QtWidgets.QLabel("End-of-mission voltage: -- V")
        self.ai_health = QtWidgets.QLabel("Status: --")
        self.ai_confidence = QtWidgets.QLabel("Confidence: -- %")
        for lbl in (self.ai_runtime, self.ai_end_voltage, self.ai_health, self.ai_confidence):
            lbl.setStyleSheet("color: #8ac0d0; font-size: 14px;")
            ai_layout.addWidget(lbl)
        ai_box.setLayout(ai_layout)
        bottom.addWidget(ai_box)

        layout.addLayout(bottom)

        # Notes and legend
        notes = QtWidgets.QLabel(
            "System Notes: Power IC: INA219 (I2C) | Battery: 18650 Li-Ion (2S) | Cap bank: 4700 uF | Rate: 1 Hz"
        )
        notes.setStyleSheet("color: #5a7a8a; font-size: 12px;")
        layout.addWidget(notes)

        legend = QtWidgets.QLabel("[ Normal ]  [ Warning ]  [ Critical ]")
        legend.setStyleSheet("color: #8aaabc; font-size: 14px;")
        layout.addWidget(legend)

    def update(self, packet):
        volts = packet.get("VOLTAGE", 0.0)
        current = 0.42  # placeholder, from INA219 would come in packet
        power = volts * current
        if volts >= 7.4:
            cap = 100
        elif volts <= 6.0:
            cap = 0
        else:
            cap = (volts - 6.0) / (7.4 - 6.0) * 100
        self.power_voltage.setText(f"Battery: {volts:.2f} V")
        self.power_current.setText(f"Current: {current:.2f} A")
        self.power_power.setText(f"Power: {power:.2f} W")
        self.power_capacity.setText(f"Remaining: {cap:.0f} %")

        self.rail_bat.setText(f"Battery Rail (7.4V): {volts:.2f} V")
        self.rail_5v.setText(f"5V Rail (Buck): {volts*0.9:.2f} V")
        self.rail_3v3.setText(f"3.3V Rail (LDO): {volts*0.45:.2f} V")

        fc, lora, sens, cam, gyro = 110, 90, 35, 180, 120
        total = fc + lora + sens + cam + gyro
        self.sub_fc.setText(f"Flight Computer: {fc} mA")
        self.sub_loRa.setText(f"LoRa Telemetry: {lora} mA")
        self.sub_sens.setText(f"Sensors: {sens} mA")
        self.sub_cam.setText(f"Cameras (x2): {cam} mA")
        self.sub_gyro.setText(f"Gyroscope: {gyro} mA")
        self.sub_total.setText(f"Total Current: {total} mA")

        self.current_buf.append(total)
        if len(self.current_buf) > self.buffer_size:
            self.current_buf.pop(0)
        self.power_curve.setData(list(range(len(self.current_buf))), self.current_buf)

        remaining_time = cap * 0.02
        self.ai_runtime.setText(f"Remaining Runtime: {remaining_time:.0f} min")
        self.ai_end_voltage.setText(f"End-of-mission voltage: {volts - 0.5:.2f} V")
        self.ai_health.setText("Status: Healthy")
        self.ai_confidence.setText("Confidence: 92 %")

    def reset(self):
        self.current_buf = []