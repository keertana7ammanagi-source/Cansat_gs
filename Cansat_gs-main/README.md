# CAN-7USAT Ground Station

## Overview

The CAN-7USAT Ground Station is a Python-based application designed to receive, process, visualize, and manage telemetry data from a CanSat mission. The project follows a modular architecture to ensure scalability, maintainability, and ease of future development.

This repository contains the Ground Station software and supporting modules required for telemetry monitoring and mission operations.

---

## Features

- Real-time telemetry data handling
- Modular and scalable architecture
- Configuration management using YAML
- Sensor data processing
- Telemetry logging
- Simulation support
- Two operator tabs: live telemetry and offline analytics/reports
- 37-field live value cards and numeric plots, with a projected 3D attitude indicator
- Dark and outdoor high-contrast themes
- Background environmental, lapse-rate, and accelerometer stability analysis
- CSV logging to `Flight_2026-INSPACe-CAN-7USAT-036.csv` and PDF mission reports
- Extensible communication framework
- Organized project structure for maintainability

---

## Project Structure

```text
CAN-7USAT-GroundStation/
│
├── assets/             # Images and other static resources
├── config/             # Configuration files
├── core/               # Core application logic
├── logs/               # Runtime logs
├── simulation/         # Simulation modules
├── ui/                 # User interface
├── main.py             # Application entry point
├── requirements.txt    # Python dependencies
└── README.md
```

---

## Technology Stack

- Python 3.x
- PyYAML
- Matplotlib
- NumPy

*Additional libraries are listed in `requirements.txt`.*

---

## Installation

Clone the repository:

```bash
git clone https://github.com/meghanamurali10-crypto/gs.git
```

Navigate to the project directory:

```bash
cd gs
```

Install the required dependencies:

```bash
pip install -r requirements.txt
```

The ground station's live telemetry and background analysis do not require
scikit-learn. The parser accepts the current 37-field team schema and the
checked-in 24-field transmitter format; absent extension fields show as
unavailable. Update the flight transmitter and real sensor drivers before
expecting all 37 values over the radio.

Run the application:

```bash
python main.py
```

---

## Functionality

The Ground Station is designed to support the following operations:

- Receive telemetry packets from the CanSat
- Process incoming sensor data
- Display mission parameters
- Record telemetry for post-mission analysis
- Support simulation and testing
- Provide a foundation for future mission capabilities

The **LIVE TELEMETRY** tab contains the existing dashboards, command controls,
simulation tools, live graphs, and all-field view. The **AI ANALYTICS & REPORTS**
tab displays background analysis and generates the mission PDF on request.
The command button labeled **CALIBRATE** sends `CAL`, matching the current
flight firmware; the visible `CXON` and `CXOFF` buttons send those literal
commands.

## Firmware builds

The ground receiver and flight transmitter are separate firmware targets.
Build either from the repository root with PlatformIO:

```bash
pio run -e ttgo-lora32-v1
pio run -e ttgo-lora32-v1-flight
```

The receiver target is for the ground station's LoRa-to-USB bridge; the flight
target is for the CanSat transmitter and guidance servo.

---

## Future Enhancements

Planned improvements include:

- Advanced telemetry visualization
- Interactive mission dashboard
- Data export functionality
- Multi-device communication support
- Geographic map integration
- Mission replay capability
- Enhanced error handling
- Automated packet validation

---

## Contributing

Contributions are welcome. If you would like to improve the project:

1. Fork the repository.
2. Create a new feature branch.
3. Commit your changes.
4. Submit a Pull Request.

---

## License

This project is intended for educational and research purposes.

## Competition Operations Notes

The judge CSV is written in the repository root. In the Simulation Tools panel,
**Stream Pressure CSV over RF** sends the addressed `SIM_ENABLE`, `SIMP,<Pa>`
pressure samples at 1 Hz, and `SIM_DISABLE` when stopped. This requires a live
radio connection; the separate local synthetic simulator is used while the
radio is disconnected. `simulation/inject.py <virtual-port> <telemetry.csv>`
replays a 37-column CSV into one end of a virtual COM pair at 1 Hz; select its
paired endpoint in the GCS.

The selected point-to-point LoRa library does not provide XBee `NETID` or
`PANID` registers. Uplink commands therefore include a team-ID application
address (`NETID,<team-id>,<command>`), which the flight firmware checks before
acting. This does not configure a hardware NETID/PANID field.
