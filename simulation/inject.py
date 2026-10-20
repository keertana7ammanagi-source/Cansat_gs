"""Stream a judge-schema telemetry CSV into one end of a virtual COM pair.

Use the paired COM port in the GCS. This script must use the opposite end of
the virtual pair; a serial device cannot be opened by both programs at once.
"""
import argparse
import csv
import time
from pathlib import Path

import serial

from core.telemetry.constants import FIELD_NAMES, TEAM_ID


def load_packets(csv_path):
    with Path(csv_path).open("r", newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames:
            raise ValueError("CSV must have a header row")
        missing = [name for name in FIELD_NAMES if name not in reader.fieldnames]
        if missing:
            raise ValueError("CSV is missing current telemetry columns: " + ", ".join(missing))
        packets = []
        for row_number, row in enumerate(reader, start=2):
            if row.get("TEAM_ID") != TEAM_ID:
                raise ValueError(f"Row {row_number} has a different TEAM_ID")
            packets.append(",".join((row.get(name) or "") for name in FIELD_NAMES))
    if not packets:
        raise ValueError("CSV contains no telemetry rows")
    return packets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", help="virtual COM endpoint paired with the GCS endpoint")
    parser.add_argument("csv", help="37-column telemetry CSV to replay")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--interval", type=float, default=1.0, help="seconds between packets")
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error("--interval must be positive")

    packets = load_packets(args.csv)
    with serial.Serial(args.port, args.baud, timeout=0.1, write_timeout=1.0) as link:
        deadline = time.monotonic()
        try:
            for index, packet in enumerate(packets, start=1):
                wait = deadline - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                link.write((packet + "\n").encode("ascii"))
                link.flush()
                print(f"Injected packet {index}/{len(packets)}")
                deadline += args.interval
        except KeyboardInterrupt:
            print("Replay stopped by operator.")


if __name__ == "__main__":
    main()
