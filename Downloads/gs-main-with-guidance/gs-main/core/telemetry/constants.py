"""
CAN-7USAT Telemetry Field Definitions
32 flat fields — all comma-separated, no sub-fields.
"""

TEAM_ID = "2026-INSPACe-CAN-7USAT-036"

# ============================================================
# TELEMETRY COMMAND CONSTANTS (Rule 6.1.ii, 6.1.v, 6.1.vi)
# ============================================================
CMD_TELEMETRY_ON  = "CXON"      # Start telemetry transmission
CMD_TELEMETRY_OFF = "CXOFF"     # Stop telemetry transmission
CMD_CALIBRATE     = "CAL_ALL"   # Calibrate all sensors on pad

# ============================================================
# THE 32 FIELDS — ORDER MATTERS (matches ESP32 transmitter)
# ============================================================
FIELD_NAMES = [
    # --- Mandatory IN-SPACe (15) ---
    "TEAM_ID",                # 1
    "TIME_STAMPING",          # 2
    "PACKET_COUNT",           # 3
    "ALTITUDE",               # 4
    "PRESSURE",               # 5
    "TEMP",                   # 6  (from SHT40)
    "VOLTAGE",                # 7
    "GNSS_TIME",              # 8
    "GNSS_LATITUDE",          # 9
    "GNSS_LONGITUDE",         # 10
    "GNSS_ALTITUDE",          # 11
    "GNSS_SATS",              # 12
    "ACCELEROMETER_DATA",     # 13 (ax;ay;az)
    "GYRO_SPIN_RATE",         # 14 (Hall sensor, deg/s)
    "FLIGHT_SOFTWARE_STATE",  # 15 (0-7)

    # --- Precision Landing (8) ---
    "PRED_LAT",               # 16
    "PRED_LON",               # 17
    "CROSS_ERROR",            # 18
    "ERROR_NORTH",            # 19
    "ERROR_EAST",             # 20
    "PETAL_STATE",            # 21
    "GLIDE_CMD",              # 22
    "DWELL_MS",               # 23

    # --- Sensor Data (9) ---
    "HUM",                    # 24 SHT40
    "UV",                     # 25 LTR390
    "LUX",                    # 26 LTR390
    "CURRENT",                # 27 INA219
    "POWER",                  # 28 INA219
    "ROLL",                   # 29 BNO085
    "PITCH",                  # 30 BNO085
    "YAW",                    # 31 BNO085
    "CAM_A_STATUS",           # 32 ESP32-CAM A
]

FLOAT_FIELDS = {
    "TIME_STAMPING", "ALTITUDE", "PRESSURE", "TEMP", "VOLTAGE",
    "GNSS_LATITUDE", "GNSS_LONGITUDE", "GNSS_ALTITUDE", "GYRO_SPIN_RATE",
    "PRED_LAT", "PRED_LON", "CROSS_ERROR", "ERROR_NORTH", "ERROR_EAST",
    "HUM", "UV", "CURRENT", "POWER", "ROLL", "PITCH", "YAW",
}

INT_FIELDS = {
    "PACKET_COUNT", "GNSS_SATS", "FLIGHT_SOFTWARE_STATE",
    "LUX", "CAM_A_STATUS", "DWELL_MS",
}

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
    "ERR":           "CROSS_ERROR",
    "ERR_N":         "ERROR_NORTH",
    "ERR_E":         "ERROR_EAST",
    "PETAL":         "PETAL_STATE",
    "CMD":           "GLIDE_CMD",
    "DWELL":         "DWELL_MS",
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