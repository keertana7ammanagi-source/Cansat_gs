"""Deterministic GNSS ground-motion and descent-stability estimates."""
from math import asin, atan2, cos, degrees, isfinite, radians, sin, sqrt


def haversine(lat1, lon1, lat2, lon2):
    radius_m = 6_371_000
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * radius_m * asin(sqrt(a))


class WindEstimator:
    """Estimate horizontal ground velocity from timestamped GNSS fixes.

    GNSS ground motion is not a direct wind measurement. The legacy result
    keys are retained for report compatibility, but UI labels should say
    ground drift/track.
    """

    def __init__(self):
        self.prev_lat = None
        self.prev_lon = None
        self.prev_time = None

    def update(self, packet):
        try:
            lat = float(packet.get("GNSS_LATITUDE"))
            lon = float(packet.get("GNSS_LONGITUDE"))
            timestamp = float(packet.get("TIME_STAMPING"))
        except (TypeError, ValueError):
            return {"available": False}
        if not (isfinite(lat) and isfinite(lon) and isfinite(timestamp)
                and -90 <= lat <= 90 and -180 <= lon <= 180):
            return {"available": False}

        previous = (self.prev_lat, self.prev_lon, self.prev_time)
        self.prev_lat, self.prev_lon, self.prev_time = lat, lon, timestamp
        if previous[0] is None or timestamp <= previous[2]:
            return {"available": False}

        prev_lat, prev_lon, prev_time = previous
        dt = timestamp - prev_time
        north_m = radians(lat - prev_lat) * 6_371_000
        east_m = radians(lon - prev_lon) * 6_371_000 * cos(radians((lat + prev_lat) / 2))
        speed = sqrt(east_m * east_m + north_m * north_m) / dt
        bearing = degrees(atan2(east_m, north_m)) % 360
        return {
            "available": True,
            "ground_speed_mps": speed,
            "ground_track_deg": bearing,
            "wind_speed_mps": speed,  # legacy key; value is ground speed
            "wind_direction_deg": bearing,  # legacy key; value is track bearing
        }


class StabilityMonitor:
    def __init__(self, window=20):
        self.window = window
        self.accel_history = []
        self.stability_index = 100.0

    def update(self, packet):
        # Older packet formats use R/P/Y aliases; current packets split
        # ACCELEROMETER_DATA into XYZ in add_legacy_aliases().
        values = (
            packet.get("ACCEL_X", packet.get("ACCEL_R", 0)),
            packet.get("ACCEL_Y", packet.get("ACCEL_P", 0)),
            packet.get("ACCEL_Z", packet.get("ACCEL_Y", 0)),
        )
        try:
            sample = tuple(float(value) for value in values)
        except (TypeError, ValueError):
            return {"stability_index": self.stability_index}

        self.accel_history.append(sample)
        self.accel_history = self.accel_history[-self.window:]
        if len(self.accel_history) >= 5:
            means = [sum(sample[i] for sample in self.accel_history) / len(self.accel_history) for i in range(3)]
            variances = [
                sum((sample[i] - means[i]) ** 2 for sample in self.accel_history) / len(self.accel_history)
                for i in range(3)
            ]
            mean_std = sum(sqrt(value) for value in variances) / 3
            self.stability_index = max(0.0, 100.0 - (mean_std / 2.0) * 100.0)
        return {"stability_index": self.stability_index}

    def stability_index_percent(self):
        return self.stability_index


def estimate_landing_drift(lat, lon, alt, descent_rate_mps, ground_speed_mps, ground_track_deg):
    """Linearly extrapolate the last horizontal GNSS velocity to ground."""
    try:
        lat, lon, alt = float(lat), float(lon), float(alt)
        descent_rate_mps = float(descent_rate_mps)
        ground_speed_mps = float(ground_speed_mps)
        ground_track_deg = float(ground_track_deg)
    except (TypeError, ValueError):
        return {"available": False}
    if not (
        all(isfinite(value) for value in (lat, lon, alt, descent_rate_mps, ground_speed_mps, ground_track_deg))
        and -90 <= lat <= 90
        and -180 <= lon <= 180
        and descent_rate_mps > 0
        and alt >= 0
    ):
        return {"available": False}

    time_to_land = alt / descent_rate_mps
    drift_dist = ground_speed_mps * time_to_land
    bearing = radians(ground_track_deg)
    lat_rad = radians(lat)
    predicted_lat = lat + degrees((drift_dist * cos(bearing)) / 6_371_000)
    cos_lat = cos(lat_rad)
    if abs(cos_lat) < 1e-8:
        predicted_lon = lon
    else:
        predicted_lon = lon + degrees((drift_dist * sin(bearing)) / (6_371_000 * cos_lat))
    return {
        "available": True,
        "time_to_land_seconds": time_to_land,
        "drift_distance_m": drift_dist,
        "predicted_landing_lat": predicted_lat,
        "predicted_landing_lon": predicted_lon,
    }
