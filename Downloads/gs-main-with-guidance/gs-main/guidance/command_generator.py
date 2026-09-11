"""
guidance/command_generator.py

Turns a LandingController decision into a structured, checksummed
command string to hand to the LoRa transmitter, and tracks sequence
numbers / acknowledgements.

Packet format (simple, human-debuggable over serial/LoRa terminal):

    CMD,<seq>,<command>,<checksum>

checksum = 8-bit XOR of all preceding bytes (seq + command), printed
as 2 hex digits. This is not cryptographic -- it's just enough to
reject a corrupted-in-transit packet, matching the "don't accept
commands blindly" requirement.
"""

import time


def _checksum(payload: str) -> str:
    csum = 0
    for b in payload.encode("ascii"):
        csum ^= b
    return f"{csum:02X}"


class CommandGenerator:
    def __init__(self):
        self.seq = 0
        # seq -> (command, sent_time, acked)
        self._pending = {}

    def build(self, command):
        """
        Build the next command packet string and register it as pending
        (awaiting ACK). Returns the packet string, e.g.
        "CMD,1043,GLIDE_RIGHT,3F".
        """
        self.seq += 1
        payload = f"{self.seq},{command}"
        packet = f"CMD,{payload},{_checksum(payload)}"

        self._pending[self.seq] = {
            "command": command,
            "sent_time": time.monotonic(),
            "acked": False,
        }
        return packet

    def on_ack(self, ack_line):
        """
        Feed a received line such as "ACK,1043,GLIDE_RIGHT" and mark
        that sequence number acknowledged. Returns True if it matched a
        pending command, False otherwise (unexpected/duplicate ACK).
        """
        parts = ack_line.strip().split(",")
        if len(parts) < 2 or parts[0] != "ACK":
            return False
        try:
            seq = int(parts[1])
        except ValueError:
            return False

        entry = self._pending.get(seq)
        if entry is None:
            return False

        entry["acked"] = True
        return True

    def unacked_older_than(self, seconds):
        """
        Return sequence numbers still unacknowledged after `seconds`
        have elapsed since they were sent. Useful for a link-health
        indicator in the guidance dashboard.
        """
        now = time.monotonic()
        stale = []
        for seq, entry in self._pending.items():
            if not entry["acked"] and (now - entry["sent_time"]) > seconds:
                stale.append(seq)
        return stale

    def prune(self, keep_last=50):
        """Drop old pending entries so this dict doesn't grow forever."""
        if len(self._pending) <= keep_last:
            return
        for seq in sorted(self._pending.keys())[: len(self._pending) - keep_last]:
            del self._pending[seq]


def parse_command_packet(line):
    """
    Parse a "CMD,<seq>,<command>,<checksum>" line as the CanSat firmware
    would. Returns (seq, command) if valid, or None if malformed or the
    checksum doesn't match.

    This mirrors the validation the ESP32 side should perform -- kept
    here too so the Ground Station can sanity-check its own outgoing
    packets in tests, and so the parsing logic is specified once even
    though the real check runs in firmware C++.
    """
    parts = line.strip().split(",")
    if len(parts) != 4 or parts[0] != "CMD":
        return None

    seq_str, command, checksum = parts[1], parts[2], parts[3]
    payload = f"{seq_str},{command}"
    if _checksum(payload) != checksum.upper():
        return None

    try:
        seq = int(seq_str)
    except ValueError:
        return None

    if command not in ("HOVER", "GLIDE_LEFT", "GLIDE_RIGHT"):
        return None

    return seq, command
