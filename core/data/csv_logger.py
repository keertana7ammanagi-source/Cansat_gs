"""
CSV Logger — writes 37-column telemetry to Flight_<TEAM_ID>.csv

Values are rounded to the resolution the rulebook requires (section 6.3
table) before being written, so the judged CSV matches what was actually
transmitted rather than raw Python float noise (e.g. writing "94012" Pa
instead of "94011.999999997").
"""
import csv
import os
import shutil
from pathlib import Path

from config.config_loader import Config
from core.telemetry.constants import FIELD_NAMES, TEAM_ID
from utils.logger import get_logger

logger = get_logger(__name__)

# Decimal places per field. Mandatory fields (ALTITUDE, PRESSURE, TEMP,
# VOLTAGE, GNSS_LATITUDE, GNSS_LONGITUDE, GNSS_ALTITUDE) come straight
# from the rule table's resolution column. TIME_STAMPING is rounded to
# 0.1 s, better than the "one second or better" requirement. The sensor
# extras match the precision the firmware actually transmits at (see
# firmware/flight_transmitter.ino's snprintf format string) so the CSV
# never implies more precision than was really sent over the air.
# Fields not listed here (TEAM_ID, PACKET_COUNT, GNSS_SATS, GNSS_TIME,
# FLIGHT_SOFTWARE_STATE) are integers or strings and are written as-is.
FIELD_RESOLUTION = {
    "TIMESTAMP": 1,
    "TIME_STAMPING": 1,
    "ALTITUDE": 1,
    "PRESSURE": 0,
    "TEMP": 1,
    "VOLTAGE": 2,
    "GNSS_LATITUDE": 4,
    "GNSS_LONGITUDE": 4,
    "GNSS_ALTITUDE": 1,
    "GYRO_SPIN_RATE": 2,
    "HUM": 1,
    "UV": 1,
    "CURRENT": 2,
    "POWER": 2,
    "ROLL": 1,
    "PITCH": 1,
    "YAW": 1,
    "ACCEL_X": 2, "ACCEL_Y": 2, "ACCEL_Z": 2,
    "GYRO_X": 2, "GYRO_Y": 2, "GYRO_Z": 2,
    "MAG_X": 2, "MAG_Y": 2, "MAG_Z": 2,
    "REL_ALTITUDE": 1, "VERTICAL_SPEED": 2,
    "GNSS_GROUND_SPEED": 2, "GNSS_COURSE": 1, "GNSS_HDOP": 2,
    "HUMIDITY": 1, "UV_INDEX": 1, "HALL_RPM": 2,
}


def _format_value(name, value):
    if value is None or value == '':
        return ''
    decimals = FIELD_RESOLUTION.get(name)
    if decimals is None:
        return value
    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return value


class CSVLogger:
    def __init__(self, filepath: str = None):
        cfg = Config()
        if filepath is None:
            # The competition upload expects the named CSV in the GCS root.
            # Anchor it to this repository rather than the process working
            # directory so shortcuts/launch scripts produce the same file.
            project_root = Path(__file__).resolve().parents[2]
            filepath = str(project_root / f"Flight_{TEAM_ID}.csv")

        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)

        # Upgrade the existing legacy header/rows in place so future 37-field
        # telemetry does not get appended under a stale 24-column header.
        if self.filepath.exists() and self.filepath.stat().st_size:
            self._upgrade_existing_file()

        is_new = not self.filepath.exists()
        self._file = open(self.filepath, 'a', newline='')
        self._writer = csv.writer(self._file)

        if is_new:
            self._writer.writerow(FIELD_NAMES)
            self._file.flush()
            logger.info(f"CSV created: {self.filepath} ({len(FIELD_NAMES)} columns)")

    def _upgrade_existing_file(self):
        with self.filepath.open("r", newline="", encoding="utf-8-sig") as source:
            reader = csv.DictReader(source)
            old_names = reader.fieldnames or []
            if old_names == FIELD_NAMES:
                return
            rows = list(reader)
        aliases = {
            "TIMESTAMP": "TIME_STAMPING", "HUMIDITY": "HUM", "UV_INDEX": "UV",
            "LIGHT_LUX": "LUX", "HALL_RPM": "GYRO_SPIN_RATE",
            "ACCEL_X": "ACCEL_R", "ACCEL_Y": "ACCEL_P", "ACCEL_Z": "ACCEL_Y",
            "ROLL": "GYRO_R", "PITCH": "GYRO_P", "YAW": "GYRO_Y",
            "MAG_X": "MAG_R", "MAG_Y": "MAG_P", "MAG_Z": "MAG_Y",
            "FLIGHT_SOFTWARE_STATE": "FLIGHT_STATE", "LIGHT_LUX": "LIGHT_INTENSITY",
            "HALL_RPM": "ROTOR_RPM", "REL_ALTITUDE": "ALTITUDE",
        }
        temp_path = self.filepath.with_suffix(self.filepath.suffix + ".migrating")
        backup_path = self.filepath.with_suffix(self.filepath.suffix + ".legacy.bak")
        if not backup_path.exists():
            shutil.copy2(self.filepath, backup_path)
        with temp_path.open("w", newline="", encoding="utf-8") as target:
            writer = csv.DictWriter(target, fieldnames=FIELD_NAMES)
            writer.writeheader()
            for old in rows:
                row = {name: old.get(name, "") for name in FIELD_NAMES}
                for name, alias in aliases.items():
                    if not row[name]:
                        row[name] = old.get(alias, "")
                if not row["TEAM_ID"]:
                    row["TEAM_ID"] = old.get("TEAM_ID", "")
                writer.writerow(row)
        os.replace(temp_path, self.filepath)
        logger.info("Migrated existing flight CSV to the current 37-field schema")

    def log(self, packet):
        """Write a normalized telemetry row (37 columns), rounded to spec resolution."""
        try:
            row = [
                _format_value(name, packet.fields.get(name, ''))
                for name in FIELD_NAMES
            ]
            self._writer.writerow(row)
            self._file.flush()
        except Exception as e:
            logger.error(f"CSV write error: {e}")

    def close(self):
        if self._file and not self._file.closed:
            self._file.close()
            logger.debug("CSV closed.")
