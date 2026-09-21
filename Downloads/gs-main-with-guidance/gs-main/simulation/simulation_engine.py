"""
Simulation Engine – Generates synthetic telemetry or replays CSV files.
"""
import csv
import time
import math
import random
import os
from datetime import datetime
from PyQt5 import QtCore

from core.telemetry.constants import TEAM_ID, FIELD_NAMES
from utils.logger import get_logger

logger = get_logger(__name__)


class SimulationEngine(QtCore.QObject):
    """
    Emits telemetry packets at a configurable rate.
    Can generate synthetic mission data or replay a CSV file.
    """
    packet_ready = QtCore.pyqtSignal(str)  # emits raw CSV line
    status_updated = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self._next_packet)
        self.packet_queue = []
        self.is_running = False
        self.is_paused = False
        self.speed_multiplier = 1.0
        self.mode = "synthetic"  # "synthetic" or "replay"
        self.replay_data = []
        self.replay_index = 0
        self.start_time = None
        self.packet_count = 0
        self.synthetic_time = 0.0
        self.synthetic_state = "ASCENT"
        self.altitude = 0.0
        self.velocity = 0.0
        self.apogee = 1000.0
        self.secondary_deploy_alt = 600.0

    def start_synthetic(self, interval_ms=1000):
        """Start generating synthetic telemetry."""
        self.mode = "synthetic"
        self.packet_count = 0
        self.synthetic_time = 0.0
        self.altitude = 0.0
        self.velocity = 0.0
        self.synthetic_state = "LAUNCH_PAD"
        self.is_running = True
        self.is_paused = False
        self.start_time = time.time()
        self.timer.start(int(interval_ms / self.speed_multiplier))
        self.status_updated.emit("Synthetic simulation started.")

    def start_replay(self, csv_filepath, interval_ms=1000):
        """Load a CSV file and start replaying it."""
        try:
            self.replay_data = []
            with open(csv_filepath, 'r') as f:
                reader = csv.reader(f)
                headers = next(reader)
                # Ensure headers match FIELD_NAMES, or map accordingly
                for row in reader:
                    if len(row) == len(FIELD_NAMES):
                        self.replay_data.append(row)
                    else:
                        # Try to map by header
                        logger.warning("CSV header mismatch, attempting to map fields.")
                        # For simplicity, we only accept exact match in this version.
                        pass
            if not self.replay_data:
                self.status_updated.emit("Error: CSV has no data or wrong format.")
                return

            self.mode = "replay"
            self.replay_index = 0
            self.is_running = True
            self.is_paused = False
            self.timer.start(int(interval_ms / self.speed_multiplier))
            self.status_updated.emit(f"Replay started: {os.path.basename(csv_filepath)} ({len(self.replay_data)} packets)")

        except Exception as e:
            self.status_updated.emit(f"Replay error: {e}")
            logger.error(f"Replay error: {e}")

    def stop(self):
        self.is_running = False
        self.timer.stop()
        self.status_updated.emit("Simulation stopped.")
        logger.info("Simulation stopped.")

    def pause(self):
        self.is_paused = not self.is_paused
        self.status_updated.emit("Paused" if self.is_paused else "Resumed")
        logger.info(f"Simulation paused: {self.is_paused}")

    def set_speed(self, multiplier):
        self.speed_multiplier = multiplier
        # Restart timer with new interval
        if self.is_running and not self.is_paused:
            current_interval = self.timer.interval()
            new_interval = int(current_interval / multiplier)
            if new_interval < 10:
                new_interval = 10  # min 10ms
            self.timer.setInterval(new_interval)
        self.status_updated.emit(f"Speed: {multiplier}x")

    def _next_packet(self):
        if self.is_paused:
            return

        if self.mode == "synthetic":
            line = self._generate_synthetic_packet()
        else:
            line = self._get_next_replay_packet()

        if line:
            self.packet_ready.emit(line)

    def _get_next_replay_packet(self):
        if self.replay_index >= len(self.replay_data):
            self.stop()
            self.status_updated.emit("Replay finished.")
            return None
        row = self.replay_data[self.replay_index]
        self.replay_index += 1
        # Re-insert TEAM_ID if missing
        if len(row) == len(FIELD_NAMES):
            return ",".join(row)
        return None

    def _generate_synthetic_packet(self):
        """
        Generate a realistic telemetry packet for a full mission.
        """
        dt = 1.0  # 1 second per packet
        self.synthetic_time += dt
        self.packet_count += 1

        # --- Flight profile ---
        # Phase 1: Ascent (0-30s) to 1000m
        if self.synthetic_time < 30:
            self.synthetic_state = "ASCENT"
            # Quadratic ascent: accelerates then decelerates
            progress = self.synthetic_time / 30.0
            self.altitude = 1000.0 * (1 - math.cos(progress * math.pi / 2))
            self.velocity = (1000.0 * math.pi / 60) * math.sin(progress * math.pi / 2)
            if self.velocity < 0:
                self.velocity = 0

        # Phase 2: Apogee (30-32s)
        elif self.synthetic_time < 32:
            self.synthetic_state = "APOGEE"
            self.altitude = 1000.0 - (self.synthetic_time - 30) * 2
            self.velocity = -2.0

        # Phase 3: Primary Descent (32-62s) at ~20 m/s
        elif self.synthetic_time < 62:
            self.synthetic_state = "DESCENT_PRIMARY"
            self.altitude = 1000.0 - 20 * (self.synthetic_time - 30)
            self.velocity = -20.0

        # Phase 4: Secondary deployment at 600m (62-82s) at ~3 m/s
        elif self.synthetic_time < 82:
            self.synthetic_state = "DESCENT_SECONDARY"
            # Decelerate smoothly to 3 m/s
            if self.velocity < -3.0:
                self.velocity += 0.5
                if self.velocity > -3.0:
                    self.velocity = -3.0
            self.altitude = 600.0 - 3 * (self.synthetic_time - 62)
            if self.altitude < 0:
                self.altitude = 0

        # Phase 5: Landing / Impact
        else:
            self.synthetic_state = "IMPACT"
            self.altitude = 0.0
            self.velocity = 0.0
            self.stop()
            self.status_updated.emit("Mission complete (impact detected).")
            return None

        # --- Compute derived values ---
        # Pressure (simulate altitude-pressure relationship)
        pressure = 1013.25 * math.exp(-self.altitude / 8500.0)

        # Temperature (decrease with altitude, then stabilize)
        temp = 25.0 - 0.0065 * self.altitude
        if temp < -10:
            temp = -10

        # Humidity (random)
        humidity = 40 + random.uniform(-10, 10)

        # UV (peak at midday)
        uv = 3.0 + random.uniform(-1, 1)

        # Light (decrease with altitude, random clouds)
        light = 200.0 * (1 - self.altitude / 1200.0) + random.uniform(-20, 20)
        if light < 0:
            light = 0

        # Voltage (battery discharge)
        voltage = 7.6 - 0.0005 * self.packet_count
        if voltage < 6.0:
            voltage = 6.0

        # Current / Power (simulate load)
        current = 0.42 + random.uniform(-0.05, 0.05)

        # IMU (gyro/accel) – slight oscillations during descent
        osc = math.sin(self.synthetic_time * 0.5) * 2.0
        if self.synthetic_state in ("DESCENT_PRIMARY", "DESCENT_SECONDARY"):
            gyro_r = 10.0 + osc
            gyro_p = 5.0 + osc * 0.5
            gyro_y = 3.0 + osc * 0.2
            accel_r = 0.2 + random.uniform(-0.1, 0.1)
            accel_p = 0.1 + random.uniform(-0.1, 0.1)
            accel_y = 9.8 + random.uniform(-0.2, 0.2)
        else:
            gyro_r, gyro_p, gyro_y = 0.0, 0.0, 0.0
            accel_r, accel_p, accel_y = 0.0, 0.0, 9.8

        # RPM (rotor)
        rpm = 0
        if self.synthetic_state in ("DESCENT_PRIMARY", "DESCENT_SECONDARY"):
            rpm = 1500 + random.randint(-200, 200)

        # GPS (simulate with slight drift)
        lat = 28.6129 + self.altitude * 0.0000001 + random.uniform(-0.0001, 0.0001)
        lon = 77.2295 + self.altitude * 0.0000001 + random.uniform(-0.0001, 0.0001)
        gps_alt = self.altitude + random.uniform(-5, 5)
        sats = 9 + random.randint(-2, 2)
        if sats < 4:
            sats = 4

        # Time
        h = int(self.synthetic_time // 3600)
        m = int((self.synthetic_time % 3600) // 60)
        s = int(self.synthetic_time % 60)
        time_str = f"{h:02d}:{m:02d}:{s:02d}"

        # State mapping
        state_map = {
            "LAUNCH_PAD": 2,
            "ASCENT": 3,
            "APOGEE": 4,
            "DESCENT_PRIMARY": 5,
            "DESCENT_SECONDARY": 6,
            "IMPACT": 7,
        }
        state = state_map.get(self.synthetic_state, 5)

        # Build 28-field packet
        fields = [
            TEAM_ID, time_str, str(self.packet_count),
            f"{self.altitude:.1f}", f"{pressure:.1f}", f"{temp:.1f}", f"{voltage:.2f}",
            time_str, f"{lat:.6f}", f"{lon:.6f}", f"{gps_alt:.1f}", str(sats),
            f"{accel_r:.2f}", f"{accel_p:.2f}", f"{accel_y:.2f}",
            f"{gyro_r:.2f}", f"{gyro_p:.2f}", f"{gyro_y:.2f}",
            str(state),
            f"{humidity:.1f}", f"{uv:.1f}", f"{light:.1f}", f"{rpm:.0f}",
            "0.18", "0.05", "0.41",
            "1", "OK"
        ]

        return ",".join(fields)