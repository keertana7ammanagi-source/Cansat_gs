"""
Packet sequencing – loss detection, duplicate detection.
"""
from typing import Optional, Dict
from .packet import TelemetryPacket


class PacketSequencer:
    def __init__(self):
        self.last_packet_num: Optional[int] = None
        self.total_received = 0
        self.total_missed = 0

    def process(self, packet: TelemetryPacket) -> Dict:
        result = {"missed": 0, "duplicate": False, "out_of_order": False}
        pkt_num = packet.get("PACKET_COUNT")
        if pkt_num is None:
            return result

        self.total_received += 1

        if self.last_packet_num is not None:
            if pkt_num == self.last_packet_num:
                result["duplicate"] = True
            elif pkt_num < self.last_packet_num:
                result["out_of_order"] = True
            elif pkt_num > self.last_packet_num + 1:
                missed = pkt_num - self.last_packet_num - 1
                result["missed"] = missed
                self.total_missed += missed

        self.last_packet_num = pkt_num
        return result

    def loss_rate_percent(self) -> float:
        total = self.total_received + self.total_missed
        return 0.0 if total == 0 else 100.0 * self.total_missed / total