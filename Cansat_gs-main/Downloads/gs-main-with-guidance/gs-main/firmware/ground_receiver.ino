/*
  GROUND SIDE — LilyGO TTGO T3 LoRa32 V1.6.1
  -------------------------------------------
  Acts as a dumb LoRa <-> USB Serial bridge for the laptop.
  - Anything received over LoRa gets printed to Serial (USB), one packet per line.
  - Anything typed/sent to it over Serial gets forwarded over LoRa
    (this is how the Python GS app sends START_TM / STOP_TM / CAL_ZERO).

  Must use the SAME LORA_FREQUENCY and setSyncWord() as the flight board.
*/

#include <SPI.h>
#include <LoRa.h>

#define LORA_SCK   5
#define LORA_MISO  19
#define LORA_MOSI  27
#define LORA_SS    18
#define LORA_RST   23
#define LORA_DIO0  26

#define LORA_FREQUENCY 915E6

void setup() {
  Serial.begin(115200);
  delay(300);

  SPI.begin(LORA_SCK, LORA_MISO, LORA_MOSI, LORA_SS);
  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);

  if (!LoRa.begin(LORA_FREQUENCY)) {
    Serial.println("LoRa init failed. Check wiring/frequency.");
    while (1) delay(1000);
  }

  LoRa.setSpreadingFactor(9);
  LoRa.setSignalBandwidth(125E3);
  LoRa.setCodingRate4(5);
  LoRa.setSyncWord(0x12); // must match flight board

  Serial.println("Ground receiver ready.");
}

void loop() {
  // LoRa -> Serial (telemetry coming down from CanSat)
  int packetSize = LoRa.parsePacket();
  if (packetSize) {
    String received = "";
    while (LoRa.available()) received += (char)LoRa.read();
    Serial.println(received);   // Python app reads this line
  }

  // Serial -> LoRa (commands going up from Python GS app)
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.length() > 0) {
      LoRa.beginPacket();
      LoRa.print(cmd);
      LoRa.endPacket();
    }
  }
}
