"""Parse current 37-field or legacy 24-field CAN-7USAT comma-separated telemetry."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dataclasses import dataclass
from core.telemetry.constants import (
    FIELD_NAMES, LEGACY_FIELD_NAMES, FLOAT_FIELDS, INT_FIELDS, TEAM_ID,
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
    """Parse either the current 37-field team schema or legacy 24-field wire packets."""
    raw = line.strip()
    if not raw:
        raise PacketParseError("Empty line")

    parts = [p.strip() for p in raw.split(",")]

    names = FIELD_NAMES if len(parts) == len(FIELD_NAMES) else LEGACY_FIELD_NAMES
    if len(parts) != len(names):
        raise PacketParseError(
            f"Expected {len(FIELD_NAMES)} (current) or {len(LEGACY_FIELD_NAMES)} (legacy) fields, got {len(parts)}"
        )

    fields = {}
    for name, value in zip(names, parts):
        if value == "" and name != "TEAM_ID":
            fields[name] = None
            continue
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
    fields = packet.fields
    # Normalize the 37-field ground schema to the canonical dashboard keys.
    for alias, canonical in {
        "TIME_STAMPING": "TIMESTAMP", "HUM": "HUMIDITY", "UV": "UV_INDEX",
        "LUX": "LIGHT_LUX", "GYRO_SPIN_RATE": "HALL_RPM",
    }.items():
        if canonical in fields and alias not in fields:
            fields[alias] = fields[canonical]
    for canonical, alias in {
        "TIMESTAMP": "TIME_STAMPING", "HUMIDITY": "HUM", "UV_INDEX": "UV",
        "LIGHT_LUX": "LUX", "HALL_RPM": "GYRO_SPIN_RATE",
    }.items():
        if canonical not in fields and alias in fields:
            fields[canonical] = fields[alias]
    if "ACCELEROMETER_DATA" not in fields and all(k in fields for k in ("ACCEL_X", "ACCEL_Y", "ACCEL_Z")):
        fields["ACCELEROMETER_DATA"] = ";".join(str(fields[k]) for k in ("ACCEL_X", "ACCEL_Y", "ACCEL_Z"))
    # Missing extension fields remain empty for legacy packets and CSV output.
    for name in FIELD_NAMES:
        fields.setdefault(name, None)
    for old_key, new_key in FIELD_ALIASES.items():
        if new_key in fields and old_key not in fields:
            fields[old_key] = fields[new_key]

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
