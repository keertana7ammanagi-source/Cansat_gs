import math
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from guidance.coordinate_utils import (
    gps_to_local,
    distance_m,
    bearing_deg,
    cross_track_error,
)
from guidance.landing_controller import (
    LandingController,
    CMD_HOVER,
    CMD_GLIDE_LEFT,
    CMD_GLIDE_RIGHT,
)
from guidance.command_generator import CommandGenerator, parse_command_packet


class TestCoordinateUtils(unittest.TestCase):
    def test_gps_to_local_zero_at_reference(self):
        east, north = gps_to_local(13.0, 77.0, 13.0, 77.0)
        self.assertAlmostEqual(east, 0.0, places=6)
        self.assertAlmostEqual(north, 0.0, places=6)

    def test_distance_pythagoras(self):
        self.assertAlmostEqual(distance_m((0, 0), (3, 4)), 5.0)

    def test_bearing_north(self):
        self.assertAlmostEqual(bearing_deg((0, 0), (0, 10)), 0.0)

    def test_bearing_east(self):
        self.assertAlmostEqual(bearing_deg((0, 0), (10, 0)), 90.0)

    def test_cross_track_on_line(self):
        error, sign = cross_track_error((0, 0), (0, 100), (0, 50))
        self.assertAlmostEqual(error, 0.0)
        self.assertEqual(sign, 0.0)

    def test_cross_track_right_of_line(self):
        # Path goes due north; a point to the east is to the "right".
        error, sign = cross_track_error((0, 0), (0, 100), (20, 50))
        self.assertAlmostEqual(error, 20.0)
        self.assertGreater(sign, 0)

    def test_cross_track_left_of_line(self):
        error, sign = cross_track_error((0, 0), (0, 100), (-20, 50))
        self.assertAlmostEqual(error, 20.0)
        self.assertLess(sign, 0)


class TestLandingController(unittest.TestCase):
    def make_controller(self, **kwargs):
        c = LandingController(**kwargs)
        c.set_reference(13.0, 77.0)
        c.set_origin(13.0, 77.0)          # local (0, 0)
        # Target 100 m due north of origin.
        # 100 m north == d_lat = 100 / 111320
        target_lat = 13.0 + 100.0 / 111320.0
        c.set_target(target_lat, 77.0)
        c.arm()
        return c

    def test_not_armed_returns_hover(self):
        c = LandingController()
        result = c.update(13.0, 77.0, 150.0, "6", now_s=0.0)
        self.assertEqual(result["command"], CMD_HOVER)
        self.assertFalse(result["transmit"])

    def test_wrong_flight_state_hovers(self):
        c = self.make_controller()
        result = c.update(13.0, 77.0, 150.0, "3", now_s=0.0)
        self.assertEqual(result["command"], CMD_HOVER)

    def test_low_altitude_forces_hover(self):
        c = self.make_controller(glide_disable_altitude_m=50.0)
        # Way off track but too low to glide.
        lon_offset = 30.0 / (111320.0 * math.cos(math.radians(13.0)))
        result = c.update(
            13.0 + 50.0 / 111320.0, 77.0 + lon_offset, 40.0,
            "6", now_s=0.0,
        )
        self.assertEqual(result["command"], CMD_HOVER)

    def test_large_error_triggers_glide_and_transmit(self):
        c = self.make_controller()
        # 30 m east of the line, halfway up -> should glide left
        # (east of line = right side = correction is GLIDE_LEFT).
        lon_offset = 30.0 / (111320.0 * math.cos(math.radians(13.0)))
        lat = 13.0 + 50.0 / 111320.0
        lon = 77.0 + lon_offset
        result = c.update(lat, lon, 150.0, "6", now_s=0.0)
        self.assertEqual(result["command"], CMD_GLIDE_LEFT)
        self.assertTrue(result["transmit"])

    def test_small_error_stays_hover(self):
        c = self.make_controller()
        lon_offset = 5.0 / (111320.0 * math.cos(math.radians(13.0)))
        lat = 13.0 + 50.0 / 111320.0
        lon = 77.0 + lon_offset
        result = c.update(lat, lon, 150.0, "6", now_s=0.0)
        self.assertEqual(result["command"], CMD_HOVER)
        self.assertFalse(result["transmit"])

    def test_hysteresis_prevents_chatter(self):
        c = self.make_controller(
            start_glide_threshold_m=20.0, stop_glide_threshold_m=10.0
        )
        lat = 13.0 + 50.0 / 111320.0

        def lon_for_offset(offset_m):
            return 77.0 + offset_m / (111320.0 * math.cos(math.radians(13.0)))

        # Cross the start threshold -> begin glide, transmits once.
        r1 = c.update(lat, lon_for_offset(21.0), 150.0, "6", now_s=0.0)
        self.assertEqual(r1["command"], CMD_GLIDE_LEFT)
        self.assertTrue(r1["transmit"])

        # Drop to inside the hysteresis band (between stop and start) ->
        # command should PERSIST as GLIDE_LEFT, not oscillate to HOVER,
        # and should NOT retransmit since nothing changed.
        r2 = c.update(lat, lon_for_offset(15.0), 150.0, "6", now_s=1.0)
        self.assertEqual(r2["command"], CMD_GLIDE_LEFT)
        self.assertFalse(r2["transmit"])

        # Drop below stop threshold -> HOVER, transmits (rate limit ok
        # since >= min_command_interval_s has passed... use a big now_s).
        r3 = c.update(lat, lon_for_offset(5.0), 150.0, "6", now_s=5.0)
        self.assertEqual(r3["command"], CMD_HOVER)
        self.assertTrue(r3["transmit"])

    def test_rate_limiting_blocks_rapid_retransmit(self):
        c = self.make_controller(min_command_interval_s=2.0)
        lat = 13.0 + 50.0 / 111320.0

        def lon_for_offset(offset_m):
            return 77.0 + offset_m / (111320.0 * math.cos(math.radians(13.0)))

        r1 = c.update(lat, lon_for_offset(25.0), 150.0, "6", now_s=0.0)
        self.assertTrue(r1["transmit"])

        # Error direction flips immediately (change=True) but only
        # 0.1s later -- should be rate limited.
        r2 = c.update(lat, lon_for_offset(-25.0), 150.0, "6", now_s=0.1)
        self.assertEqual(r2["command"], CMD_GLIDE_RIGHT)
        self.assertFalse(r2["transmit"])

    def test_altitude_gate_hover_bypasses_rate_limit(self):
        """
        Safety-critical: once a GLIDE command has just been sent, dropping
        below the altitude gate must transmit HOVER immediately, even if
        it's within the normal rate-limit window -- it must NOT wait.
        """
        c = self.make_controller(min_command_interval_s=2.0)
        lon_offset = 30.0 / (111320.0 * math.cos(math.radians(13.0)))
        lat_high = 13.0 + 100.0 / 111320.0

        r1 = c.update(lat_high, 77.0 + lon_offset, 150.0, "6", now_s=0.0)
        self.assertEqual(r1["command"], CMD_GLIDE_LEFT)
        self.assertTrue(r1["transmit"])

        # 0.1s later (well within the 2s rate limit window), altitude
        # drops below the glide-disable gate.
        lat_low = 13.0 + 40.0 / 111320.0
        r2 = c.update(lat_low, 77.0 + lon_offset, 40.0, "6", now_s=0.1)
        self.assertEqual(r2["command"], CMD_HOVER)
        self.assertTrue(r2["transmit"], "altitude-gate HOVER must not be rate limited")

    def test_flight_state_gate_hover_bypasses_rate_limit(self):
        """Same safety requirement for the flight-state gate."""
        c = self.make_controller(min_command_interval_s=2.0)
        lon_offset = 30.0 / (111320.0 * math.cos(math.radians(13.0)))
        lat = 13.0 + 100.0 / 111320.0

        r1 = c.update(lat, 77.0 + lon_offset, 150.0, "6", now_s=0.0)
        self.assertTrue(r1["transmit"])

        r2 = c.update(lat, 77.0 + lon_offset, 150.0, "3", now_s=0.1)  # ASCENT
        self.assertEqual(r2["command"], CMD_HOVER)
        self.assertTrue(r2["transmit"], "flight-state-gate HOVER must not be rate limited")


class TestCommandGenerator(unittest.TestCase):
    def test_build_and_parse_roundtrip(self):
        gen = CommandGenerator()
        packet = gen.build("GLIDE_LEFT")
        parsed = parse_command_packet(packet)
        self.assertIsNotNone(parsed)
        seq, command = parsed
        self.assertEqual(seq, 1)
        self.assertEqual(command, "GLIDE_LEFT")

    def test_corrupted_checksum_rejected(self):
        gen = CommandGenerator()
        packet = gen.build("HOVER")
        corrupted = packet[:-2] + "00"
        # Only assert rejection if we actually corrupted the checksum.
        if corrupted != packet:
            self.assertIsNone(parse_command_packet(corrupted))

    def test_ack_flow(self):
        gen = CommandGenerator()
        packet = gen.build("GLIDE_RIGHT")
        seq, _ = parse_command_packet(packet)
        self.assertEqual(gen.unacked_older_than(0), [seq])
        ok = gen.on_ack(f"ACK,{seq},GLIDE_RIGHT")
        self.assertTrue(ok)
        self.assertEqual(gen.unacked_older_than(0), [])


if __name__ == "__main__":
    unittest.main()
