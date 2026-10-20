/*
  FLIGHT SIDE — LilyGO TTGO T3 LoRa32 V1.6.1
  Sends the CAN-7USAT's actual 24-field telemetry packet over LoRa once
  per second, in this exact order:

  TEAM_ID,TIME_STAMPING,PACKET_COUNT,ALTITUDE,PRESSURE,TEMP,VOLTAGE,
  GNSS_TIME,GNSS_LATITUDE,GNSS_LONGITUDE,GNSS_ALTITUDE,GNSS_SATS,
  ACCELEROMETER_DATA,GYRO_SPIN_RATE,FLIGHT_SOFTWARE_STATE,
  HUM,UV,LUX,CURRENT,POWER,ROLL,PITCH,YAW,CAM_A_STATUS

  This MUST stay in sync with core/telemetry/constants.py FIELD_NAMES on
  the ground station. If you add/remove/reorder a field here, update
  FIELD_NAMES (and FLOAT_FIELDS/INT_FIELDS) there too, or every packet
  will be rejected by parse_packet() on a field-count mismatch.

  All read*() functions below are PLACEHOLDERS returning fake data for
  bench testing. Replace each with a real driver call before flight:
    - readAltitude/readPressure  -> BMP581
    - readTemperature/readHumidity -> SHT40
    - readUV/readLux             -> LTR390
    - readCurrent/readPower      -> INA219
    - readRoll/readPitch/readYaw -> BNO085
    - readGyroSpinRate           -> Hall sensor
    - readGPS*                   -> GNSS module (also replace the fake
                                     GNSS_TIME below with the receiver's
                                     own UTC time, NOT the mission clock)
    - readCamAStatus              -> ESP32-CAM A health/liveness pin
*/

#include <SPI.h>
#include <LoRa.h>
#include <Servo.h>

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

// TODO: flightState and missionStartMillis are RAM-only right now, so a
// processor reset loses both -- this violates rule 6.1.ix / 6.2.ii
// (mission clock & system state must survive a reset). Persist both to
// ESP32 NVS/Preferences on change and restore them in setup().

// ---- Fake sensor data (replace with real reads) ----
float readAltitude()      { return 700.0 + random(-50, 50) / 10.0; }        // m, relative to ground
float readPressure()      { return 94000.0 + random(-200, 200); }           // Pa
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
float readGyroSpinRate()  { return 12.4 + random(-20, 20) / 10.0; }         // deg/s, Hall sensor
float readGPSLat()        { return 28.6129 + random(-5, 5) / 100000.0; }    // deg
float readGPSLon()        { return 77.2295 + random(-5, 5) / 100000.0; }    // deg
float readGPSAlt()        { return 700.0 + random(-10, 10); }               // m
int   readGPSSats()       { return 9 + random(-2, 2); }
int   readCamAStatus()    { return 1; }                                     // 1 = camera A OK

// PLACEHOLDER: returns the mission-elapsed clock, NOT real GNSS time.
// Replace with the GNSS receiver's own UTC time once that module is wired
// in -- GNSS_TIME must come from the GPS fix, not the onboard clock.
String readGNSSTime(uint32_t elapsedSeconds) {
  char buf[9];
  sprintf(buf, "%02lu:%02lu:%02lu",
          elapsedSeconds / 3600, (elapsedSeconds / 60) % 60, elapsedSeconds % 60);
  return String(buf);
}

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
  if (cmd == "CXON") {
    telemetryEnabled = true;
    Serial.println("Telemetry STARTED.");
  } else if (cmd == "CXOFF") {
    telemetryEnabled = false;
    Serial.println("Telemetry STOPPED.");
  } else if (cmd == "CAL") {
    // Calibrate sensors: zero gyro, baro altitude, accelerometer (rule 6.1.x).
    Serial.println("Calibration command received.");
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
  float ax       = readAccelX();
  float ay       = readAccelY();
  float az       = readAccelZ();
  float gyroSpin = readGyroSpinRate();
  float hum      = readHumidity();
  float uv       = readUV();
  int   lux      = readLux();
  float current  = readCurrent();
  float power    = readPower();
  float roll     = readRoll();
  float pitch    = readPitch();
  float yaw      = readYaw();
  int   camA     = readCamAStatus();

  // ACCELEROMETER_DATA is one CSV field, packed "ax;ay;az" -- the ground
  // station splits it back out in core/telemetry/packet.py.
  char accelStr[40];
  snprintf(accelStr, sizeof(accelStr), "%.2f;%.2f;%.2f", ax, ay, az);

  // ---- Build the 24-field packet in EXACT competition/team order ----
  char packet[300];
  snprintf(packet, sizeof(packet),
    "%s,%lu,%lu,%.1f,%.1f,%.1f,%.2f,"
    "%s,%.4f,%.4f,%.1f,%d,"
    "%s,%.2f,%d,"
    "%.1f,%.1f,%d,%.2f,%.2f,%.1f,%.1f,%.1f,%d",
    TEAM_ID, elapsedSeconds, packetCount, alt, press, temp, volt,
    gnssTime.c_str(), lat, lon, gpsAlt, sats,
    accelStr, gyroSpin, flightState,
    hum, uv, lux, current, power, roll, pitch, yaw, camA
  );

  LoRa.beginPacket();
  LoRa.print(packet);
  LoRa.endPacket();

  Serial.println(packet);
}