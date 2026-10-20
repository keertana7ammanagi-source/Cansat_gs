"""Phase-based CAN-7USAT telemetry simulation and CSV replay."""
import csv
import math
import os
import random

from PyQt5 import QtCore

from core.telemetry.constants import FIELD_NAMES, TEAM_ID
from utils.logger import get_logger

logger = get_logger(__name__)


class SimulationEngine(QtCore.QObject):
    """Generate 37-field telemetry at a steady cadence or replay a CSV."""

    packet_ready = QtCore.pyqtSignal(str)
    status_updated = QtCore.pyqtSignal(str)

    # Mission timeline, measured in simulated seconds.
    PAD_END = 5.0
    ASCENT_END = 35.0
    APOGEE_END = 39.0
    DEPLOYMENT_START = 59.0       # descent profile reaches 600 m here
    DEPLOYMENT_END = 65.0
    DEPLOYMENT_ALTITUDE_END = 525.0
    FLARE_ALTITUDE = 25.0 / 3.0   # integrates to zero over the 5 s flare
    FLARE_DURATION = 5.0
    CONTROLLED_DESCENT_END = DEPLOYMENT_END + (DEPLOYMENT_ALTITUDE_END - FLARE_ALTITUDE) / 5.0
    LANDING_TIME = CONTROLLED_DESCENT_END + FLARE_DURATION

    def __init__(self):
        super().__init__()
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._next_packet)
        self.is_running = False
        self.is_paused = False
        self.speed_multiplier = 1.0
        self.base_interval_ms = 1000
        self.mode = "synthetic"
        self.replay_data = []
        self.replay_index = 0
        self.packet_count = 0
        self.synthetic_time = 0.0
        self.synthetic_phase = "READY"
        self.mission_complete = False
        self.rng = random.Random()
        self._noise = {}
        self._latitude = 28.612900
        self._longitude = 77.229500
        self._last_angles = (0.0, 0.0, 0.0)
        self._has_previous_attitude = False

    @staticmethod
    def _smoothstep(u):
        u = max(0.0, min(1.0, u))
        return u * u * u * (u * (u * 6.0 - 15.0) + 10.0)

    @staticmethod
    def _hermite(y0, v0, y1, v1, duration, u):
        """Cubic Hermite position, velocity, and acceleration at normalized u."""
        u = max(0.0, min(1.0, u))
        u2, u3 = u * u, u * u * u
        pos = ((2*u3 - 3*u2 + 1) * y0 + (u3 - 2*u2 + u) * duration * v0
               + (-2*u3 + 3*u2) * y1 + (u3 - u2) * duration * v1)
        vel = (((6*u2 - 6*u) / duration) * y0 + (3*u2 - 4*u + 1) * v0
               + ((-6*u2 + 6*u) / duration) * y1 + (3*u2 - 2*u) * v1)
        acc = (((12*u - 6) / duration**2) * y0 + ((6*u - 4) / duration) * v0
               + ((-12*u + 6) / duration**2) * y1 + ((6*u - 2) / duration) * v1)
        return pos, vel, acc

    def _set_phase(self, phase):
        if phase != self.synthetic_phase:
            self.synthetic_phase = phase
            self.status_updated.emit(f"Simulation phase: {phase}")

    def start_synthetic(self, interval_ms=1000):
        """Start the complete launch-to-landing profile, one sample per second."""
        self.stop(announce=False)
        self.mode = "synthetic"
        self.packet_count = 0
        self.synthetic_time = 0.0
        self.synthetic_phase = "READY"
        self.mission_complete = False
        self._noise.clear()
        self._latitude, self._longitude = 28.612900, 77.229500
        self._last_angles = (0.0, 0.0, 0.0)
        self._has_previous_attitude = False
        self.rng = random.Random(2026)
        self.base_interval_ms = max(100, int(interval_ms))
        self.is_running = True
        self.is_paused = False
        self.timer.start(max(10, int(self.base_interval_ms / self.speed_multiplier)))
        self.status_updated.emit("37-field hardware-substitute simulation started.")

    def start_replay(self, csv_filepath, interval_ms=1000):
        """Load rows with either current-schema or legacy headers for replay."""
        try:
            self.replay_data = []
            with open(csv_filepath, "r", newline="", encoding="utf-8-sig") as source:
                reader = csv.DictReader(source)
                if not reader.fieldnames:
                    raise ValueError("CSV is missing a header row")
                for row in reader:
                    values = [row.get(name, "") or "" for name in FIELD_NAMES]
                    if values[0] == TEAM_ID:
                        self.replay_data.append(",".join(values))
            if not self.replay_data:
                raise ValueError("CSV has no rows matching the 37-field team schema")
            self.stop(announce=False)
            self.mode = "replay"
            self.replay_index = 0
            self.mission_complete = False
            self.base_interval_ms = max(100, int(interval_ms))
            self.is_running = True
            self.is_paused = False
            self.timer.start(max(10, int(self.base_interval_ms / self.speed_multiplier)))
            self.status_updated.emit(
                f"Replay started: {os.path.basename(csv_filepath)} ({len(self.replay_data)} packets)"
            )
        except Exception as exc:
            self.status_updated.emit(f"Replay error: {exc}")
            logger.exception("Replay load failed: %s", exc)

    def stop(self, announce=True):
        self.is_running = False
        self.timer.stop()
        if announce:
            self.status_updated.emit("Simulation stopped.")
        logger.info("Simulation stopped.")

    def pause(self):
        self.is_paused = not self.is_paused
        self.status_updated.emit("Paused" if self.is_paused else "Resumed")

    def set_speed(self, multiplier):
        self.speed_multiplier = max(0.1, float(multiplier))
        if self.is_running and not self.is_paused:
            self.timer.setInterval(max(10, int(self.base_interval_ms / self.speed_multiplier)))
        self.status_updated.emit(f"Speed: {self.speed_multiplier:g}x")

    def _next_packet(self):
        if self.is_paused or not self.is_running:
            return
        line = self._generate_synthetic_packet() if self.mode == "synthetic" else self._get_next_replay_packet()
        if line:
            self.packet_ready.emit(line)
        if self.mission_complete:
            self.stop(announce=False)
            self.status_updated.emit("Mission complete: landing packet logged.")

    def _get_next_replay_packet(self):
        if self.replay_index >= len(self.replay_data):
            self.stop()
            self.status_updated.emit("Replay finished.")
            return None
        row = self.replay_data[self.replay_index]
        self.replay_index += 1
        return row

    def _colored_noise(self, name, sigma, rho=0.88):
        previous = self._noise.get(name, 0.0)
        value = rho * previous + self.rng.gauss(0.0, sigma * math.sqrt(1.0 - rho * rho))
        self._noise[name] = value
        return value

    def _flight_kinematics(self, t):
        if t < self.PAD_END:
            self._set_phase("LAUNCH PAD")
            return 0.0, 0.0, 0.0, 2
        if t < self.ASCENT_END:
            self._set_phase("ASCENT")
            duration = self.ASCENT_END - self.PAD_END
            u = (t - self.PAD_END) / duration
            altitude = 1000.0 * self._smoothstep(u)
            velocity = 1000.0 / duration * 30.0 * u**2 * (u - 1.0)**2
            acceleration = 1000.0 / duration**2 * (120*u**3 - 180*u**2 + 60*u)
            return altitude, velocity, acceleration, 3
        if t < self.APOGEE_END:
            self._set_phase("APOGEE HOLD")
            return 1000.0, 0.0, 0.0, 4
        if t < self.DEPLOYMENT_START:
            self._set_phase("DESCENT TO 600 m")
            u = (t - self.APOGEE_END) / (self.DEPLOYMENT_START - self.APOGEE_END)
            return (*self._hermite(1000.0, 0.0, 600.0, -20.0, 20.0, u), 5)
        if t < self.DEPLOYMENT_END:
            self._set_phase("ANTRS DEPLOYMENT AT 600 m")
            u = (t - self.DEPLOYMENT_START) / (self.DEPLOYMENT_END - self.DEPLOYMENT_START)
            return (*self._hermite(600.0, -20.0, self.DEPLOYMENT_ALTITUDE_END, -5.0, 6.0, u), 6)
        if t < self.CONTROLLED_DESCENT_END:
            self._set_phase("CONTROLLED DESCENT")
            altitude = self.DEPLOYMENT_ALTITUDE_END - 5.0 * (t - self.DEPLOYMENT_END)
            return altitude, -5.0, 0.0, 5
        if t < self.LANDING_TIME:
            self._set_phase("LANDING FLARE")
            u = (t - self.CONTROLLED_DESCENT_END) / self.FLARE_DURATION
            altitude = self.FLARE_ALTITUDE - 5.0 * self.FLARE_DURATION * (u - u*u + u**3/3.0)
            velocity = -5.0 * (1.0 - u)**2
            acceleration = 10.0 * (1.0 - u) / self.FLARE_DURATION
            return max(0.0, altitude), velocity, acceleration, 5
        self._set_phase("LANDED")
        self.mission_complete = True
        return 0.0, 0.0, 0.0, 7

    def _generate_synthetic_packet(self):
        """Return one smooth, lightly noisy 37-field CSV packet."""
        self.synthetic_time += 1.0
        self.packet_count += 1
        t = min(self.synthetic_time, self.LANDING_TIME)
        altitude, vertical_speed, vertical_accel, flight_state = self._flight_kinematics(t)
        if flight_state == 7:
            altitude = vertical_speed = vertical_accel = 0.0

        # Slowly varying horizontal drift; reported GPS position is its integral.
        east = 2.2 + 0.45 * math.sin(t / 38.0)
        north = 0.55 + 0.30 * math.sin(t / 29.0 + 0.4)
        self._latitude += north / 111320.0
        self._longitude += east / (111320.0 * math.cos(math.radians(self._latitude)))
        ground_speed = math.hypot(east, north)
        course = math.degrees(math.atan2(east, north)) % 360.0

        roll = 2.0 * math.sin(t / 14.0) + self._colored_noise("roll", 0.08)
        pitch = 1.6 * math.sin(t / 19.0 + 0.3) + self._colored_noise("pitch", 0.08)
        yaw = course + 1.2 * math.sin(t / 24.0) + self._colored_noise("yaw", 0.08)
        if self._has_previous_attitude:
            gyro_x = roll - self._last_angles[0]
            gyro_y = pitch - self._last_angles[1]
            gyro_z = yaw - self._last_angles[2]
        else:
            gyro_x = gyro_y = gyro_z = 0.0
            self._has_previous_attitude = True
        self._last_angles = (roll, pitch, yaw)

        pressure = 101325.0 * max(0.01, 1.0 - 2.25577e-5 * altitude) ** 5.25588
        pressure += self._colored_noise("pressure", 2.5)
        temperature = 25.0 - 0.0065 * altitude + 0.08 * math.sin(t / 31.0)
        temperature += self._colored_noise("temperature", 0.035)
        humidity = max(15.0, min(90.0, 43.0 - 0.004 * altitude + 1.4 * math.sin(t / 43.0)
                                 + self._colored_noise("humidity", 0.25)))
        uv_index = max(0.0, 3.0 + 0.00045 * altitude + 0.12 * math.sin(t / 36.0)
                       + self._colored_noise("uv", 0.025))
        lux = max(0.0, 24000.0 + 1200.0 * math.sin(t / 48.0) + 0.55 * altitude
                  + self._colored_noise("lux", 90.0))

        voltage = 7.60 - 0.00065 * t + self._colored_noise("voltage", 0.002)
        deployment_load = 70.0 * self._smoothstep((t - self.DEPLOYMENT_START) / 5.0) * (
            1.0 - self._smoothstep((t - self.DEPLOYMENT_END) / 5.0)
        )
        current_ma = 430.0 + 35.0 * self._smoothstep((t - self.PAD_END) / 3.0) + deployment_load
        current_ma += self._colored_noise("current", 1.8)
        power_mw = voltage * current_ma

        accel_x = 0.10 * math.sin(t / 7.0) + self._colored_noise("accel_x", 0.025)
        accel_y = 0.08 * math.sin(t / 9.0 + 0.5) + self._colored_noise("accel_y", 0.025)
        accel_z = 9.80665 + vertical_accel + self._colored_noise("accel_z", 0.035)
        magnetic_x = 22.0 * math.cos(math.radians(yaw)) + self._colored_noise("mag_x", 0.08)
        magnetic_y = 22.0 * math.sin(math.radians(yaw)) + self._colored_noise("mag_y", 0.08)
        magnetic_z = 41.0 + 0.2 * math.sin(t / 51.0) + self._colored_noise("mag_z", 0.08)

        rpm = 1200.0 * self._smoothstep((t - self.DEPLOYMENT_START) / 8.0)
        rpm += self._colored_noise("rpm", 3.0) if rpm > 0.0 else 0.0
        gps_altitude = max(0.0, altitude + self._colored_noise("gps_altitude", 0.45))
        gps_latitude = self._latitude + self._colored_noise("gps_latitude", 0.000002)
        gps_longitude = self._longitude + self._colored_noise("gps_longitude", 0.000002)
        hdop = max(0.65, min(1.4, 0.82 + self._colored_noise("hdop", 0.025)))
        sats = max(8, min(12, 10 + int(round(self._colored_noise("sats", 0.3)))))

        seconds = int(t)
        gnss_time = f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"
        values = {
            "TEAM_ID": TEAM_ID, "TIMESTAMP": t, "PACKET_COUNT": self.packet_count,
            "ALTITUDE": max(0.0, altitude + self._colored_noise("altitude", 0.12)) if flight_state != 7 else 0.0,
            "PRESSURE": pressure, "TEMP": temperature, "VOLTAGE": voltage,
            "GNSS_TIME": gnss_time, "GNSS_LATITUDE": gps_latitude, "GNSS_LONGITUDE": gps_longitude,
            "GNSS_ALTITUDE": gps_altitude, "GNSS_SATS": sats,
            "ACCEL_X": accel_x, "ACCEL_Y": accel_y, "ACCEL_Z": accel_z,
            "GYRO_X": gyro_x, "GYRO_Y": gyro_y, "GYRO_Z": gyro_z,
            "MAG_X": magnetic_x, "MAG_Y": magnetic_y, "MAG_Z": magnetic_z,
            "ROLL": roll, "PITCH": pitch, "YAW": yaw, "LIGHT_LUX": lux,
            "UV_INDEX": uv_index, "HALL_RPM": max(0.0, rpm),
            "FLIGHT_SOFTWARE_STATE": flight_state, "REL_ALTITUDE": altitude,
            "VERTICAL_SPEED": vertical_speed, "GNSS_GROUND_SPEED": ground_speed,
            "GNSS_COURSE": course, "GNSS_HDOP": hdop, "GNSS_FIX": 3,
            "HUMIDITY": humidity, "CURRENT": current_ma, "POWER": power_mw,
        }
        return ",".join(self._format_field(name, values[name]) for name in FIELD_NAMES)

    @staticmethod
    def _format_field(name, value):
        if name in {"TEAM_ID", "GNSS_TIME"}:
            return str(value)
        if name in {"PACKET_COUNT", "GNSS_SATS", "FLIGHT_SOFTWARE_STATE", "GNSS_FIX"}:
            return str(int(value))
        if name in {"GNSS_LATITUDE", "GNSS_LONGITUDE"}:
            return f"{float(value):.7f}"
        if name in {"TIMESTAMP", "ALTITUDE", "GNSS_ALTITUDE", "REL_ALTITUDE"}:
            return f"{float(value):.2f}"
        return f"{float(value):.4f}"
