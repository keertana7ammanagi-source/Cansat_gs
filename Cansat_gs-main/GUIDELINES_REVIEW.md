# CAN-7USAT Guidelines Review

Reviewed against the supplied 2026 CAN-7USAT competition guideline PDF, the team's PDR mini PDF, the team's CDR PDF, and the current ground-station code.

## Competition requirements confirmed

The official guideline requires the ground station to:

- Display telemetry near real time in SI units and plot telemetry fields during flight (Ground Station 6.1.i; numbered requirement 30 in the CDR compliance list).
- Send an RF command to start telemetry before launch; the CanSat must remain quiet until commanded (6.1.ii, 6.1.v; numbered requirements 31 and 34).
- Send calibration commands for gyro, barometric altitude, and accelerometer while on the pad (6.1.vi; numbered requirement 35).
- Save sensor data to CSV (6.1.vii; numbered requirement 36).
- Acquire and transmit telemetry at 1 Hz or better, with the defined mandatory telemetry prefix and any team-defined optional data (Telemetry 6.3.i; numbered requirement 42).
- Preserve mission time and flight state through processor reset, and meet the portable ground-station, battery, and antenna requirements (6.1.iii-iv, 6.1.viii-xi; numbered requirements 32-40).

The mandatory telemetry prefix is 15 fields: TEAM ID, TIME STAMPING, PACKET COUNT, ALTITUDE, PRESSURE, TEMP, VOLTAGE, GNSS TIME, GNSS LATITUDE, GNSS LONGITUDE, GNSS ALTITUDE, GNSS SATS, ACCELEROMETER DATA, GYRO SPIN RATE, and FLIGHT SOFTWARE STATE. The guide permits optional data after this prefix; it does not prescribe a 37-field packet.

## Claims that need correction or qualification

- AI/ML is not a mandatory requirement. The PDR describes K-Means, Random Forest, sensor fusion, and rule-based health monitoring as ground-station innovations. The guideline's optional-objective section offers extra points for specified demonstrable innovations, but does not promise points specifically for AI. Describe AI as a proposed team innovation, not as a guaranteed scoring bonus.
- Rule 28 is the prohibition on XBee broadcast mode. Rule 30 covers real-time SI display and plotting. The 1 Hz telemetry requirement is Telemetry 6.3.i (also numbered 42 in the compliance list); CSV is Rule 36; calibration is Rule 35.
- The rules require RF telemetry on/off and calibration capabilities, but do not mandate the literal strings `CXON`, `CXOFF`, or `CAL`. `SIM` is not listed as a required flight command. The guideline does ask the PDR to describe the simulation-mode strategy and asks the CDR to discuss simulation/test plans; that is not the same as requiring a specific RF command.
- Position data and portable recovery operations are required, but an offline map is not specified as a competition requirement.
- The pasted 37-field list does not match the official field names/order or this repository's flight transmitter. The checked-in transmitter sends 24 fields: the 15-field mandatory prefix plus nine optional fields, matching the parser and logger. The guide allows optional fields, but does not require the pasted 37-field schema.
- The suggested pressure threshold `PRESS < 950` is inconsistent with the guideline's pressure unit of pascals (typical atmospheric readings are around 100,000 Pa). The lapse-rate estimate also needs direction specified: a point 100 m lower during descent would be roughly 0.65 C warmer under the standard-atmosphere approximation, not colder. GPS ground motion alone is not a wind measurement; without a motion model it should be called ground drift/velocity.
- The guide has conflicting antenna wording: Ground Station 6.1.xi says antenna mounted on a tripod, while numbered requirement 39 says handheld antenna. Confirm the accepted configuration with the organizers.

## Flight-readiness gaps in the supplied firmware

- All sensor readers in flight_transmitter.ino are explicitly fake bench-test values. The current 1 Hz packet cadence and schema are demonstrated, but the software is not ready to provide real sensor telemetry until those functions are replaced with hardware drivers.
- The CAL command currently prints an acknowledgement only; it does not calibrate or zero sensors. Rule 35 requires the calibration behavior, so this remains an implementation gap.
- Mission time and flight state are RAM-only and reset on reboot. The firmware itself marks this as a reset-compliance TODO; the guide requires preserving both.
- The PDR/CDR describe LoRa WAN and radio network identifiers, while the checked-in transmitter/receiver use point-to-point LoRa and a sync word. Confirm this radio configuration with the approved competition interface before flight.

## Repository changes made

- Grouped the existing dashboards into the requested two top-level tabs and added a 37-field live value grid, numeric plots, a projected attitude cube, simulation-mode toggle, and dark/outdoor theme toggle.
- Added a background worker for rule-based environmental classification, the standard lapse-rate temperature estimate, and rolling accelerometer-magnitude variance. These are lightweight insights, not trained ML models or measured wind predictions.
- The packet parser accepts both the team's requested 37-field schema and the current 24-field wire packet. The CSV logger normalizes to 37 columns and preserves the pre-migration CSV as a `.legacy.bak` copy; fields not transmitted remain blank.
- Removed unsupported placeholder readings from the live telemetry and power views; unavailable receiver, rail, battery capacity, and subsystem measurements display as unavailable.
- Kept report generation in the analytics/reports tab. Removed stale `temp_map.html` and `.pytest_cache` artifacts.
- Kept the recovery dashboard's offline GNSS plot and serial-write error handling described above.
- The judged CSV is now created at the repository root as `Flight_2026-INSPACe-CAN-7USAT-036.csv`; live display converts pressure to hPa and current/power to A/W while preserving wire units in the CSV.
- Added a separate RF pressure-profile streamer: it sends the team-addressed `SIM_ENABLE`, then one `SIMP,<pressure_pa>` command per second, and sends `SIM_DISABLE` when stopped. Local synthetic simulation remains isolated from a connected serial radio.
- RF uplink commands now carry the team ID in an application-level `NETID,<team>,<command>` envelope. This is not a hardware NETID/PANID setting; point-to-point LoRa has no such XBee field.
- The flight firmware now accepts those addressed commands, gates `CAL` to launch-pad state, captures pad pressure/attitude/acceleration offsets, and uses incoming simulated pressure to calculate relative barometric altitude. These calibration reads still use placeholder sensor functions until hardware drivers are installed.

## Remaining integration item

Before flight, replace the fake sensor readers, persist mission time/state, and confirm the radio interface and antenna configuration with the organizers. The existing point-to-point LoRa firmware cannot set a native XBee NETID/PANID; the current command address is application-level only. Verify that this radio approach is accepted before flight. Laptop battery endurance and antenna coverage/range require physical testing.

The current firmware still transmits 24 fields, so the new extension fields will be blank until the transmitter is updated to emit the matching 37-field order with real sensor values. The firmware's current `CAL` handler also only acknowledges the command.

No tests were run as part of this change.
