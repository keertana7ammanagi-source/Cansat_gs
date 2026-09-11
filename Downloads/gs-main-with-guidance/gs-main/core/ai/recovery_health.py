"""
Recovery Health Monitor
Checks rotor RPM, voltage, altitude to confirm recovery system health.
"""
class RecoveryHealthMonitor:
    def __init__(self):
        self.rpm_history = []
        self.voltage_history = []
        self.altitude_history = []
        self.status = "Unknown"

    def update(self, packet):
        rpm = packet.get("ROTOR_RPM", 0)
        voltage = packet.get("VOLTAGE", 0)
        alt = packet.get("ALTITUDE", 0)
        state = packet.get("FLIGHT_STATE", "")

        self.rpm_history.append(rpm)
        self.voltage_history.append(voltage)
        self.altitude_history.append(alt)
        if len(self.rpm_history) > 20:
            self.rpm_history.pop(0)
            self.voltage_history.pop(0)
            self.altitude_history.pop(0)

        issues = []
        if len(self.rpm_history) >= 5:
            avg_rpm = sum(self.rpm_history[-5:]) / 5
            if state in ("DESCENT", "SECONDARY_DEPLOY") and avg_rpm < 1000:
                issues.append("RPM too low during descent")
            if voltage < 7.0:
                issues.append("Low battery voltage")
        if alt < 100 and state not in ("IMPACT", "RECOVERY"):
            issues.append("Altitude low but not landed")

        self.status = "OK" if not issues else "WARNING: " + "; ".join(issues)
        return {
            "status": self.status,
            "avg_rpm": sum(self.rpm_history[-5:]) / 5 if len(self.rpm_history) >= 5 else 0,
            "voltage": voltage,
        }