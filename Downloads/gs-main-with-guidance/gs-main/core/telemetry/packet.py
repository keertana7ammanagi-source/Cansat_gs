import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dataclasses import dataclass
from typing import Optional

from core.telemetry.constants import FIELD_NAMES, FLOAT_FIELDS, INT_FIELDS, TEAM_ID
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
        if name in self.fields:
            return self.fields[name]
        raise AttributeError(name)

def parse_packet(line: str) -> TelemetryPacket:
    raw = line.strip()
    parts = [p.strip() for p in raw.split(",")]

    if len(parts) != len(FIELD_NAMES):
        logger.warning(f"Field count mismatch: expected {len(FIELD_NAMES)}, got {len(parts)}")
        raise PacketParseError(f"Expected {len(FIELD_NAMES)} fields, got {len(parts)}")

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

    if fields["TEAM_ID"] != TEAM_ID:
        raise PacketParseError(f"TEAM_ID mismatch: {fields['TEAM_ID']!r} vs {TEAM_ID!r}")

    return TelemetryPacket(raw_line=raw, fields=fields)

# Move PacketSequencer here or keep in separate file.