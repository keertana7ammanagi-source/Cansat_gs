"""Tests for the requested 37-field CAN-7USAT telemetry schema."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.telemetry.packet import parse_packet, add_legacy_aliases, PacketParseError
from core.telemetry.constants import FIELD_NAMES, LEGACY_FIELD_NAMES, TEAM_ID


def make_valid_packet():
    values = {name: "" for name in FIELD_NAMES}
    values.update({
        "TEAM_ID": TEAM_ID, "TIMESTAMP": "12.0", "PACKET_COUNT": "1",
        "ALTITUDE": "700.0", "PRESSURE": "94000", "TEMP": "24.0",
        "VOLTAGE": "7.60", "GNSS_TIME": "00:00:12",
        "GNSS_LATITUDE": "28.6129", "GNSS_LONGITUDE": "77.2295",
        "GNSS_ALTITUDE": "700.0", "GNSS_SATS": "9",
        "ACCEL_X": "0.12", "ACCEL_Y": "0.08", "ACCEL_Z": "9.81",
        "ROLL": "1.4", "PITCH": "-0.6", "YAW": "45.2",
        "LIGHT_LUX": "200", "UV_INDEX": "3.0",
        "FLIGHT_SOFTWARE_STATE": "5", "REL_ALTITUDE": "700.0",
        "VERTICAL_SPEED": "0.0", "HUMIDITY": "45.0",
        "CURRENT": "318.0", "POWER": "2401.0",
    })
    return ",".join(values[name] for name in FIELD_NAMES)


def test_field_count_matches_template():
    assert len(FIELD_NAMES) == 37
    assert FIELD_NAMES[-3:] == ["HUMIDITY", "CURRENT", "POWER"]
    assert "CAM_A_STATUS" not in FIELD_NAMES


def test_parse_valid_packet():
    packet = parse_packet(make_valid_packet())
    assert packet.get("TEAM_ID") == TEAM_ID
    assert packet.get("ALTITUDE") == 700.0
    assert packet.get("FLIGHT_SOFTWARE_STATE") == 5
    assert packet.get("ACCEL_X") == 0.12
    assert packet.get("LIGHT_LUX") == 200.0
    assert packet.get("HUMIDITY") == 45.0
    assert packet.get("CAM_A_STATUS") is None


def test_parse_invalid_field_count():
    try:
        parse_packet(f"{TEAM_ID},12.0,1,700.0")
        assert False, "Should have raised PacketParseError"
    except PacketParseError:
        pass


def test_parse_wrong_team_id():
    raw = make_valid_packet().replace(TEAM_ID, "WRONG-TEAM-ID", 1)
    try:
        parse_packet(raw)
        assert False, "Should have raised PacketParseError"
    except PacketParseError:
        pass


def test_parse_float_field_error():
    raw = make_valid_packet().replace("700.0,94000", "NOT_A_NUMBER,94000", 1)
    try:
        parse_packet(raw)
        assert False, "Should have raised PacketParseError"
    except PacketParseError:
        pass


def test_flight_state_name_alias():
    packet = add_legacy_aliases(parse_packet(make_valid_packet()))
    assert packet.get("FLIGHT_STATE_NAME") == "DESCENT"


def test_legacy_packet_is_still_parseable_without_camera_field_name():
    values = ["" for _ in LEGACY_FIELD_NAMES]
    values[0] = TEAM_ID
    values[1] = "12.0"
    values[2] = "1"
    values[3] = "700.0"
    values[4] = "94000"
    values[5] = "24.0"
    values[6] = "7.60"
    values[7] = "00:00:12"
    values[8] = "28.6129"
    values[9] = "77.2295"
    values[10] = "700.0"
    values[11] = "9"
    values[12] = "0.12;0.08;9.81"
    values[13] = "12.4"
    values[14] = "5"
    values[15:24] = ["45.0", "3.0", "200", "318.0", "2401.0", "1.4", "-0.6", "45.2", "1"]
    packet = parse_packet(",".join(values))
    assert packet.get("LEGACY_UNUSED_24") == "1"
    assert packet.get("CAM_A_STATUS") is None


if __name__ == "__main__":
    test_field_count_matches_template()
