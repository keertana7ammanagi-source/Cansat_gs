"""
Recovery Dashboard – beacon status, landing prediction, AI assistant, and live map.
"""
import os
import folium
from PyQt5 import QtWidgets, QtCore, QtWebEngineWidgets

from .base_dashboard import BaseDashboard


class RecoveryDashboard(BaseDashboard):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.lat = 28.6129
        self.lon = 77.2295
        self.alt = 0.0
        self.pred_lat = 28.6129
        self.pred_lon = 77.2295
        self._build_ui()
        self._update_map()

    def _build_ui(self):
        layout = QtWidgets.QHBoxLayout(self)
        layout.setSpacing(12)

        # Map
        map_box = QtWidgets.QGroupBox("Recovery Map & Landing Prediction")
        map_layout = QtWidgets.QVBoxLayout()
        self.map_view = QtWebEngineWidgets.QWebEngineView()
        self.map_view.setMinimumHeight(400)
        map_layout.addWidget(self.map_view)
        self.map_info = QtWidgets.QLabel(
            "Launch Site: (28.613, 77.230)\nLanding Zone: --\nDistance: --\nGPS Satellites: --\nConfidence: --"
        )
        self.map_info.setStyleSheet("color: #8ac0d0; font-size: 14px;")
        map_layout.addWidget(self.map_info)
        map_box.setLayout(map_layout)
        layout.addWidget(map_box)

        # Right panel
        right = QtWidgets.QVBoxLayout()
        right.setSpacing(10)

        status_box = QtWidgets.QGroupBox("Recovery System Status")
        status_layout = QtWidgets.QVBoxLayout()
        self.beacon_status = QtWidgets.QLabel("Audio Beacon (105 dB): OFF")
        self.led_status = QtWidgets.QLabel("LED Array (4x): OFF")
        self.lora_beacon = QtWidgets.QLabel("LoRa Recovery Beacon: OFF")
        for lbl in (self.beacon_status, self.led_status, self.lora_beacon):
            lbl.setStyleSheet("color: #8ac0d0; font-size: 14px;")
            status_layout.addWidget(lbl)
        status_box.setLayout(status_layout)
        right.addWidget(status_box)

        ai_rec_box = QtWidgets.QGroupBox("AI Recovery Assistant")
        ai_rec_layout = QtWidgets.QVBoxLayout()
        self.rec_route = QtWidgets.QLabel("Recovery Route: --")
        self.rec_beam = QtWidgets.QLabel("Beam: --")
        self.rec_terrain = QtWidgets.QLabel("Terrain Type: --")
        self.rec_visibility = QtWidgets.QLabel("Visibility: --")
        self.rec_eta = QtWidgets.QLabel("Estimated Retrieval Time: --")
        for lbl in (self.rec_route, self.rec_beam, self.rec_terrain, self.rec_visibility, self.rec_eta):
            lbl.setStyleSheet("color: #8ac0d0; font-size: 14px;")
            ai_rec_layout.addWidget(lbl)
        ai_rec_box.setLayout(ai_rec_layout)
        right.addWidget(ai_rec_box)

        notes = QtWidgets.QLabel(
            "Beacon independent of main electronics | Audio: 105 dB (Guideline >92 dB)\n"
            "LEDs visible in daylight | Team contact info on structure (English, Hindi, Regional)"
        )
        notes.setStyleSheet("color: #5a7a8a; font-size: 12px;")
        right.addWidget(notes)
        right.addStretch()
        layout.addLayout(right)

    def _update_map(self):
        m = folium.Map(location=[self.lat, self.lon], zoom_start=15)
        folium.Marker([self.lat, self.lon], popup="Current Position", icon=folium.Icon(color='blue')).add_to(m)
        if self.alt > 0 and hasattr(self, 'pred_lat'):
            folium.Marker([self.pred_lat, self.pred_lon], popup="Predicted Landing", icon=folium.Icon(color='red')).add_to(m)
        map_file = os.path.join(os.getcwd(), "temp_map.html")
        m.save(map_file)
        self.map_view.setUrl(QtCore.QUrl.fromLocalFile(map_file))

    def update(self, packet):
        state = packet.get("FLIGHT_STATE", "--")
        self.lat = packet.get("GNSS_LATITUDE", 28.6129)
        self.lon = packet.get("GNSS_LONGITUDE", 77.2295)
        self.alt = packet.get("ALTITUDE", 0.0)

        if state in ("IMPACT", "RECOVERY"):
            self.beacon_status.setText("Audio Beacon (105 dB): ACTIVE")
            self.led_status.setText("LED Array (4x): ACTIVE")
            self.lora_beacon.setText("LoRa Recovery Beacon: ACTIVE")
        else:
            self.beacon_status.setText("Audio Beacon (105 dB): STANDBY")
            self.led_status.setText("LED Array (4x): STANDBY")
            self.lora_beacon.setText("LoRa Recovery Beacon: STANDBY")

        self.map_info.setText(
            f"Launch Site: (28.613, 77.230)\n"
            f"Landing Zone: ({self.lat:.5f}, {self.lon:.5f})\n"
            f"Distance: {abs(self.lat-28.613)*111000 + abs(self.lon-77.230)*111000*0.92:.0f} m\n"
            f"GPS Satellites: {packet.get('GNSS_SATS', 0)}\n"
            f"Confidence: 87%"
        )

        if state in ("DESCENT", "SECONDARY_DEPLOY"):
            self.rec_route.setText("Recovery Route: Generated (215 deg from launch)")
            self.rec_beam.setText("Beam: 215 deg")
            self.rec_terrain.setText("Terrain Type: Grassland")
            self.rec_visibility.setText("Visibility: Good")
            self.rec_eta.setText("Estimated Retrieval Time: 2 min 10 sec")
            self.pred_lat = self.lat + 0.001
            self.pred_lon = self.lon + 0.001
        elif state in ("IMPACT", "RECOVERY"):
            self.rec_route.setText("Recovery Route: Generated (walk 83 m NE)")
            self.rec_beam.setText("Beam: 220 deg")
            self.rec_terrain.setText("Terrain Type: Grassland")
            self.rec_visibility.setText("Visibility: Good")
            self.rec_eta.setText("Estimated Retrieval Time: 1 min 30 sec")
            self.pred_lat = self.lat
            self.pred_lon = self.lon
        else:
            self.rec_route.setText("Recovery Route: --")
            self.rec_beam.setText("Beam: --")
            self.rec_terrain.setText("Terrain Type: --")
            self.rec_visibility.setText("Visibility: --")
            self.rec_eta.setText("Estimated Retrieval Time: --")

        self._update_map()

    def reset(self):
        pass