/*
  FLIGHT SIDE — LilyGO TTGO T3 LoRa32 V1.6.1
  Sends the requested 37-field telemetry schema over LoRa once per second.
  The exact field order is documented beside sendTelemetryPacket() and in
  core/telemetry/constants.py FIELD_NAMES. Do not add camera-status fields.

  All read*() functions below are PLACEHOLDERS returning fake data for
  bench testing. Replace each with a real driver call before flight:
    - readAltitude/readPressure  -> BMP581
    - readTemperature/readHumidity -> SHT40
    - readUV/readLux             -> LTR390
    - readCurrent/readPower      -> INA219
    - readRoll/readPitch/readYaw -> BNO085
    - HALL_RPM                   -> provide a real RPM reading before flight
    - readGPS*                   -> GNSS module (also replace the fake
                                     GNSS_TIME below with the receiver's
                                     own UTC time, NOT the mission clock)
*/

#include <Arduino.h>
#include <LoRa.h>
#include <ESP32Servo.h>

// ---- LoRa pins ----
#define LORA_SCK   5
#define LORA_MISO  19
#define LORA_MOSI  27
#define LORA_SS    18
#define LORA_RST   23
#define LORA_DIO0  26

#define LORA_FREQUENCY 915E6   // change to 868E6 if required

// ---- Guidance servo (precision landing) ----
// Independent of the telemetry packet above. Only acted on if/when the
// ground station's LandingController sends HOVER/GLIDE_LEFT/GLIDE_RIGHT;
// the current telemetry format carries no guidance fields.
// PLACEHOLDER values -- do NOT fly with these. Determine the real
// neutral/left/right angles and safe travel limits from your cam/rod
// calibration table (see guidance/README.md) before connecting this to
// the actual mechanism.
#define SERVO2_PIN     13
#define CAM_POS_HOVER  90
#define CAM_POS_LEFT   60
#define CAM_POS_RIGHT  120
#define SERVO_MIN      60
#define SERVO_MAX      120

Servo servo2;

// Only allow glide commands during AEROBRAKE_RELEASE (flightState == 6),
// matching FLIGHT_STATES in core/telemetry/constants.py and the same
// gate the Ground Station's LandingController uses. Any other state
// forces HOVER even if a glide command is somehow received.
#define GUIDANCE_ALLOWED_STATE 6

// Failsafe: if the last ACCEPTED glide command is older than this and
// we're not back to HOVER, force HOVER. Protects against a lost link
// leaving the CanSat mid-glide indefinitely.
#define GUIDANCE_TIMEOUT_MS 5000

unsigned long lastGuidanceCommandMillis = 0;
bool guidanceEverActive = false;

const char* TEAM_ID = "2026-INSPACe-CAN-7USAT-036";

uint32_t packetCount = 0;
uint32_t missionStartMillis = 0;
bool telemetryEnabled = false;
int flightState = 2;  // LAUNCH_PAD
// LoRa point-to-point has no native NETID/PANID. Commands are addressed at
// the application layer with this team ID, and the radio sync word remains
// the physical link discriminator.
const char* RADIO_NETWORK_ID = "2026-INSPACe-CAN-7USAT-036";
bool simulationMode = false;
bool simulatedPressureValid = false;
float simulatedPressurePa = 101325.0;
float padPressurePa = 101325.0;
bool padCalibrationValid = false;
float accelZeroX = 0.0, accelZeroY = 0.0, accelZeroZ = 0.0;
float rollZero = 0.0, pitchZero = 0.0, yawZero = 0.0;

// TODO: flightState and missionStartMillis are RAM-only right now, so a
// processor reset loses both -- this violates rule 6.1.ix / 6.2.ii
// (mission clock & system state must survive a reset). Persist both to
// ESP32 NVS/Preferences on change and restore them in setup().

// ---- Fake sensor data (replace with real reads) ----
float readPressure()      {
  if (simulationMode && simulatedPressureValid) return simulatedPressurePa;
  return 94000.0 + random(-200, 200);
} // Pa; replace fallback with the BMP581 driver before flight
float readAltitude()      {
  if (((simulationMode && simulatedPressureValid) || padCalibrationValid) && padPressurePa > 0.0) {
    float ratio = readPressure() / padPressurePa;
    return max(0.0f, 44330.0f * (1.0f - pow(ratio, 0.19029495f)));
  }
  return 700.0 + random(-50, 50) / 10.0;
} // m; simulated pressure is converted relative to pad pressure
float readTemperature()   { return 24.0 + random(-10, 10) / 10.0; }         // deg C
float readVoltage()       { return 7.6 + random(-5, 5) / 100.0; }           // V
float readHumidity()      { return 45.0 + random(-5, 5); }                  // % RH
float readUV()            { return 3.0 + random(-10, 10) / 10.0; }          // UV index
int   readLux()           { return 200 + random(-50, 50); }                 // lux
float readCurrent()       { return 320.0 + random(-20, 20); }               // mA
float readPower()         { return 2400.0 + random(-100, 100); }            // mW
float readRoll()          { return 1.5 + random(-20, 20) / 10.0; }          // deg
float readPitch()         { return -0.8 + random(-20, 20) / 10.0; }         // deg
float readYaw()           { return 45.0 + random(-30, 30) / 10.0; }         // deg
float readAccelX()        { return 0.12 + random(-5, 5) / 100.0; }          // m/s^2
float readAccelY()        { return 0.08 + random(-5, 5) / 100.0; }          // m/s^2
float readAccelZ()        { return 9.81 + random(-5, 5) / 100.0; }          // m/s^2
float readGPSLat()        { return 28.6129 + random(-5, 5) / 100000.0; }    // deg
float readGPSLon()        { return 77.2295 + random(-5, 5) / 100000.0; }    // deg
float readGPSAlt()        { return 700.0 + random(-10, 10); }               // m
int   readGPSSats()       { return 9 + random(-2, 2); }

// PLACEHOLDER: returns the mission-elapsed clock, NOT real GNSS time.
// Replace with the GNSS receiver's own UTC time once that module is wired
// in -- GNSS_TIME must come from the GPS fix, not the onboard clock.
String readGNSSTime(uint32_t elapsedSeconds) {
  char buf[9];
  sprintf(buf, "%02lu:%02lu:%02lu",
          elapsedSeconds / 3600, (elapsedSeconds / 60) % 60, elapsedSeconds % 60);
  return String(buf);
}

void handleCommand(String cmd);
void sendTelemetryPacket();
void guidanceFailsafeCheck();

void setup() {
  Serial.begin(115200);
  delay(300);

  SPI.begin(LORA_SCK, LORA_MISO, LORA_MOSI, LORA_SS);
  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);

  if (!LoRa.begin(LORA_FREQUENCY)) {
    Serial.println("LoRa init failed.");
    while (1) delay(1000);
  }

  LoRa.setSpreadingFactor(9);
  LoRa.setSignalBandwidth(125E3);
  LoRa.setCodingRate4(5);
  LoRa.setSyncWord(0x12);   // unique per team

  Serial.println("Flight transmitter ready.");
  missionStartMillis = millis();
  flightState = 2;  // LAUNCH_PAD

  servo2.attach(SERVO2_PIN);
  servo2.write(CAM_POS_HOVER);
}

void loop() {
  // Listen for ground commands
  int packetSize = LoRa.parsePacket();
  if (packetSize) {
    String cmd = "";
    while (LoRa.available()) cmd += (char)LoRa.read();
    handleCommand(cmd);
  }

  static uint32_t lastSend = 0;
  if (telemetryEnabled && millis() - lastSend >= 1000) {
    lastSend = millis();
    sendTelemetryPacket();
  }

  guidanceFailsafeCheck();
}

int safeServoPosition(int requested) {
  if (requested < SERVO_MIN) return SERVO_MIN;
  if (requested > SERVO_MAX) return SERVO_MAX;
  return requested;
}

void executeHover() {
  servo2.write(safeServoPosition(CAM_POS_HOVER));
}

void executeGlideLeft() {
  servo2.write(safeServoPosition(CAM_POS_LEFT));
}

void executeGlideRight() {
  servo2.write(safeServoPosition(CAM_POS_RIGHT));
}

// If we've ever accepted a glide command and haven't heard a valid
// guidance command in GUIDANCE_TIMEOUT_MS, force HOVER. Protects
// against a lost LoRa link leaving the rods extended.
void guidanceFailsafeCheck() {
  if (!guidanceEverActive) return;
  if (millis() - lastGuidanceCommandMillis > GUIDANCE_TIMEOUT_MS) {
    executeHover();
    guidanceEverActive = false;
    Serial.println("Guidance failsafe: no command received, forcing HOVER.");
  }
}

void handleCommand(String cmd) {
  cmd.trim();
  // Require an explicit address on all uplink commands. This is an
  // application-level NETID because the selected point-to-point LoRa
  // library does not expose XBee NETID/PANID configuration.
  if (!cmd.startsWith("NETID,")) return;
  int idEnd = cmd.indexOf(',', 6);
  if (idEnd < 0 || cmd.substring(6, idEnd) != RADIO_NETWORK_ID) return;
  cmd = cmd.substring(idEnd + 1);
  cmd.trim();

  if (cmd == "CXON") {
    telemetryEnabled = true;
    Serial.println("Telemetry STARTED.");
  } else if (cmd == "CXOFF") {
    telemetryEnabled = false;
    Serial.println("Telemetry STOPPED.");
  } else if (cmd == "CAL") {
    // Capture the pad reference for barometric altitude and zero the
    // accelerometer/gyro outputs. These reads must be replaced with real
    // sensor-driver calls before flight (see placeholder declarations).
    if (flightState != 2) {
      Serial.println("Calibration rejected: payload is not on the launch pad.");
      return;
    }
    padPressurePa = readPressure();
    padCalibrationValid = padPressurePa > 0.0;
    accelZeroX = readAccelX(); accelZeroY = readAccelY(); accelZeroZ = readAccelZ();
    rollZero = readRoll(); pitchZero = readPitch(); yawZero = readYaw();
    Serial.println("Pad calibration reference captured.");
  } else if (cmd == "SIM_ENABLE") {
    simulationMode = true;
    simulatedPressureValid = false;
    if (!padCalibrationValid) padPressurePa = 101325.0;
    Serial.println("Pressure simulation enabled.");
  } else if (cmd == "SIM_DISABLE") {
    simulationMode = false;
    simulatedPressureValid = false;
    Serial.println("Pressure simulation disabled.");
  } else if (cmd.startsWith("SIMP,")) {
    float pressure = cmd.substring(5).toFloat();
    if (simulationMode && pressure > 0.0) {
      simulatedPressurePa = pressure;
      simulatedPressureValid = true;
    }
  } else if (cmd == "HOVER" || cmd == "GLIDE_LEFT" || cmd == "GLIDE_RIGHT") {
    // Precision-landing guidance commands from the Ground Station's
    // LandingController. Only acted on during AEROBRAKE_RELEASE --
    // otherwise silently forced to HOVER, same gate the GS applies on
    // its side, so an out-of-state command can never move the servo.
    String executed = cmd;
    if (cmd != "HOVER" && flightState != GUIDANCE_ALLOWED_STATE) {
      executed = "HOVER";
    }

    if (executed == "HOVER") {
      executeHover();
    } else if (executed == "GLIDE_LEFT") {
      executeGlideLeft();
    } else if (executed == "GLIDE_RIGHT") {
      executeGlideRight();
    }

    lastGuidanceCommandMillis = millis();
    if (executed != "HOVER") {
      guidanceEverActive = true;
    }

    Serial.print("Guidance command: ");
    Serial.print(cmd);
    if (executed != cmd) {
      Serial.print(" -> overridden to ");
      Serial.print(executed);
      Serial.print(" (flight state ");
      Serial.print(flightState);
      Serial.print(" != ");
      Serial.print(GUIDANCE_ALLOWED_STATE);
      Serial.print(")");
    }
    Serial.println();
  }
}

void sendTelemetryPacket() {
  packetCount++;

  uint32_t elapsedSeconds = (millis() - missionStartMillis) / 1000;

  // ---- Read all sensor values ----
  float alt      = readAltitude();
  float press    = readPressure();
  float temp     = readTemperature();
  float volt     = readVoltage();
  String gnssTime = readGNSSTime(elapsedSeconds);
  float lat      = readGPSLat();
  float lon      = readGPSLon();
  float gpsAlt   = readGPSAlt();
  int   sats     = readGPSSats();
  float ax       = readAccelX() - accelZeroX;
  float ay       = readAccelY() - accelZeroY;
  float az       = readAccelZ() - accelZeroZ;
  float hum      = readHumidity();
  float uv       = readUV();
  int   lux      = readLux();
  float current  = readCurrent();
  float power    = readPower();
  float roll     = readRoll() - rollZero;
  float pitch    = readPitch() - pitchZero;
  float yaw      = readYaw() - yawZero;

  // 37-field CSV schema. Fields for sensors not currently implemented by
  // this firmware are deliberately empty (not fabricated). The receiver's
  // parser preserves empty fields as None. Replace placeholders with real
  // sensor-driver values before flight.
  static float previousAltitude = 0.0f;
  static uint32_t previousAltitudeMillis = 0;
  float verticalSpeed = 0.0f;
  uint32_t nowMillis = millis();
  if (previousAltitudeMillis != 0 && nowMillis > previousAltitudeMillis) {
    verticalSpeed = (alt - previousAltitude) * 1000.0f /
                    (float)(nowMillis - previousAltitudeMillis);
  }
  previousAltitude = alt;
  previousAltitudeMillis = nowMillis;

  // Keep the exact field order in core/telemetry/constants.py:
  // TEAM_ID,TIMESTAMP,PACKET_COUNT,ALTITUDE,PRESSURE,TEMP,VOLTAGE,
  // GNSS_TIME,GNSS_LATITUDE,GNSS_LONGITUDE,GNSS_ALTITUDE,GNSS_SATS,
  // ACCEL_X,ACCEL_Y,ACCEL_Z,GYRO_X,GYRO_Y,GYRO_Z,MAG_X,MAG_Y,MAG_Z,
  // ROLL,PITCH,YAW,LIGHT_LUX,UV_INDEX,HALL_RPM,FLIGHT_SOFTWARE_STATE,
  // REL_ALTITUDE,VERTICAL_SPEED,GNSS_GROUND_SPEED,GNSS_COURSE,
  // GNSS_HDOP,GNSS_FIX,HUMIDITY,CURRENT,POWER
  char packet[255];
  snprintf(packet, sizeof(packet),
    "%s,%lu,%lu,%.1f,%.0f,%.1f,%.2f,"
    "%s,%.4f,%.4f,%.1f,%d,"
    "%.2f,%.2f,%.2f,,,,,,,%.1f,%.1f,%.1f,"
    "%d,%.1f,,%d,%.1f,%.2f,,,,,%.1f,%.2f,%.2f",
    TEAM_ID, elapsedSeconds, packetCount, alt, press, temp, volt,
    gnssTime.c_str(), lat, lon, gpsAlt, sats,
    ax, ay, az,
    roll, pitch, yaw,
    lux, uv, flightState,
    alt, verticalSpeed, hum, current, power
  );

  LoRa.beginPacket();
  LoRa.print(packet);
  LoRa.endPacket();

  Serial.println(packet);
}
