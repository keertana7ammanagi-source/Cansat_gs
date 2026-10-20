"""
guidance/wind_estimator.py

Deterministic (non-ML) wind / drift estimator. This is Phase 1 of the
plan: estimate horizontal drift purely from consecutive GPS fixes and
time deltas. There is no machine learning here -- an ML wind predictor
is a later addition that would feed its output into the same interface
(get_wind_estimate()) so the LandingController doesn't need to change.

Method:
    velocity_east  = d(east)  / d(time)
    velocity_north = d(north) / d(time)

The estimate is smoothed with a simple moving average over the last
N samples to reduce GPS jitter, since raw single-sample derivatives
are noisy.
"""

import math
from collections import deque

from guidance.coordinate_utils import gps_to_local


class WindEstimator:
    def __init__(self, ref_lat, ref_lon, history_len=5):
        """
        ref_lat, ref_lon: reference point used to convert GPS to local
                           metres (should match what LandingController
                           uses, e.g. the launch point).
        history_len:       number of recent velocity samples to average.
        """
        self.ref_lat = ref_lat
        self.ref_lon = ref_lon

        self._last_pos = None      # (east, north)
        self._last_time = None     # seconds (monotonic or mission time)

        self._vel_history = deque(maxlen=history_len)

        self.velocity_east = 0.0
        self.velocity_north = 0.0

    def update(self, lat, lon, timestamp_s):
        """
        Feed a new GPS fix + timestamp (seconds, monotonically increasing).
        Returns the current smoothed (velocity_east, velocity_north) in m/s.
        """
        east, north = gps_to_local(lat, lon, self.ref_lat, self.ref_lon)

        if self._last_pos is not None and self._last_time is not None:
            dt = timestamp_s - self._last_time
            if dt > 1e-3:  # ignore duplicate/zero-interval packets
                ve = (east - self._last_pos[0]) / dt
                vn = (north - self._last_pos[1]) / dt
                self._vel_history.append((ve, vn))

        self._last_pos = (east, north)
        self._last_time = timestamp_s

        if self._vel_history:
            avg_ve = sum(v[0] for v in self._vel_history) / len(self._vel_history)
            avg_vn = sum(v[1] for v in self._vel_history) / len(self._vel_history)
            self.velocity_east = avg_ve
            self.velocity_north = avg_vn

        return self.velocity_east, self.velocity_north

    def get_wind_estimate(self):
        """
        Returns (speed_m_s, direction_deg) using compass convention
        (0 = North, 90 = East), describing the CanSat's estimated
        horizontal ground drift.

        NOTE: this is ground-track drift, not true wind speed -- it
        includes any commanded glide motion too. True wind estimation
        would need to subtract the expected glide-induced velocity
        (from the servo command in effect), which is a later refinement.
        """
        speed = math.hypot(self.velocity_east, self.velocity_north)
        if speed < 1e-6:
            direction = 0.0
        else:
            direction = math.degrees(
                math.atan2(self.velocity_east, self.velocity_north)
            ) % 360.0
        return speed, direction

    def reset(self):
        self._last_pos = None
        self._last_time = None
        self._vel_history.clear()
        self.velocity_east = 0.0
        self.velocity_north = 0.0
