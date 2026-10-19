"""
CAN-7USAT Telemetry Packet Parser
Parses 24-field comma-separated telemetry and adds legacy aliases.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dataclasses import dataclass
from core.telemetry.constants import (
    FIELD_NAMES, FLOAT_FIELDS, INT_FIELDS, TEAM_ID,
    FIELD_ALIASES, FLIGHT_STATES,
)
from utils.logger import get_logger

logger = get_logger(__name__)


class PacketParseError(Exception):
    pass


@dataclass
class TelemetryPacket:
    raw_line: str
    fields: dict

    def get(self, name, default=None):
        return self.fields.get(name, default)

    def __getattr__(self, name):
        if name.startswith("_") or name in ("fields", "raw_line"):
            raise AttributeError(name)
        fields = self.__dict__.get("fields", {})
        if name in fields:
            return fields[name]
        raise AttributeError(name)


def parse_packet(line: str) -> TelemetryPacket:
    """Parse a raw telemetry line into a 24-field dictionary."""
    raw = line.strip()
    if not raw:
        raise PacketParseError("Empty line")

    parts = [p.strip() for p in raw.split(",")]

    if len(parts) != len(FIELD_NAMES):
        raise PacketParseError(
            f"Expected {len(FIELD_NAMES)} fields, got {len(parts)}"
        )

    fields = {}
    for name, value in zip(FIELD_NAMES, parts):
        if name in FLOAT_FIELDS:
            try:
                fields[name] = float(value)
            except ValueError:
                raise PacketParseError(f"Field {name} expected float, got {value!r}")
        elif name in INT_FIELDS:
            try:
                fields[name] = int(value)
            except ValueError:
                raise PacketParseError(f"Field {name} expected int, got {value!r}")
        else:
            fields[name] = value

    # Validate team ID
    if fields.get("TEAM_ID") != TEAM_ID:
        raise PacketParseError(f"TEAM_ID mismatch: {fields['TEAM_ID']!r}")

    return TelemetryPacket(raw_line=raw, fields=fields)


def _split_accelerometer_data(packet: TelemetryPacket) -> None:
    """
    ACCELEROMETER_DATA arrives as one CSV field packed "ax;ay;az" (m/s^2).
    Split it into ACCEL_X / ACCEL_Y / ACCEL_Z floats so dashboards and
    plots can consume individual axes without re-parsing the raw string.
    Leaves the original packed field untouched (still written to the CSV
    verbatim, as required).
    """
    raw = packet.fields.get("ACCELEROMETER_DATA")
    if not raw:
        return

    parts = str(raw).split(";")
    if len(parts) != 3:
        logger.warning(f"ACCELEROMETER_DATA malformed (expected ax;ay;az): {raw!r}")
        return

    try:
        packet.fields["ACCEL_X"] = float(parts[0])
        packet.fields["ACCEL_Y"] = float(parts[1])
        packet.fields["ACCEL_Z"] = float(parts[2])
    except ValueError:
        logger.warning(f"ACCELEROMETER_DATA has non-numeric axis value: {raw!r}")


def add_legacy_aliases(packet: TelemetryPacket) -> TelemetryPacket:
    """Add legacy key names and human-readable state name for old dashboards."""
    for old_key, new_key in FIELD_ALIASES.items():
        if new_key in packet.fields and old_key not in packet.fields:
            packet.fields[old_key] = packet.fields[new_key]

    _split_accelerometer_data(packet)

    # Human-readable flight state name
    state_num = packet.fields.get("FLIGHT_SOFTWARE_STATE")
    if state_num is not None:
        try:
            packet.fields["FLIGHT_STATE_NAME"] = FLIGHT_STATES.get(
                int(state_num), f"STATE_{state_num}"
            )
        except (ValueError, TypeError):
            packet.fields["FLIGHT_STATE_NAME"] = str(state_num)

    return packet