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

