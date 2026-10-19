"""
CSV Logger — writes 24-column telemetry to Flight_<TEAM_ID>.csv

Values are rounded to the resolution the rulebook requires (section 6.3
table) before being written, so the judged CSV matches what was actually
transmitted rather than raw Python float noise (e.g. writing "94012" Pa
instead of "94011.999999997").
"""
import csv
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
# ACCELEROMETER_DATA, FLIGHT_SOFTWARE_STATE, LUX, CAM_A_STATUS) are
# either integers or strings and are written as-is.
FIELD_RESOLUTION = {
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
            base = cfg.get('paths.flights', 'data/flights/')
            filepath = str(Path(base) / f"Flight_{TEAM_ID}.csv")

        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)

        is_new = not self.filepath.exists()
        self._file = open(self.filepath, 'a', newline='')
        self._writer = csv.writer(self._file)

        if is_new:
            self._writer.writerow(FIELD_NAMES)
            self._file.flush()
            logger.info(f"CSV created: {self.filepath} ({len(FIELD_NAMES)} columns)")

    def log(self, packet):
        """Write a TelemetryPacket row (24 columns), rounded to spec resolution."""
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