"""
Comprehensive Tests for Offline Anomaly Detection Module.
CAN-7USAT Ground Station – IN-SPACe 2026.

All tests utilize labelled SYNTHETIC test data.
"""

import math
import os
import sys
import tempfile
from pathlib import Path
import pytest

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ai.anomaly_detector import (
    AnomalyDetector,
    SensorBaselineTracker,
    AnomalyEvent,
    DEFAULT_ENGINEERING_LIMITS,
)
from core.telemetry.packet import parse_packet, add_legacy_aliases
from core.telemetry.constants import TEAM_ID, FIELD_NAMES
from core.data.csv_logger import CSVLogger


def make_synthetic_packet(overrides=None):
    """Generate a valid 37-field synthetic telemetry packet dictionary."""
    packet_data = {
        "TEAM_ID": TEAM_ID,
        "TIMESTAMP": 10.0,
        "PACKET_COUNT": 1,
        "ALTITUDE": 500.0,
        "PRESSURE": 95000.0,
        "TEMP": 25.0,
        "VOLTAGE": 7.40,
        "GNSS_TIME": "12:00:00",
        "GNSS_LATITUDE": 28.6129,
        "GNSS_LONGITUDE": 77.2295,
        "GNSS_ALTITUDE": 500.0,
        "GNSS_SATS": 10,
        "ACCEL_X": 0.05,
        "ACCEL_Y": -0.02,
        "ACCEL_Z": 9.81,
        "GYRO_X": 0.0,
        "GYRO_Y": 0.0,
        "GYRO_Z": 0.0,
        "MAG_X": 25.0,
        "MAG_Y": -15.0,
        "MAG_Z": 42.0,
        "ROLL": 0.5,
        "PITCH": -0.3,
        "YAW": 120.0,
        "LIGHT_LUX": 500.0,
        "UV_INDEX": 2.5,
        "HALL_RPM": 1200.0,
        "FLIGHT_SOFTWARE_STATE": 2,  # LAUNCH_PAD
        "REL_ALTITUDE": 500.0,
        "VERTICAL_SPEED": 0.0,
        "GNSS_GROUND_SPEED": 0.0,
        "GNSS_COURSE": 0.0,
        "GNSS_HDOP": 1.2,
        "GNSS_FIX": 3,
        "HUMIDITY": 50.0,
        "CURRENT": 350.0,
        "POWER": 2590.0,
    }
    if overrides:
        packet_data.update(overrides)
    return packet_data


# =========================================================================
# 1. Warmup and Insufficient Baseline Samples
# =========================================================================

def test_warmup_insufficient_samples():
    """Verify that detector remains in INSUFFICIENT_BASELINE_SAMPLES until min_samples is met."""
    detector = AnomalyDetector(min_samples=10, window_size=20)
    for i in range(10):
        pkt = make_synthetic_packet({"TIMESTAMP": float(i), "TEMP": 24.0 + 0.05 * i})
        state, alerts = detector.process_packet(pkt)
        assert state == AnomalyDetector.STATE_WARMING_UP
        assert len(alerts) == 0

    # 11th sample (index 10) now has 10 prior baseline samples -> transitions to MONITORING
    pkt = make_synthetic_packet({"TIMESTAMP": 10.0, "TEMP": 24.5})
    state, alerts = detector.process_packet(pkt)
    assert state == AnomalyDetector.STATE_MONITORING
    assert len(alerts) == 0


# =========================================================================
# 2. Normal Steady Telemetry
# =========================================================================

def test_normal_steady_telemetry():
    """Verify that nominal readings within physical bounds trigger zero alerts."""
    detector = AnomalyDetector(min_samples=5, window_size=15)
    for i in range(20):
        # Small realistic Gaussian-like noise around 25.0 C, 95000 Pa, 7.4 V
        pkt = make_synthetic_packet({
            "TIMESTAMP": float(i),
            "TEMP": 25.0 + (0.1 if i % 2 == 0 else -0.1),
            "PRESSURE": 95000.0 + (10.0 if i % 2 == 0 else -10.0),
            "VOLTAGE": 7.40 + (0.01 if i % 2 == 0 else -0.01),
        })
        state, alerts = detector.process_packet(pkt)
        if i >= 5:
            assert state == AnomalyDetector.STATE_MONITORING
            assert len(alerts) == 0


# =========================================================================
# 3. Sudden Isolated Outlier Spike & Baseline Protection
# =========================================================================

def test_isolated_outlier_spike_detection():
    """Verify that a sudden statistical spike is flagged."""
    detector = AnomalyDetector(min_samples=10, window_size=20, warning_z_score=3.0)
    # Feed 10 steady baseline samples (25 °C)
    for i in range(10):
        detector.process_packet(make_synthetic_packet({"TIMESTAMP": float(i), "TEMP": 25.0}))

    # Inject isolated spike: 45 °C (Z-score >> 3.0)
    spike_pkt = make_synthetic_packet({"TIMESTAMP": 11.0, "TEMP": 45.0})
    state, alerts = detector.process_packet(spike_pkt)

    assert state == AnomalyDetector.STATE_ANOMALY
    assert len(alerts) >= 1
    temp_alert = [a for a in alerts if a.sensor == "TEMP"][0]
    assert temp_alert.anomaly_type == "STATISTICAL_ANOMALY"
    assert temp_alert.severity in ("WARNING", "CRITICAL")
    assert temp_alert.score > 3.0


def test_baseline_protection_quarantines_outliers():
    """
    Verify that an anomalous spike is quarantined and NOT included in the baseline,
    so that subsequent normal samples are NOT falsely flagged due to baseline contamination.
    """
    detector = AnomalyDetector(min_samples=10, window_size=20, warning_z_score=3.0)
    for i in range(10):
        detector.process_packet(make_synthetic_packet({"TIMESTAMP": float(i), "TEMP": 25.0}))

    # Inject isolated spike
    detector.process_packet(make_synthetic_packet({"TIMESTAMP": 11.0, "TEMP": 45.0}))

    # Baseline stats for TEMP should still have median=25.0, not contaminated by 45.0
    summary = detector.get_sensor_summary()["TEMP"]
    assert summary["median"] == 25.0

    # Next normal sample (25.0 °C) should be completely nominal
    norm_pkt = make_synthetic_packet({"TIMESTAMP": 12.0, "TEMP": 25.0})
    state, alerts = detector.process_packet(norm_pkt)
    assert state == AnomalyDetector.STATE_MONITORING
    assert len(alerts) == 0


# =========================================================================
# 4. Physical & Engineering Limit Violations
# =========================================================================

def test_engineering_limit_violations():
    """Verify bounds violations on confirmed & provisional limits."""
    detector = AnomalyDetector(min_samples=5, window_size=15)

    # 1. Temperature exceeds BMP/SHT limit (> 85 °C)
    pkt_high_temp = make_synthetic_packet({"TIMESTAMP": 1.0, "TEMP": 105.0})
    state, alerts = detector.process_packet(pkt_high_temp)
    assert any(a.sensor == "TEMP" and a.anomaly_type == "LIMIT_VIOLATION" and a.severity == "CRITICAL" for a in alerts)

    # 2. Voltage below safe operating bounds (< 5.0 V)
    pkt_low_volt = make_synthetic_packet({"TIMESTAMP": 2.0, "VOLTAGE": 3.80})
    state, alerts = detector.process_packet(pkt_low_volt)
    assert any(a.sensor == "VOLTAGE" and a.anomaly_type == "LIMIT_VIOLATION" for a in alerts)

    # 3. Negative humidity (< 0 %)
    pkt_neg_hum = make_synthetic_packet({"TIMESTAMP": 3.0, "HUMIDITY": -10.0})
    state, alerts = detector.process_packet(pkt_neg_hum)
    assert any(a.sensor == "HUMIDITY" and a.anomaly_type == "LIMIT_VIOLATION" for a in alerts)


# =========================================================================
# 5. Numerical Safety (Zero Variance, NaN, Inf, Non-Numeric)
# =========================================================================

def test_zero_variance_numerical_safety():
    """
    Verify that a sensor with zero standard deviation (perfectly flat baseline)
    does not cause ZeroDivisionError, Inf scores, or false alarms on identical readings.
    """
    tracker = SensorBaselineTracker(sensor_name="TEMP", min_samples=5, min_delta=0.5)
    for _ in range(10):
        tracker.record_normal(24.5)

    stats = tracker.get_stats()
    assert stats["std"] == 0.0
    assert stats["mad"] == 0.0

    # Test exact identical reading -> score 0.0
    score, desc = tracker.score_sample(24.5)
    assert score == 0.0
    assert not math.isinf(score)
    assert not math.isnan(score)

    # Test tiny sub-resolution deviation (< min_delta 0.5) -> score 0.0 (no false alarm)
    score_small, _ = tracker.score_sample(24.6)
    assert score_small == 0.0

    # Test significant deviation (> min_delta 0.5) -> safe non-infinite score
    score_large, desc_large = tracker.score_sample(27.5)
    assert score_large > 3.0
    assert not math.isinf(score_large)


def test_data_quality_nan_inf_corrupt():
    """Verify safe handling of NaN, Inf, and corrupt string values."""
    detector = AnomalyDetector(min_samples=5)

    # NaN value
    pkt_nan = make_synthetic_packet({"TIMESTAMP": 1.0, "TEMP": float("nan")})
    state, alerts = detector.process_packet(pkt_nan)
    assert state == AnomalyDetector.STATE_INVALID_DATA
    assert any(a.sensor == "TEMP" and a.anomaly_type == "DATA_QUALITY" for a in alerts)

    # Inf value
    pkt_inf = make_synthetic_packet({"TIMESTAMP": 2.0, "PRESSURE": float("inf")})
    state, alerts = detector.process_packet(pkt_inf)
    assert state == AnomalyDetector.STATE_INVALID_DATA
    assert any(a.sensor == "PRESSURE" and a.anomaly_type == "DATA_QUALITY" for a in alerts)

    # Corrupt string that cannot be cast to float
    pkt_str = make_synthetic_packet({"TIMESTAMP": 3.0, "VOLTAGE": "MALFORMED_FLOAT"})
    state, alerts = detector.process_packet(pkt_str)
    assert state == AnomalyDetector.STATE_INVALID_DATA
    assert any(a.sensor == "VOLTAGE" and a.anomaly_type == "DATA_QUALITY" for a in alerts)


# =========================================================================
# 6. Alert Deduplication & Cooldown
# =========================================================================

def test_alert_deduplication_cooldown():
    """Verify that repeated identical anomalies within cooldown do not flood the UI."""
    cooldown_s = 5.0
    detector = AnomalyDetector(min_samples=5, cooldown_seconds=cooldown_s)

    # Warmup
    for i in range(5):
        detector.process_packet(make_synthetic_packet({"TIMESTAMP": float(i), "VOLTAGE": 7.4}))

    # First anomaly at t=6.0 s
    pkt1 = make_synthetic_packet({"TIMESTAMP": 6.0, "VOLTAGE": 4.2})
    _, alerts1 = detector.process_packet(pkt1)
    assert len(alerts1) == 1
    assert alerts1[0].count == 1

    # Second identical anomaly at t=7.0 s (< cooldown 5.0s) -> should be suppressed
    pkt2 = make_synthetic_packet({"TIMESTAMP": 7.0, "VOLTAGE": 4.2})
    _, alerts2 = detector.process_packet(pkt2)
    assert len(alerts2) == 0  # Deduplicated / suppressed

    # Third anomaly at t=12.0 s (> cooldown 5.0s) -> should emit new alert
    pkt3 = make_synthetic_packet({"TIMESTAMP": 12.0, "VOLTAGE": 4.2})
    _, alerts3 = detector.process_packet(pkt3)
    assert len(alerts3) == 1


# =========================================================================
# 7. Flight-Phase Awareness
# =========================================================================

def test_flight_phase_awareness_avoids_false_positives():
    """
    Verify that during dynamic flight phases (DESCENT, ASCENT), legitimate rapid
    altitude/pressure drops are not classified as sensor failures.
    """
    detector = AnomalyDetector(min_samples=5, window_size=15, warning_z_score=3.0)

    # Establish initial baseline at launchpad (altitude=500m)
    for i in range(10):
        detector.process_packet(make_synthetic_packet({
            "TIMESTAMP": float(i),
            "ALTITUDE": 500.0,
            "PRESSURE": 95000.0,
            "FLIGHT_SOFTWARE_STATE": 2,  # LAUNCH_PAD
            "FLIGHT_STATE_NAME": "LAUNCH_PAD",
        }))

    # Now transition to DESCENT: altitude drops from 500m to 470m (legitimate parachute descent)
    descent_pkt = make_synthetic_packet({
        "TIMESTAMP": 11.0,
        "ALTITUDE": 470.0,
        "PRESSURE": 95300.0,
        "FLIGHT_SOFTWARE_STATE": 5,  # DESCENT
        "FLIGHT_STATE_NAME": "DESCENT",
    })
    state, alerts = detector.process_packet(descent_pkt)

    # Altitude alert should NOT be triggered due to phase adaptation
    alt_alerts = [a for a in alerts if a.sensor == "ALTITUDE"]
    assert len(alt_alerts) == 0


# =========================================================================
# 8. Persistent Faults & Step Changes
# =========================================================================

def test_persistent_shift_detection():
    """
    Verify that when a sensor steps to a new persistent value,
    after persistent_shift_limit consecutive samples it triggers a PERSISTENT_SHIFT alert
    and subsequently adapts the baseline.
    """
    detector = AnomalyDetector(min_samples=5, window_size=10, persistent_shift_limit=5)
    # Baseline at 20.0 °C
    for i in range(5):
        detector.process_packet(make_synthetic_packet({"TIMESTAMP": float(i), "TEMP": 20.0}))

    # Sensor steps permanently to 30.0 °C
    shift_detected = False
    for i in range(5, 12):
        pkt = make_synthetic_packet({"TIMESTAMP": float(i), "TEMP": 30.0})
        _, alerts = detector.process_packet(pkt)
        if any(a.anomaly_type == "PERSISTENT_SHIFT" for a in alerts):
            shift_detected = True

    assert shift_detected, "PERSISTENT_SHIFT should have been triggered"

    # Once adapted, new samples around 30.0 °C should become normal
    pkt_norm = make_synthetic_packet({"TIMESTAMP": 15.0, "TEMP": 30.0})
    state, alerts = detector.process_packet(pkt_norm)
    assert not any(a.sensor == "TEMP" for a in alerts)


# =========================================================================
# 9. Synthetic Labelled Evaluation (Confusion Matrix Reporting)
# =========================================================================

def test_synthetic_labelled_evaluation_report():
    """
    Evaluate against a synthetic benchmark with ground-truth labels.
    Calculates TP, FP, TN, FN.
    Label: 0 = Normal, 1 = Outlier/Fault.
    """
    detector = AnomalyDetector(min_samples=10, window_size=20, warning_z_score=3.0)

    # 50 synthetic test samples:
    # 0-14: Normal steady (0)
    # 15: Injected spike at 50 °C (1)
    # 16-24: Normal steady (0)
    # 25: Voltage limit breach 3.5 V (1)
    # 26-34: Normal steady (0)
    # 35: NaN temperature (1)
    # 36-49: Normal steady (0)

    test_stream = []
    for t in range(50):
        label = 0
        overrides = {"TIMESTAMP": float(t), "TEMP": 24.0, "VOLTAGE": 7.4}
        if t == 15:
            overrides["TEMP"] = 55.0
            label = 1
        elif t == 25:
            overrides["VOLTAGE"] = 3.5
            label = 1
        elif t == 35:
            overrides["TEMP"] = float("nan")
            label = 1
        test_stream.append((overrides, label))

    tp, fp, tn, fn = 0, 0, 0, 0

    for idx, (overrides, true_label) in enumerate(test_stream):
        pkt = make_synthetic_packet(overrides)
        _, alerts = detector.process_packet(pkt)
        # We evaluate detection after warmup (idx >= 10)
        if idx >= 10:
            predicted_anomaly = 1 if len(alerts) > 0 else 0
            if true_label == 1 and predicted_anomaly == 1:
                tp += 1
            elif true_label == 0 and predicted_anomaly == 1:
                fp += 1
            elif true_label == 0 and predicted_anomaly == 0:
                tn += 1
            elif true_label == 1 and predicted_anomaly == 0:
                fn += 1

    # Report results
    print(f"\n[SYNTHETIC TEST BENCHMARK] TP: {tp}, FP: {fp}, TN: {tn}, FN: {fn}")
    assert tp == 3, f"Expected 3 True Positives, got {tp}"
    assert fp == 0, f"Expected 0 False Positives, got {fp}"
    assert fn == 0, f"Expected 0 False Negatives, got {fn}"


# =========================================================================
# 10. End-to-End Regression with Existing Telemetry Pipeline & CSV Logger
# =========================================================================

def test_regression_with_packet_parsing_and_csv_logger():
    """Verify that existing packet parser, aliases, and CSVLogger operate alongside detector."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / f"Flight_{TEAM_ID}.csv"
        logger = CSVLogger(filepath=str(csv_path))
        detector = AnomalyDetector(min_samples=5)

        # Create valid wire format line
        values = {name: "" for name in FIELD_NAMES}
        values.update({
            "TEAM_ID": TEAM_ID, "TIMESTAMP": "15.0", "PACKET_COUNT": "42",
            "ALTITUDE": "700.0", "PRESSURE": "94000", "TEMP": "24.0",
            "VOLTAGE": "7.60", "GNSS_TIME": "00:00:15",
            "GNSS_LATITUDE": "28.6129", "GNSS_LONGITUDE": "77.2295",
            "GNSS_ALTITUDE": "700.0", "GNSS_SATS": "9",
            "ACCEL_X": "0.12", "ACCEL_Y": "0.08", "ACCEL_Z": "9.81",
            "ROLL": "1.4", "PITCH": "-0.6", "YAW": "45.2",
            "LIGHT_LUX": "200", "UV_INDEX": "3.0",
            "FLIGHT_SOFTWARE_STATE": "5", "REL_ALTITUDE": "700.0",
            "VERTICAL_SPEED": "0.0", "HUMIDITY": "45.0",
            "CURRENT": "318.0", "POWER": "2401.0",
        })
        raw_line = ",".join(values[name] for name in FIELD_NAMES)

        # 1. Parse packet using existing logic
        packet = add_legacy_aliases(parse_packet(raw_line))
        assert packet.get("ALTITUDE") == 700.0
        assert packet.get("FLIGHT_STATE_NAME") == "DESCENT"

        # 2. Existing CSV logger writes without issue
        logger.log(packet)
        assert csv_path.exists()
        assert csv_path.stat().st_size > 0

        # 3. Anomaly detector processes packet without side effects
        state, alerts = detector.process_packet(packet)
        assert state in (AnomalyDetector.STATE_WARMING_UP, AnomalyDetector.STATE_MONITORING)

        # Close file explicitly so Windows temp directory cleanup succeeds
        logger._file.close()
