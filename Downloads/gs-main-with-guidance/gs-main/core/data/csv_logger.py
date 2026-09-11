"""
CSV Logger – writes telemetry packets to a CSV file.
"""
import csv
import os
from pathlib import Path

from config.config_loader import Config
from core.telemetry.constants import FIELD_NAMES, TEAM_ID
from utils.logger import get_logger

logger = get_logger(__name__)


class CSVLogger:
    def __init__(self, filepath: str = None):
        cfg = Config()
        if filepath is None:
            # Build path: data/flights/Flight_<TEAM_ID>.csv
            base = cfg.get('paths.flights', 'data/flights/')
            filename = f"Flight_{TEAM_ID}.csv"
            filepath = str(Path(base) / filename)

        self.filepath = Path(filepath)
        # Ensure directory exists
        self.filepath.parent.mkdir(parents=True, exist_ok=True)

        is_new = not self.filepath.exists()
        self._file = open(self.filepath, 'a', newline='')
        self._writer = csv.writer(self._file)

        if is_new:
            self._writer.writerow(FIELD_NAMES)
            self._file.flush()
            logger.info(f"CSV log created: {self.filepath}")

    def log(self, packet):
        """Write a TelemetryPacket to the CSV."""
        try:
            row = [packet.fields.get(name, '') for name in FIELD_NAMES]
            self._writer.writerow(row)
            self._file.flush()
        except Exception as e:
            logger.error(f"CSV write error: {e}")

    def close(self):
        if self._file and not self._file.closed:
            self._file.close()
            logger.debug("CSV file closed.")