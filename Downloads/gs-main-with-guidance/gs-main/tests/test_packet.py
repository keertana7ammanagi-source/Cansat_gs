"""
Unit tests for telemetry packet parsing.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.telemetry.packet import parse_packet, PacketParseError
from core.telemetry.constants import FIELD_NAMES


def test_parse_valid_packet():
    """Test parsing a valid 28-field packet."""
    raw = (
        "2026-INSPACe-CAN-7USAT-036,00:00:01,1,"
        "700.0,940.0,24.0,7.60,"
        "00:00:01,28.6129,77.2295,700.0,9,"
        "0.12,0.08,9.81,"
        "12.4,8.7,3.2,"
        "5,"
        "45.0,3.0,200.0,2150,"
        "0.18,0.05,0.41,"
        "1,OK"
    )
    packet = parse_packet(raw)
    assert packet.get("ALTITUDE") == 700.0
    assert packet.get("FLIGHT_STATE") == "5"
    assert packet.get("TEAM_ID") == "2026-INSPACe-CAN-7USAT-036"


def test_parse_invalid_field_count():
    """Test that a packet with wrong field count raises an error."""
    raw = "2026-INSPACe-CAN-7USAT-036,00:00:01,1,700.0"
    try:
        parse_packet(raw)
        assert False, "Should have raised PacketParseError"
    except PacketParseError:
        assert True


def test_parse_wrong_team_id():
    """Test that a packet from a different team is rejected."""
    raw = "WRONG-TEAM,00:00:01,1,700.0,940.0,24.0,7.60,00:00:01,28.6129,77.2295,700.0,9,0.12,0.08,9.81,12.4,8.7,3.2,5,45.0,3.0,200.0,2150,0.18,0.05,0.41,1,OK"
    try:
        parse_packet(raw)
        assert False, "Should have raised PacketParseError"
    except PacketParseError:
        assert True


def test_parse_float_field_error():
    """Test that a non-numeric value in a float field raises an error."""
    raw = (
        "2026-INSPACe-CAN-7USAT-036,00:00:01,1,"
        "NOT_A_NUMBER,940.0,24.0,7.60,"
        "00:00:01,28.6129,77.2295,700.0,9,"
        "0.12,0.08,9.81,"
        "12.4,8.7,3.2,"
        "5,"
        "45.0,3.0,200.0,2150,"
        "0.18,0.05,0.41,"
        "1,OK"
    )
    try:
        parse_packet(raw)
        assert False, "Should have raised PacketParseError"
    except PacketParseError:
        assert True


if __name__ == "__main__":
    test_parse_valid_packet()
    test_parse_invalid_field_count()
    test_parse_wrong_team_id()
    test_parse_float_field_error()
    print("All packet tests passed!")