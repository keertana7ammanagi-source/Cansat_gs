"""
CAN-7USAT Telemetry Field Definitions
24 flat fields — all comma-separated, no sub-fields
(ACCELEROMETER_DATA is the one exception: it is a single CSV field that
internally packs "ax;ay;az" — see core/telemetry/packet.py for the split).
"""

TEAM_ID = "2026-INSPACe-CAN-7USAT-036"

# ============================================================
# TELEMETRY COMMAND CONSTANTS (Rule 6.1.ii, 6.1.v, 6.1.vi)
# ============================================================
CMD_TELEMETRY_ON  = "CXON"      # Start telemetry transmission
CMD_TELEMETRY_OFF = "CXOFF"     # Stop telemetry transmission
CMD_CALIBRATE     = "CAL"       # Calibrate all sensors on pad (matches firmware's handleCommand)

# ============================================================
# THE 24 FIELDS — ORDER MATTERS (matches the flight transmitter)
# ============================================================
FIELD_NAMES = [
    # --- Mandatory IN-SPACe (15) ---
    "TEAM_ID",                # 1
    "TIME_STAMPING",          # 2  mission elapsed time, seconds
    "PACKET_COUNT",           # 3
    "ALTITUDE",               # 4  meters, relative to ground
    "PRESSURE",               # 5  pascals
    "TEMP",                   # 6  deg C (SHT40)
    "VOLTAGE",                # 7  volts
    "GNSS_TIME",              # 8  time from GNSS receiver (HH:MM:SS)
    "GNSS_LATITUDE",          # 9  degrees
    "GNSS_LONGITUDE",         # 10 degrees
    "GNSS_ALTITUDE",          # 11 meters
    "GNSS_SATS",              # 12 satellite count
    "ACCELEROMETER_DATA",     # 13 packed "ax;ay;az" (m/s^2)
    "GYRO_SPIN_RATE",         # 14 deg/s (Hall sensor)
    "FLIGHT_SOFTWARE_STATE",  # 15 0-7

    # --- Sensor Data (9) ---
    "HUM",                    # 16 SHT40, % RH
    "UV",                     # 17 LTR390
    "LUX",                    # 18 LTR390
    "CURRENT",                # 19 INA219, mA
    "POWER",                  # 20 INA219, mW
    "ROLL",                   # 21 BNO085, deg
    "PITCH",                  # 22 BNO085, deg
    "YAW",                    # 23 BNO085, deg
    "CAM_A_STATUS",           # 24 ESP32-CAM A (0/1)
]

FLOAT_FIELDS = {
    "TIME_STAMPING", "ALTITUDE", "PRESSURE", "TEMP", "VOLTAGE",
    "GNSS_LATITUDE", "GNSS_LONGITUDE", "GNSS_ALTITUDE", "GYRO_SPIN_RATE",
    "HUM", "UV", "CURRENT", "POWER", "ROLL", "PITCH", "YAW",
}

INT_FIELDS = {
    "PACKET_COUNT", "GNSS_SATS", "FLIGHT_SOFTWARE_STATE",
    "LUX", "CAM_A_STATUS",
}

# ACCELEROMETER_DATA and GNSS_TIME are intentionally left as plain strings
# (ACCELEROMETER_DATA is unpacked separately by add_legacy_aliases()).

FIELD_ALIASES = {
    "MISSION_TIME":  "TIME_STAMPING",
    "STATE":         "FLIGHT_SOFTWARE_STATE",
    "FLIGHT_STATE":  "FLIGHT_SOFTWARE_STATE",
    "TEMPERATURE":   "TEMP",
    "GPS_TIME":      "GNSS_TIME",
    "GPS_LATITUDE":  "GNSS_LATITUDE",
    "GPS_LONGITUDE": "GNSS_LONGITUDE",
    "GPS_ALTITUDE":  "GNSS_ALTITUDE",
    "GPS_SATS":      "GNSS_SATS",
    "I":             "CURRENT",
    "P":             "POWER",
    "CAM_A":         "CAM_A_STATUS",
}

FLIGHT_STATES = {
    0: "BOOT",
    1: "TEST_MODE",
    2: "LAUNCH_PAD",
    3: "ASCENT",
    4: "ROCKET_DEPLOY",
    5: "DESCENT",
    6: "AEROBRAKE_RELEASE",
    7: "IMPACT",
}