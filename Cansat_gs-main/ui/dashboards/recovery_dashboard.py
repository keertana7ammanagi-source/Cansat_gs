"""Recovery dashboard with an embedded, network-free GNSS track view."""
from math import asin, cos, isfinite, radians, sin, sqrt

from PyQt5 import QtCore, QtWidgets
try:
    from PyQt5 import QtWebEngineWidgets
    HAS_WEBENGINE = True
except ImportError:
    QtWebEngineWidgets = None
    HAS_WEBENGINE = False


from .base_dashboard import BaseDashboard


def _distance_m(lat1, lon1, lat2, lon2):
    """Great-circle distance between two WGS84 coordinates."""
    radius_m = 6_371_000
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * radius_m * asin(sqrt(min(1.0, max(0.0, a))))


class RecoveryDashboard(BaseDashboard):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.lat = None
        self.lon = None
        self.alt = None
        self.satellites = None
        self.track = []
        self.origin = None
        self._build_ui()
        self._update_map()

    def _build_ui(self):
        layout = QtWidgets.QHBoxLayout(self)
        layout.setSpacing(12)

        map_box = QtWidgets.QGroupBox("Offline GNSS Track")
        map_layout = QtWidgets.QVBoxLayout()
        if HAS_WEBENGINE:
            self.map_view = QtWebEngineWidgets.QWebEngineView()
            self.map_view.setMinimumHeight(400)
            map_layout.addWidget(self.map_view)
        else:
            self.map_view = None
            placeholder = QtWidgets.QLabel("GNSS Track view (QtWebEngine unavailable on this Python environment)")
            placeholder.setStyleSheet("color: #6a8aaa; font-style: italic; padding: 20px;")
            map_layout.addWidget(placeholder)
        self.map_info = QtWidgets.QLabel("Waiting for a valid GNSS fix")
        self.map_info.setStyleSheet("color: #8ac0d0; font-size: 14px;")
        map_layout.addWidget(self.map_info)
        map_box.setLayout(map_layout)
        layout.addWidget(map_box)

        right = QtWidgets.QVBoxLayout()
        right.setSpacing(10)

        status_box = QtWidgets.QGroupBox("Recovery System Status")
        status_layout = QtWidgets.QVBoxLayout()
        self.beacon_status = QtWidgets.QLabel("Audio Beacon: status not reported")
        self.led_status = QtWidgets.QLabel("LED Array: status not reported")
        self.lora_beacon = QtWidgets.QLabel("LoRa Recovery Beacon: status not reported")
        for label in (self.beacon_status, self.led_status, self.lora_beacon):
            label.setStyleSheet("color: #8ac0d0; font-size: 14px;")
            status_layout.addWidget(label)
        status_box.setLayout(status_layout)
        right.addWidget(status_box)

        note = QtWidgets.QLabel(
            "The track is drawn from received GNSS fixes and uses no online map tiles.\n"
            "It shows position history; it does not infer wind or predict touchdown."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #8ac0d0; font-size: 12px;")
        right.addWidget(note)
        right.addStretch()
        layout.addLayout(right)

    def _update_map(self):
        if not self.track:
            body = '<text x="400" y="220" text-anchor="middle" fill="#8ac0d0">Waiting for GNSS data</text>'
            info = "Waiting for a valid GNSS fix"
        else:
            width, height, margin = 800, 440, 48
            lats = [point[0] for point in self.track]
            lons = [point[1] for point in self.track]
            span_lat = max(max(lats) - min(lats), 0.00005)
            span_lon = max(max(lons) - min(lons), 0.00005)
            pad_lat, pad_lon = span_lat * 0.15, span_lon * 0.15
            min_lat, max_lat = min(lats) - pad_lat, max(lats) + pad_lat
            min_lon, max_lon = min(lons) - pad_lon, max(lons) + pad_lon

            def project(point):
                lat, lon = point
                x = margin + (lon - min_lon) / (max_lon - min_lon) * (width - 2 * margin)
                y = height - margin - (lat - min_lat) / (max_lat - min_lat) * (height - 2 * margin)
                return x, y

            plotted = [project(point) for point in self.track]
            path_points = " ".join(f"{x:.1f},{y:.1f}" for x, y in plotted)
            first_x, first_y = plotted[0]
            last_x, last_y = plotted[-1]
            body = (
                '<g stroke="#355066" stroke-width="1">'
                f'<path d="M{margin} {height-margin} H{width-margin} M{margin} {margin} V{height-margin}"/>'
                f'<path d="M{width/2} {margin} V{height-margin} M{margin} {height/2} H{width-margin}" stroke-dasharray="4 6"/>'
                '</g>'
                f'<polyline points="{path_points}" fill="none" stroke="#f4c95d" stroke-width="3"/>'
                f'<circle cx="{first_x:.1f}" cy="{first_y:.1f}" r="7" fill="#58a6ff"/>'
                f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="8" fill="#ff6b6b"/>'
                f'<text x="{margin}" y="{height-12}" fill="#8ac0d0">{min_lat:.5f}° lat</text>'
                f'<text x="{width-margin}" y="{height-12}" text-anchor="end" fill="#8ac0d0">{max_lon:.5f}° lon</text>'
                '<text x="60" y="36" fill="#58a6ff">Track start</text>'
                '<text x="145" y="36" fill="#ff6b6b">Latest fix</text>'
            )
            origin_lat, origin_lon = self.origin
            distance = _distance_m(origin_lat, origin_lon, self.lat, self.lon)
            info = (
                f"Latest fix: {self.lat:.6f}, {self.lon:.6f}  |  "
                f"Altitude: {self.alt:.1f} m  |  GNSS satellites: {self.satellites}  |  "
                f"Distance from first fix: {distance:.1f} m"
            )

        html = (
            '<!doctype html><html><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<style>html,body{margin:0;background:#101a24;color:#d0dce8;font-family:Arial,sans-serif}'
            'svg{width:100%;height:100vh;min-height:400px}</style></head><body>'
            f'<svg viewBox="0 0 800 440" role="img" aria-label="Offline GNSS track">'
            f'<rect width="800" height="440" fill="#101a24"/>{body}</svg></body></html>'
        )
        self.map_info.setText(info)
        if self.map_view is not None:
            self.map_view.setHtml(html, QtCore.QUrl("about:blank"))


    def update(self, packet):
        # The current telemetry schema has no beacon/LED status fields.
        # Flight state alone does not prove those devices activated.

        lat = packet.get("GNSS_LATITUDE")
        lon = packet.get("GNSS_LONGITUDE")
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError):
            return
        if not (isfinite(lat) and isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            return

        self.lat, self.lon = lat, lon
        if self.origin is None:
            self.origin = (lat, lon)
        self.alt = float(packet.get("ALTITUDE") or 0.0)
        self.satellites = packet.get("GNSS_SATS", "--")
        self.track.append((lat, lon))
        if len(self.track) > 600:
            self.track.pop(0)
        self._update_map()

    def reset(self):
        self.lat = self.lon = self.alt = None
        self.satellites = None
        self.track.clear()
        self.origin = None
        self._update_map()
