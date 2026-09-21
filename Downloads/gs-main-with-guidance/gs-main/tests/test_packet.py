"""
Unit tests for telemetry packet parsing.

Rewritten against the CAN-7USAT's actual 24-field packet (see
core/telemetry/constants.py FIELD_NAMES) -- the previous version of this
file tested a stale 28-field layout that matched neither the real
hardware format nor the ground station's own constants.py, so it was
failing (or silently meaningless) either way.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.telemetry.packet import parse_packet, add_legacy_aliases, PacketParseError
from core.telemetry.constants import FIELD_NAMES, TEAM_ID

# A valid 24-field line, in FIELD_NAMES order:
# TEAM_ID,TIME_STAMPING,PACKET_COUNT,ALTITUDE,PRESSURE,TEMP,VOLTAGE,
# GNSS_TIME,GNSS_LATITUDE,GNSS_LONGITUDE,GNSS_ALTITUDE,GNSS_SATS,
# ACCELEROMETER_DATA,GYRO_SPIN_RATE,FLIGHT_SOFTWARE_STATE,
# HUM,UV,LUX,CURRENT,POWER,ROLL,PITCH,YAW,CAM_A_STATUS
VALID_PACKET = (
    f"{TEAM_ID},12.0,1,700.0,94000,24.0,7.60,"
    "00:00:12,28.6129,77.2295,700.0,9,"
    "0.12;0.08;9.81,12.4,5,"
    "45.0,3.0,200,318.0,2401.0,1.4,-0.6,45.2,1"
)


def test_field_count_matches_constants():
    """FIELD_NAMES must have exactly 24 entries -- this is the whole
    point of the fix: the ground station used to expect 32."""
    assert len(FIELD_NAMES) == 24


def test_parse_valid_packet():
    packet = parse_packet(VALID_PACKET)
    assert packet.get("TEAM_ID") == TEAM_ID
    assert packet.get("ALTITUDE") == 700.0
    assert packet.get("FLIGHT_SOFTWARE_STATE") == 5
    assert packet.get("CAM_A_STATUS") == 1
    assert packet.get("LUX") == 200
    assert isinstance(packet.get("LUX"), int)
    assert isinstance(packet.get("ALTITUDE"), float)


def test_parse_invalid_field_count():
    """A line with the wrong number of fields must be rejected, not
    silently truncated or padded."""
    raw = f"{TEAM_ID},12.0,1,700.0"
    try:
        parse_packet(raw)
        assert False, "Should have raised PacketParseError"
    except PacketParseError:
        pass


def test_parse_wrong_team_id():
    raw = VALID_PACKET.replace(TEAM_ID, "WRONG-TEAM-ID")
    try:
        parse_packet(raw)
        assert False, "Should have raised PacketParseError"
    except PacketParseError:
        pass


def test_parse_float_field_error():
    raw = VALID_PACKET.replace("700.0,94000", "NOT_A_NUMBER,94000", 1)
    try:
        parse_packet(raw)
        assert False, "Should have raised PacketParseError"
    except PacketParseError:
        pass


def test_accelerometer_data_is_split_into_axes():
    """ACCELEROMETER_DATA arrives packed as 'ax;ay;az' in one CSV field;
    add_legacy_aliases() must split it for the dashboards/plots."""
    packet = add_legacy_aliases(parse_packet(VALID_PACKET))
    assert packet.get("ACCELEROMETER_DATA") == "0.12;0.08;9.81"
    assert packet.get("ACCEL_X") == 0.12
    assert packet.get("ACCEL_Y") == 0.08
    assert packet.get("ACCEL_Z") == 9.81


def test_malformed_accelerometer_data_does_not_crash():
    """A malformed accel field (wrong number of parts) should be logged
    and skipped, not raise -- one bad axis shouldn't drop the whole packet."""
    raw = VALID_PACKET.replace("0.12;0.08;9.81", "0.12;0.08", 1)
    packet = add_legacy_aliases(parse_packet(raw))
    assert packet.get("ACCEL_X") is None


def test_flight_state_name_alias():
    packet = add_legacy_aliases(parse_packet(VALID_PACKET))
    assert packet.get("FLIGHT_STATE_NAME") == "DESCENT"  # state 5


if __name__ == "__main__":
    test_field_count_matches_constants()
    test_parse_valid_packet()
    test_parse_invalid_field_count()
    test_parse_wrong_team_id()
    test_parse_float_field_error()
    test_accelerometer_data_is_split_into_axes()
    test_malformed_accelerometer_data_does_not_crash()
    test_flight_state_name_alias()
    print("All packet tests passed!")