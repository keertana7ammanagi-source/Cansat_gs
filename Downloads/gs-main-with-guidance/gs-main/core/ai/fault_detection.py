"""
Mission Health & Fault Detection
Monitors packet loss, GPS lock, sensor ranges, battery health.
"""
class FaultDetector:
    def __init__(self):
        self.packet_loss_rate = 0.0
        self.sensor_faults = []
        self.consecutive_timeouts = 0
        self.last_packet_time = None

    def update(self, packet, packet_loss_rate):
        self.packet_loss_rate = packet_loss_rate
        faults = []

        # GPS lock
        sats = packet.get("GNSS_SATS", 0)
        if sats < 4:
            faults.append("GPS weak (<4 satellites)")

        # Sensor out-of-range
        alt = packet.get("ALTITUDE", 0)
        if alt < 0 or alt > 2000:
            faults.append("Altitude out of range")
        temp = packet.get("TEMP", 0)
        if temp < -10 or temp > 50:
            faults.append("Temperature out of range")
        voltage = packet.get("VOLTAGE", 0)
        if voltage < 5.0:
            faults.append("Battery critically low")

        if packet_loss_rate > 20:
            faults.append(f"High packet loss: {packet_loss_rate:.1f}%")

        self.sensor_faults = faults
        return {
            "faults": faults,
            "packet_loss_rate": packet_loss_rate,
            "status": "OK" if not faults else "ALERT",
        }