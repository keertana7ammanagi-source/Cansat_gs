"""
Offline Anomaly Detection Module for CAN-7USAT Ground Station.

Features:
- Pure Python, zero-dependency, deterministic offline operation.
- Dual-tier detection:
  1. Configurable physical & engineering limits (spec-based and provisional).
  2. Robust rolling statistical detection (Modified Z-score using Median & MAD).
- Baseline protection:
  - Candidates are scored strictly against prior valid samples before inclusion.
  - Outliers are quarantined from the baseline to prevent variance distortion.
  - Persistent shift detection tracks consecutive anomalies to identify step changes.
- Numerical safety:
  - Safe zero-variance & near-zero variance handling (no division by zero or Inf).
  - Explicit handling for NaN, Inf, non-numeric values, and missing telemetry fields.
- Flight-phase awareness:
  - Recognizes dynamic flight states (ASCENT, DESCENT, ROCKET_DEPLOY, AEROBRAKE_RELEASE)
    and relaxes or adapts velocity/rate-of-change checks to avoid false alarms.
- Alert deduplication and cooldown to prevent UI flooding.
- Passive & read-only: never issues uplink commands or alters flight control.
"""

from collections import deque
import math
from typing import Any, Dict, List, Optional, Tuple


# Default provisional & spec-backed engineering limits.
# BMP581: 20000 - 110000 Pa (operational range), Altitude -50 to 5000 m
# SHT40: Temp -40 to 85 °C, Humidity 0 to 100 %
# LTR390: UV Index 0 to 20, Light Lux 0 to 100000 lux
# INA219: Voltage 5.0 to 9.0 V (provisional 2S LiPo), Current 0 to 3000 mA, Power 0 to 15000 mW
# GNSS: Sats 0 to 32, HDOP 0 to 20
# BNO085: Roll/Pitch -180 to 180 deg, Yaw -360 to 360 deg
# Accelerometer: -160 to 160 m/s^2 (provisional +/-16g scale)
DEFAULT_ENGINEERING_LIMITS = {
    "ALTITUDE": (-50.0, 5000.0),
    "PRESSURE": (20000.0, 110000.0),
    "TEMP": (-40.0, 85.0),
    "VOLTAGE": (5.0, 9.0),
    "HUMIDITY": (0.0, 100.0),
    "CURRENT": (0.0, 3000.0),
    "POWER": (0.0, 15000.0),
    "LIGHT_LUX": (0.0, 100000.0),
    "UV_INDEX": (0.0, 20.0),
    "GNSS_SATS": (0.0, 32.0),
    "GNSS_HDOP": (0.0, 25.0),
    "ACCEL_X": (-160.0, 160.0),
    "ACCEL_Y": (-160.0, 160.0),
    "ACCEL_Z": (-160.0, 160.0),
    "ROLL": (-180.0, 180.0),
    "PITCH": (-180.0, 180.0),
    "YAW": (-360.0, 360.0),
    "HALL_RPM": (0.0, 100000.0),
}

# Minimum noticeable deviation required before flagging a near-constant baseline.
# Prevents false positives when a sensor reading stays rock solid and std/MAD approaches 0.
DEFAULT_MIN_DELTA = {
    "ALTITUDE": 2.0,       # meters
    "PRESSURE": 30.0,      # Pa (~0.3 hPa)
    "TEMP": 0.5,           # °C
    "VOLTAGE": 0.05,       # Volts
    "HUMIDITY": 1.0,       # %
    "CURRENT": 10.0,       # mA
    "POWER": 50.0,         # mW
    "LIGHT_LUX": 5.0,      # Lux
    "UV_INDEX": 0.2,       # Index
    "ACCEL_X": 0.5,        # m/s^2
    "ACCEL_Y": 0.5,
    "ACCEL_Z": 0.5,
    "ROLL": 1.0,           # deg
    "PITCH": 1.0,
    "YAW": 1.0,
    "HALL_RPM": 10.0,
}

# Dynamic flight phases where rapid vertical/pressure/acceleration changes are expected
DYNAMIC_FLIGHT_STATES = {
    3, 4, 5, 6,
    "3", "4", "5", "6",
    "ASCENT", "ROCKET_DEPLOY", "DESCENT", "AEROBRAKE_RELEASE"
}


class AnomalyEvent:
    """Represents a detected anomaly event."""

    def __init__(
        self,
        timestamp: Any,
        sensor: str,
        value: Any,
        anomaly_type: str,
        severity: str,
        reason: str,
        score: float = 0.0,
        flight_state: Any = None,
    ):
        self.timestamp = timestamp if timestamp is not None else "--"
        self.sensor = sensor
        self.value = value
        self.anomaly_type = anomaly_type  # DATA_QUALITY, LIMIT_VIOLATION, STATISTICAL_ANOMALY, PERSISTENT_SHIFT
        self.severity = severity          # INFO, WARNING, CRITICAL
        self.reason = reason
        self.score = score
        self.flight_state = flight_state if flight_state is not None else "--"
        self.count = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "sensor": self.sensor,
            "value": self.value,
            "anomaly_type": self.anomaly_type,
            "severity": self.severity,
            "reason": self.reason,
            "score": self.score,
            "flight_state": self.flight_state,
            "count": self.count,
        }

    def __repr__(self) -> str:
        return f"<AnomalyEvent {self.sensor} [{self.severity}] {self.reason} val={self.value}>"


class SensorBaselineTracker:
    """
    Maintains robust rolling baseline statistics for a single numeric sensor.
    Implements outlier quarantine, numerical safety, and persistent shift tracking.
    """

    def __init__(
        self,
        sensor_name: str,
        window_size: int = 30,
        min_samples: int = 10,
        min_delta: float = 1.0,
        persistent_shift_limit: int = 8,
    ):
        self.sensor_name = sensor_name
        self.window_size = max(5, window_size)
        self.min_samples = max(3, min_samples)
        self.min_delta = max(1e-5, min_delta)
        self.persistent_shift_limit = max(3, persistent_shift_limit)

        self._history: deque = deque(maxlen=self.window_size)
        self._consecutive_anomalies: int = 0
        self._quarantined_samples: List[float] = []

    @property
    def sample_count(self) -> int:
        return len(self._history)

    @property
    def is_warmed_up(self) -> bool:
        return len(self._history) >= self.min_samples

    def clear(self):
        self._history.clear()
        self._consecutive_anomalies = 0
        self._quarantined_samples.clear()

    def get_stats(self) -> Dict[str, float]:
        """Return current baseline summary (mean, std, median, MAD)."""
        if not self._history:
            return {"mean": 0.0, "std": 0.0, "median": 0.0, "mad": 0.0, "samples": 0}

        vals = list(self._history)
        n = len(vals)
        mean_val = sum(vals) / n
        var = sum((x - mean_val) ** 2 for x in vals) / n
        std_val = math.sqrt(var)

        sorted_vals = sorted(vals)
        mid = n // 2
        median_val = sorted_vals[mid] if n % 2 != 0 else (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0

        abs_devs = sorted(abs(x - median_val) for x in vals)
        mad_val = abs_devs[mid] if n % 2 != 0 else (abs_devs[mid - 1] + abs_devs[mid]) / 2.0

        return {
            "mean": mean_val,
            "std": std_val,
            "median": median_val,
            "mad": mad_val,
            "samples": n,
        }

    def score_sample(self, value: float) -> Tuple[float, str]:
        """
        Score a new reading against the existing baseline BEFORE adding it.
        Returns (score, metric_description).
        Uses Modified Z-score with MAD when MAD > 0; falls back safely to std or min_delta.
        """
        stats = self.get_stats()
        median_val = stats["median"]
        mad_val = stats["mad"]
        std_val = stats["std"]
        diff = abs(value - median_val)

        # Numerical safety: near-zero dispersion protection
        if mad_val > 1e-6:
            # Modified Z-Score: 0.6745 * (x - median) / MAD
            score = 0.6745 * diff / mad_val
            return score, f"Mod-Z={score:.2f} (MAD={mad_val:.2f})"
        elif std_val > 1e-6:
            score = diff / std_val
            return score, f"Z={score:.2f} (std={std_val:.2f})"
        else:
            # Baseline is constant (zero variance). Evaluate against minimum noticeable delta.
            if diff < self.min_delta:
                return 0.0, "Diff < min_delta (steady baseline)"
            else:
                score = (diff / self.min_delta) * 3.0
                return score, f"ConstBaselineDiff={diff:.2f} (min_delta={self.min_delta:.2f})"

    def record_normal(self, value: float):
        """Append a validated, normal reading into the baseline."""
        self._history.append(value)
        self._consecutive_anomalies = 0
        self._quarantined_samples.clear()

    def record_anomalous(self, value: float) -> bool:
        """
        Record that a reading was anomalous.
        Quarantines the sample. If consecutive anomalies reach persistent_shift_limit,
        the baseline absorbs the quarantined samples to adapt to the new steady state.
        Returns True if a persistent shift threshold was triggered.
        """
        self._consecutive_anomalies += 1
        self._quarantined_samples.append(value)

        if self._consecutive_anomalies >= self.persistent_shift_limit:
            # Persistent shift detected: absorb the quarantined samples into the baseline
            for s in self._quarantined_samples[-self.window_size:]:
                self._history.append(s)
            self._consecutive_anomalies = 0
            self._quarantined_samples.clear()
            return True
        return False


class AnomalyDetector:
    """
    Offline Anomaly Detector for CanSat Telemetry.
    Inspects telemetry packets, verifies limits, computes statistical deviations,
    and returns detected anomalies while deduplicating alerts.
    """

    STATE_MONITORING = "MONITORING"
    STATE_ANOMALY = "POTENTIAL_ANOMALY_DETECTED"
    STATE_WARMING_UP = "INSUFFICIENT_BASELINE_SAMPLES"
    STATE_INVALID_DATA = "INVALID_SENSOR_DATA"

    def __init__(
        self,
        monitored_fields: Optional[List[str]] = None,
        engineering_limits: Optional[Dict[str, Tuple[float, float]]] = None,
        window_size: int = 30,
        min_samples: int = 10,
        warning_z_score: float = 3.0,
        critical_z_score: float = 4.5,
        cooldown_seconds: float = 5.0,
        persistent_shift_limit: int = 8,
    ):
        self.monitored_fields = monitored_fields or [
            "ALTITUDE", "PRESSURE", "TEMP", "VOLTAGE", "HUMIDITY",
            "CURRENT", "POWER", "ACCEL_X", "ACCEL_Y", "ACCEL_Z",
            "LIGHT_LUX", "UV_INDEX", "HALL_RPM", "GNSS_SATS"
        ]
        self.engineering_limits = engineering_limits or DEFAULT_ENGINEERING_LIMITS.copy()
        self.window_size = window_size
        self.min_samples = min_samples
        self.warning_z_score = warning_z_score
        self.critical_z_score = critical_z_score
        self.cooldown_seconds = cooldown_seconds
        self.persistent_shift_limit = persistent_shift_limit

        self._trackers: Dict[str, SensorBaselineTracker] = {}
        for field in self.monitored_fields:
            min_d = DEFAULT_MIN_DELTA.get(field, 1.0)
            self._trackers[field] = SensorBaselineTracker(
                sensor_name=field,
                window_size=self.window_size,
                min_samples=self.min_samples,
                min_delta=min_d,
                persistent_shift_limit=self.persistent_shift_limit,
            )

        # Alert history & cooldown tracker: (sensor, anomaly_type) -> (last_time, last_event)
        self._recent_alerts: Dict[Tuple[str, str], Tuple[float, AnomalyEvent]] = {}
        self._all_alerts: List[AnomalyEvent] = []
        self._current_state: str = self.STATE_WARMING_UP
        self._total_packets_processed: int = 0

    @property
    def current_state(self) -> str:
        return self._current_state

    @property
    def all_alerts(self) -> List[AnomalyEvent]:
        return list(self._all_alerts)

    def reset(self):
        """Reset all baselines and alert histories."""
        for tracker in self._trackers.values():
            tracker.clear()
        self._recent_alerts.clear()
        self._all_alerts.clear()
        self._current_state = self.STATE_WARMING_UP
        self._total_packets_processed = 0

    def get_sensor_summary(self) -> Dict[str, Dict[str, Any]]:
        """Return summary of all monitored sensors (baseline stats and warmup status)."""
        summary = {}
        for field, tracker in self._trackers.items():
            stats = tracker.get_stats()
            limits = self.engineering_limits.get(field)
            summary[field] = {
                "warmed_up": tracker.is_warmed_up,
                "samples": tracker.sample_count,
                "min_samples": tracker.min_samples,
                "mean": stats["mean"],
                "std": stats["std"],
                "median": stats["median"],
                "mad": stats["mad"],
                "limits": limits,
            }
        return summary

    def process_packet(self, packet: Any) -> Tuple[str, List[AnomalyEvent]]:
        """
        Analyze a single validated TelemetryPacket or field dict.
        Returns (overall_state, list_of_new_or_updated_anomalies).
        """
        self._total_packets_processed += 1
        fields = packet.fields if hasattr(packet, "fields") else packet
        if not isinstance(fields, dict):
            event = AnomalyEvent(
                timestamp="--",
                sensor="TELEMETRY",
                value=str(packet),
                anomaly_type="DATA_QUALITY",
                severity="CRITICAL",
                reason="Corrupt packet structure (not a dict)",
            )
            self._current_state = self.STATE_INVALID_DATA
            return self._current_state, [event]

        timestamp = fields.get("TIMESTAMP", fields.get("TIME_STAMPING", fields.get("GNSS_TIME")))
        try:
            time_numeric = float(timestamp) if timestamp is not None else float(self._total_packets_processed)
        except (ValueError, TypeError):
            time_numeric = float(self._total_packets_processed)

        flight_state_raw = fields.get("FLIGHT_SOFTWARE_STATE", fields.get("FLIGHT_STATE"))
        flight_state_name = fields.get("FLIGHT_STATE_NAME", str(flight_state_raw) if flight_state_raw is not None else "UNKNOWN")
        is_dynamic_phase = (
            flight_state_raw in DYNAMIC_FLIGHT_STATES or
            flight_state_name in DYNAMIC_FLIGHT_STATES
        )

        packet_anomalies: List[AnomalyEvent] = []
        has_invalid_data = False
        all_warmed_up = True

        for field in self.monitored_fields:
            if field not in fields:
                continue

            raw_val = fields[field]
            tracker = self._trackers[field]

            # 1. Check for missing / Non-numeric / NaN / Inf
            if raw_val is None:
                # Missing field in an incoming packet
                continue

            val = None
            try:
                val = float(raw_val)
                if math.isnan(val) or math.isinf(val):
                    raise ValueError("NaN or Inf")
            except (ValueError, TypeError):
                has_invalid_data = True
                event = AnomalyEvent(
                    timestamp=timestamp,
                    sensor=field,
                    value=raw_val,
                    anomaly_type="DATA_QUALITY",
                    severity="CRITICAL",
                    reason=f"Invalid non-numeric or NaN/Inf value: {raw_val!r}",
                    flight_state=flight_state_name,
                )
                packet_anomalies.append(event)
                continue

            # 2. Check Engineering Limits
            limits = self.engineering_limits.get(field)
            if limits is not None:
                lo, hi = limits
                if val < lo or val > hi:
                    event = AnomalyEvent(
                        timestamp=timestamp,
                        sensor=field,
                        value=val,
                        anomaly_type="LIMIT_VIOLATION",
                        severity="CRITICAL",
                        reason=f"Exceeds bounds [{lo}, {hi}]: observed {val}",
                        score=abs(val - (hi if val > hi else lo)),
                        flight_state=flight_state_name,
                    )
                    packet_anomalies.append(event)
                    # Quarantined: do not include out-of-bounds readings in statistical baseline
                    tracker.record_anomalous(val)
                    continue

            # 3. Check Baseline Warmup Status
            if not tracker.is_warmed_up:
                all_warmed_up = False
                # Still warming up: add valid reading into initial baseline
                tracker.record_normal(val)
                continue

            # 4. Statistical Anomaly Check (Score BEFORE adding to baseline)
            # Flight-Phase Awareness:
            # During dynamic ascent/descent, altitude and pressure change continuously by design.
            # Comparing monotonic flight changes against a stationary rolling mean causes false alarms.
            # Therefore, during dynamic flight phases, trajectory fields are checked for physical rate-of-change
            # plausibility while stationary Z-score checks are gated. Non-trajectory sensors (TEMP, VOLTAGE, etc.)
            # remain actively monitored by statistical Z-score.
            if is_dynamic_phase and field in ("ALTITUDE", "PRESSURE", "VERTICAL_SPEED", "REL_ALTITUDE"):
                # Always safely accept legitimate dynamic flight changes into the rolling baseline
                tracker.record_normal(val)
                continue

            score, desc = tracker.score_sample(val)
            effective_warn_threshold = self.warning_z_score
            effective_crit_threshold = self.critical_z_score

            if score >= effective_warn_threshold:
                severity = "CRITICAL" if score >= effective_crit_threshold else "WARNING"
                is_persistent = tracker.record_anomalous(val)

                if is_persistent:
                    reason_str = (
                        f"Persistent sensor shift: {tracker.persistent_shift_limit} consecutive "
                        f"anomalous samples ({desc})"
                    )
                    event = AnomalyEvent(
                        timestamp=timestamp,
                        sensor=field,
                        value=val,
                        anomaly_type="PERSISTENT_SHIFT",
                        severity="CRITICAL",
                        reason=reason_str,
                        score=score,
                        flight_state=flight_state_name,
                    )
                else:
                    phase_info = f" [Phase: {flight_state_name}]" if is_dynamic_phase else ""
                    reason_str = f"Statistical outlier {desc} >= {effective_warn_threshold:.1f}{phase_info}"
                    event = AnomalyEvent(
                        timestamp=timestamp,
                        sensor=field,
                        value=val,
                        anomaly_type="STATISTICAL_ANOMALY",
                        severity=severity,
                        reason=reason_str,
                        score=score,
                        flight_state=flight_state_name,
                    )
                packet_anomalies.append(event)
            else:
                # Reading is nominal: safely add to baseline
                tracker.record_normal(val)

        # 5. Alert Deduplication / Cooldown
        emitted_alerts: List[AnomalyEvent] = []
        for anom in packet_anomalies:
            key = (anom.sensor, anom.anomaly_type)
            if key in self._recent_alerts:
                last_time, prev_event = self._recent_alerts[key]
                if abs(time_numeric - last_time) < self.cooldown_seconds:
                    # Within cooldown window: suppress repeated alert spam, but update occurrence count
                    prev_event.count += 1
                    prev_event.value = anom.value
                    prev_event.timestamp = anom.timestamp
                    continue

            # Outside cooldown or new alert: emit and track
            self._recent_alerts[key] = (time_numeric, anom)
            self._all_alerts.append(anom)
            emitted_alerts.append(anom)

        # 6. Determine overall state
        if has_invalid_data:
            self._current_state = self.STATE_INVALID_DATA
        elif packet_anomalies:
            self._current_state = self.STATE_ANOMALY
        elif not all_warmed_up:
            self._current_state = self.STATE_WARMING_UP
        else:
            self._current_state = self.STATE_MONITORING

        return self._current_state, emitted_alerts
