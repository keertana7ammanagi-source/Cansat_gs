/*
  FLIGHT SIDE — LilyGO TTGO T3 LoRa32 V1.6.1
  Sends a 28-field telemetry packet over LoRa once per second.
  Packet order matches the competition's mandatory order (fields 1-15)
  with optional extras appended after STATE.
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

// Only allow glide commands during SECONDARY_DEPLOY (flightState == 6),
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

// ---- Fake sensor data (replace with real reads) ----
float readAltitude()      { return 700.0 + random(-50, 50)/10.0; }
float readPressure()      { return 940.0 + random(-20, 20)/10.0; }
float readTemperature()   { return 24.0 + random(-10, 10)/10.0; }
float readVoltage()       { return 7.6 + random(-5, 5)/100.0; }
float readHumidity()      { return 45.0 + random(-5, 5); }
float readUV()            { return 3.0 + random(-1, 1); }
float readLight()         { return 200.0 + random(-50, 50); }
float readRotorRPM()      { return 2150.0 + random(-100, 100); }
float readAccelX()        { return 0.12 + random(-5, 5)/100.0; }
float readAccelY()        { return 0.08 + random(-5, 5)/100.0; }
float readAccelZ()        { return 9.81 + random(-5, 5)/100.0; }
float readGyroR()         { return 12.4 + random(-2, 2)/10.0; }
float readGyroP()         { return 8.7 + random(-2, 2)/10.0; }
float readGyroY()         { return 3.2 + random(-2, 2)/10.0; }
float readMagR()          { return 0.18 + random(-2, 2)/100.0; }
float readMagP()          { return 0.05 + random(-2, 2)/100.0; }
float readMagY()          { return 0.41 + random(-2, 2)/100.0; }
float readGPSLat()        { return 28.6129 + random(-5, 5)/100000.0; }
float readGPSLon()        { return 77.2295 + random(-5, 5)/100000.0; }
float readGPSAlt()        { return 700.0 + random(-10, 10); }
int   readGPSSats()       { return 9 + random(-2, 2); }
const char* readCmdEcho() { return "OK"; }

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
    // Calibrate sensors
    Serial.println("Calibration command received.");
  } else if (cmd == "HOVER" || cmd == "GLIDE_LEFT" || cmd == "GLIDE_RIGHT") {
    // Precision-landing guidance commands from the Ground Station's
    // LandingController. Only acted on during SECONDARY_DEPLOY --
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

  // ---- Read all sensor values ----
  float alt      = readAltitude();
  float press    = readPressure();
  float temp     = readTemperature();
  float volt     = readVoltage();
  float hum      = readHumidity();
  float uv       = readUV();
  float light    = readLight();
  float rotor    = readRotorRPM();
  float ax       = readAccelX();
  float ay       = readAccelY();
  float az       = readAccelZ();
  float gr       = readGyroR();
  float gp       = readGyroP();
  float gy       = readGyroY();
  float mag_r    = readMagR();
  float mag_p    = readMagP();
  float mag_y    = readMagY();
  float lat      = readGPSLat();
  float lon      = readGPSLon();
  float gpsAlt   = readGPSAlt();
  int   sats     = readGPSSats();
  const char* cmdEcho = readCmdEcho();

  uint32_t elapsed = (millis() - missionStartMillis) / 1000;
  char timeStr[9];
  sprintf(timeStr, "%02lu:%02lu:%02lu", elapsed/3600, (elapsed/60)%60, elapsed%60);

  // ---- Build 28-field packet in EXACT competition order ----
  char packet[350];
  snprintf(packet, sizeof(packet),
    "%s,%s,%lu,%.1f,%.1f,%.1f,%.2f,%s,%.4f,%.4f,%.1f,%d,"
    "%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%d,"
    "%.1f,%.1f,%.1f,%.0f,%.2f,%.2f,%.2f,%d,%s",
    // mandatory 1-15
    TEAM_ID, timeStr, packetCount, alt, press, temp, volt,
    timeStr, lat, lon, gpsAlt, sats,
    ax, ay, az,      // ACCEL_R, ACCEL_P, ACCEL_Y
    gr, gp, gy,      // GYRO_R, GYRO_P, GYRO_Y
    flightState,     // FLIGHT_STATE (mandatory)
    // optional 16-28
    hum, uv, light, rotor,
    mag_r, mag_p, mag_y,
    1,               // MODE (example)
    cmdEcho
  );

  LoRa.beginPacket();
  LoRa.print(packet);
  LoRa.endPacket();

  Serial.println(packet);
}