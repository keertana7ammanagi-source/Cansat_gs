"""
scripts/guidance_e2e_smoke_test.py

Drives the REAL MainWindow (not a mock) through its REAL _handle_line()
path with fabricated telemetry lines, to prove the guidance wiring
actually works end-to-end: parse_packet -> dashboards/AI -> guidance ->
command transmit. Only the serial transport is stubbed (no physical
port available in this environment) -- everything else is the genuine
application code.

Run:
    QT_QPA_PLATFORM=offscreen python3 scripts/guidance_e2e_smoke_test.py
"""
import sys
import time

from PyQt5 import QtWebEngineWidgets  # noqa: F401  (must import before QApplication)
from PyQt5 import QtWidgets

app = QtWidgets.QApplication(sys.argv)

from ui.main_window import MainWindow
from core.telemetry.constants import TEAM_ID, FIELD_NAMES


class FakeSerialLink:
    """Records every command sent, in place of a real SerialLink."""
    def __init__(self):
        self.sent_commands = []

    def is_connected(self):
        return True

    def send_command(self, cmd):
        self.sent_commands.append(cmd)
        print(f"  [TX -> CanSat] {cmd}")


def build_line(fields: dict) -> str:
    """Build a raw CSV telemetry line from a dict of field overrides."""
    defaults = {
        "TEAM_ID": TEAM_ID, "TIME_STAMPING": "00:00:00", "PACKET_COUNT": "1",
        "ALTITUDE": "200.0", "PRESSURE": "940.0", "TEMP": "24.0", "VOLTAGE": "7.60",
        "GNSS_TIME": "00:00:00", "GNSS_LATITUDE": "13.00000", "GNSS_LONGITUDE": "77.00000",
        "GNSS_ALTITUDE": "200.0", "GNSS_SATS": "9",
        "ACCEL_R": "0.12", "ACCEL_P": "0.08", "ACCEL_Y": "9.81",
        "GYRO_R": "12.4", "GYRO_P": "8.7", "GYRO_Y": "3.2",
        "FLIGHT_STATE": "6",
        "HUMIDITY": "45.0", "UV_INDEX": "3.0", "LIGHT_INTENSITY": "200.0", "ROTOR_RPM": "2150",
        "MAG_R": "0.18", "MAG_P": "0.05", "MAG_Y": "0.41",
        "MODE": "1", "CMD_ECHO": "OK",
    }
    defaults.update({k: str(v) for k, v in fields.items()})
    return ",".join(defaults[name] for name in FIELD_NAMES)


def main():
    win = MainWindow()
    fake_serial = FakeSerialLink()
    win.serial_link = fake_serial  # stub the transport only

    print("=== Step 1: first packet with a GPS fix sets the reference ===")
    win._handle_line(build_line({
        "GNSS_LATITUDE": "13.00000", "GNSS_LONGITUDE": "77.00000",
        "ALTITUDE": "200.0", "FLIGHT_STATE": "6", "PACKET_COUNT": "1",
    }))
    assert win._guidance_reference_set, "reference should be set after first GPS fix"
    print("Reference set:", win._guidance_reference_set)

    print("\n=== Step 2: operator sets a target and arms guidance ===")
    # Target ~0m offset north-east of origin (simulate via the UI fields,
    # exactly as the operator would).
    win.guidance_dashboard.target_lat_input.setText("13.00090")   # ~100m north
    win.guidance_dashboard.target_lon_input.setText("77.00000")
    win._on_set_guidance_target()
    assert win.landing_controller.armed, "controller should be armed after SET TARGET"
    print("Controller armed:", win.landing_controller.armed)

    print("\n=== Step 3: feed a descending, eastward-drifting path ===")
    # East drift should eventually exceed the 20m cross-track threshold
    # and produce a transmitted GLIDE command; altitude gate should
    # force HOVER once below 50m.
    import math
    ref_lat, ref_lon = 13.00000, 77.00000
    m_per_deg_lat = 111320.0

    for i in range(12):
        north = 200.0 - i * 18.0     # descending toward the target's north offset
        east = i * 3.0                # drifting east -> growing cross-track error
        alt = 220.0 - i * 18.0

        lat = ref_lat + north / m_per_deg_lat
        lon = ref_lon + east / (m_per_deg_lat * math.cos(math.radians(ref_lat)))

        line = build_line({
            "GNSS_LATITUDE": f"{lat:.6f}", "GNSS_LONGITUDE": f"{lon:.6f}",
            "ALTITUDE": f"{alt:.1f}", "FLIGHT_STATE": "6",
            "PACKET_COUNT": str(i + 2),
        })
        win._handle_line(line)

        result_cmd = win.guidance_dashboard.val_command.text()
        xtrack = win.guidance_dashboard.val_xtrack.text()
        print(f"  packet {i+2}: alt={alt:6.1f}m east={east:5.1f}m "
              f"xtrack={xtrack:>8} cmd={result_cmd}")
        time.sleep(0.01)  # keep now_s strictly increasing under min_command_interval_s

    print("\n=== Step 4: flight-state gate -- wrong state must force HOVER ===")
    win._handle_line(build_line({
        "GNSS_LATITUDE": "13.00050", "GNSS_LONGITUDE": "77.00100",
        "ALTITUDE": "180.0", "FLIGHT_STATE": "3",  # ASCENT, not allowed
        "PACKET_COUNT": "99",
    }))
    print("  command after wrong-state packet:", win.guidance_dashboard.val_command.text())
    assert win.guidance_dashboard.val_command.text() == "HOVER"

    print("\n=== Step 5: MANUAL mode blocks automatic transmission ===")
    win.guidance_dashboard.manual_btn.setChecked(True)
    sent_before = len(fake_serial.sent_commands)
    win._handle_line(build_line({
        "GNSS_LATITUDE": "13.00050", "GNSS_LONGITUDE": "77.00300",
        "ALTITUDE": "150.0", "FLIGHT_STATE": "6",
        "PACKET_COUNT": "100",
    }))
    assert len(fake_serial.sent_commands) == sent_before, "MANUAL mode must not auto-transmit"
    print("  no new command sent in MANUAL mode (correct)")

    win.guidance_dashboard.manual_glide_left_btn.click()
    assert fake_serial.sent_commands[-1] == "GLIDE_LEFT"
    print("  manual override button sent:", fake_serial.sent_commands[-1])

    print("\n=== All commands transmitted over the run ===")
    for cmd in fake_serial.sent_commands:
        print(" ", cmd)

    print("\nE2E SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
