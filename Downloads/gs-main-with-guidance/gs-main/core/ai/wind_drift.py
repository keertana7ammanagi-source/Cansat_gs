import numpy as np
from math import radians, cos, sin, asin, sqrt

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return 2 * R * asin(sqrt(a))

class WindEstimator:
    def __init__(self):
        self.prev_lat = None
        self.prev_lon = None
        self.wind_speed = None
        self.wind_dir = None

    def update(self, packet):
        lat = packet.get("GNSS_LATITUDE")
        lon = packet.get("GNSS_LONGITUDE")
        if lat is None or lon is None:
            return {"available": False}

        if self.prev_lat is not None:
            dist = haversine(self.prev_lat, self.prev_lon, lat, lon)
            self.wind_speed = dist
            bearing = np.arctan2(lon - self.prev_lon, lat - self.prev_lat)
            self.wind_dir = np.degrees(bearing) % 360

        self.prev_lat, self.prev_lon = lat, lon
        return {
            "available": self.wind_speed is not None,
            "wind_speed_mps": self.wind_speed or 0,
            "wind_direction_deg": self.wind_dir or 0,
        }

class StabilityMonitor:
    def __init__(self, window=20):
        self.accel_history = []
        self.stability_index = 100

    def update(self, packet):
        ax = packet.get("ACCEL_R", 0)
        ay = packet.get("ACCEL_P", 0)
        az = packet.get("ACCEL_Y", 0)
        self.accel_history.append((ax, ay, az))
        if len(self.accel_history) > 20:
            self.accel_history.pop(0)

        if len(self.accel_history) >= 5:
            arr = np.array(self.accel_history)
            std = np.std(arr, axis=0).mean()
            self.stability_index = max(0, 100 - (std / 2.0) * 100)

        return {"stability_index": self.stability_index}

    def stability_index_percent(self):
        return self.stability_index

def estimate_landing_drift(lat, lon, alt, descent_rate_mps, wind_speed_mps, wind_direction_deg):
    if lat is None or lon is None or alt is None:
        return {"available": False}
    time_to_land = alt / descent_rate_mps if descent_rate_mps > 0 else 0
    drift_dist = wind_speed_mps * time_to_land
    return {
        "available": True,
        "time_to_land_seconds": time_to_land,
        "drift_distance_m": drift_dist,
        "predicted_landing_lat": lat,
        "predicted_landing_lon": lon,
    }