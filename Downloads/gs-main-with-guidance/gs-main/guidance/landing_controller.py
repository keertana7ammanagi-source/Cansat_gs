"""
guidance/landing_controller.py

Deterministic precision-landing guidance controller.

Responsibility: given the current GPS position, altitude, flight state,
target position and a wind/drift estimate, decide whether to command
GLIDE_LEFT, GLIDE_RIGHT or HOVER.

This module deliberately does NOT talk to LoRa, PyQt, or the dashboards.
It is a pure decision-making class so it can be:
  - unit tested in isolation (tests/test_landing_controller.py)
  - driven by a simulator with fake telemetry (simulation/)
  - reused unchanged if the transport layer changes

Design choices, matching the plan:
  - cross-track error is computed against the ORIGIN->TARGET line,
    not against the wind vector.
  - hysteresis prevents command chatter near the threshold.
  - an altitude gate disables glide commands close to the ground.
  - only flight states in ALLOWED_GLIDE_STATES may glide.
  - commands are rate-limited so we don't spam the link / servo.
"""

import time

from guidance.coordinate_utils import gps_to_local, distance_m, cross_track_error

# Commands
CMD_HOVER = "HOVER"
CMD_GLIDE_LEFT = "GLIDE_LEFT"
CMD_GLIDE_RIGHT = "GLIDE_RIGHT"

# This repo's TelemetryPacket stores FLIGHT_STATE as the raw string sent
# by the CanSat -- which, per firmware/flight_transmitter.ino and
# core/telemetry/constants.FLIGHT_STATES, is the numeric INDEX into
# FLIGHT_STATES as a string (e.g. "6"), NOT the state name. Index 6 is
# SECONDARY_DEPLOY. Only glide once the secondary/ANTRS stage has
# deployed, matching main_window.py's existing wind-estimation gate
# (which also only runs during states 5/6 = DESCENT/SECONDARY_DEPLOY).
#
# If you change FLIGHT_STATES order in constants.py, update this too --
# or pass allowed_glide_states=... explicitly to the constructor using
# str(FLIGHT_STATES.index("SECONDARY_DEPLOY")).
ALLOWED_GLIDE_STATES = {"6"}  # SECONDARY_DEPLOY


class LandingController:
    def __init__(
        self,
        start_glide_threshold_m=20.0,
        stop_glide_threshold_m=10.0,
        glide_disable_altitude_m=50.0,
        min_command_interval_s=2.0,
        allowed_glide_states=None,
    ):
        """
        start_glide_threshold_m: cross-track error above which glide begins.
        stop_glide_threshold_m:  cross-track error below which glide stops.
                                  (must be < start_glide_threshold_m, this
                                  gap is the hysteresis band)
        glide_disable_altitude_m: below this altitude, always HOVER.
        min_command_interval_s:  minimum time between two transmitted
                                  commands, even if the decision changes.
        allowed_glide_states:    set of FLIGHT_STATE values (as they
                                  appear in packet.get("FLIGHT_STATE"))
                                  during which glide is permitted.
                                  Defaults to ALLOWED_GLIDE_STATES.
        """
        if stop_glide_threshold_m >= start_glide_threshold_m:
            raise ValueError(
                "stop_glide_threshold_m must be smaller than "
                "start_glide_threshold_m to create a hysteresis band"
            )

        self.start_glide_threshold_m = start_glide_threshold_m
        self.stop_glide_threshold_m = stop_glide_threshold_m
        self.glide_disable_altitude_m = glide_disable_altitude_m
        self.min_command_interval_s = min_command_interval_s
        self.allowed_glide_states = allowed_glide_states or ALLOWED_GLIDE_STATES

        self.origin = None          # (east, north) - set via set_origin()
        self.target = None          # (east, north) - set via set_target()
        self.ref_lat = None
        self.ref_lon = None

        self.armed = False
        self.current_command = CMD_HOVER
        self._last_sent_time = None
        self._last_sent_command = None

        # Diagnostics from the most recent update(), exposed for the GUI.
        self.last_distance_m = 0.0
        self.last_cross_track_m = 0.0
        self.last_cross_track_sign = 0.0
        self.last_reason = "not armed"

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def set_reference(self, ref_lat, ref_lon):
        """
        Set the GPS reference point (typically the launch point) used to
        convert all subsequent GPS fixes into local metres. Call this
        once, before set_origin()/set_target()/update().
        """
        self.ref_lat = ref_lat
        self.ref_lon = ref_lon

    def set_origin(self, lat, lon):
        """Set the start of the desired descent line (e.g. launch point)."""
        self._require_reference()
        self.origin = gps_to_local(lat, lon, self.ref_lat, self.ref_lon)

    def set_target(self, lat, lon):
        """Set the landing target."""
        self._require_reference()
        self.target = gps_to_local(lat, lon, self.ref_lat, self.ref_lon)

    def arm(self):
        self.armed = True

    def disarm(self):
        self.armed = False
        self.current_command = CMD_HOVER

    def _require_reference(self):
        if self.ref_lat is None or self.ref_lon is None:
            raise RuntimeError(
                "set_reference(lat, lon) must be called before "
                "set_origin()/set_target()"
            )

    # ------------------------------------------------------------------
    # Main decision function
    # ------------------------------------------------------------------

    def update(self, lat, lon, altitude_m, flight_state, now_s=None):
        """
        Feed one telemetry sample. Returns a dict describing the decision:

            {
                "command": "GLIDE_LEFT" | "GLIDE_RIGHT" | "HOVER",
                "transmit": bool,   # True if this command should actually
                                     # be sent this cycle (False if rate
                                     # limited or unchanged/persisted)
                "distance_m": float,
                "cross_track_m": float,
                "cross_track_sign": float,
                "reason": str,
            }

        `now_s` defaults to time.monotonic() if not supplied, but should
        be the packet's own timestamp when replaying logs/simulation.
        """
        if now_s is None:
            now_s = time.monotonic()

        if not self.armed:
            self.last_reason = "not armed"
            return self._result(CMD_HOVER, False, now_s, "not armed")

        if self.origin is None or self.target is None:
            self.last_reason = "origin/target not set"
            return self._result(CMD_HOVER, False, now_s, "origin/target not set")

        if flight_state not in self.allowed_glide_states:
            decision = CMD_HOVER
            reason = f"flight state '{flight_state}' does not permit glide"
            return self._decide(decision, now_s, reason, urgent=True)

        if altitude_m < self.glide_disable_altitude_m:
            decision = CMD_HOVER
            reason = f"altitude {altitude_m:.1f}m below glide-disable gate"
            return self._decide(decision, now_s, reason, urgent=True)

        current = gps_to_local(lat, lon, self.ref_lat, self.ref_lon)
        dist = distance_m(current, self.target)
        error, sign = cross_track_error(self.origin, self.target, current)

        self.last_distance_m = dist
        self.last_cross_track_m = error
        self.last_cross_track_sign = sign

        decision, reason = self._apply_hysteresis(error, sign)
        return self._decide(decision, now_s, reason)

    def _apply_hysteresis(self, error, sign):
        """
        sign > 0  -> CanSat is right of the desired line -> need to move
                     left -> GLIDE_LEFT
        sign < 0  -> CanSat is left of the desired line -> need to move
                     right -> GLIDE_RIGHT
        """
        currently_gliding = self.current_command != CMD_HOVER

        if not currently_gliding:
            if error >= self.start_glide_threshold_m:
                cmd = CMD_GLIDE_LEFT if sign > 0 else CMD_GLIDE_RIGHT
                return cmd, f"error {error:.1f}m >= start threshold, begin glide"
            return CMD_HOVER, f"error {error:.1f}m below start threshold"
        else:
            if error <= self.stop_glide_threshold_m:
                return CMD_HOVER, f"error {error:.1f}m <= stop threshold, stop glide"
            # Still outside the stop band: keep correcting toward the
            # current sign (re-evaluate direction in case it flipped).
            cmd = CMD_GLIDE_LEFT if sign > 0 else CMD_GLIDE_RIGHT
            return cmd, f"error {error:.1f}m still outside hysteresis band"

    def _decide(self, decision, now_s, reason, urgent=False):
        """
        urgent=True bypasses the rate limiter on a change to HOVER --
        used for the altitude and flight-state safety gates, which must
        never be held back by the same rate limit that smooths normal
        directional corrections. Rate limiting still applies to
        ordinary GLIDE_LEFT/GLIDE_RIGHT corrections.
        """
        self.last_reason = reason
        changed = decision != self.current_command
        self.current_command = decision

        transmit = False
        if changed:
            transmit = True if urgent else self._rate_limit_ok(now_s)
        # If unchanged, we deliberately do NOT retransmit (command
        # persistence) -- the CanSat should already be holding this
        # command. A watchdog/timeout on the CanSat side handles the
        # case where it never got the last one.

        if transmit:
            self._last_sent_time = now_s
            self._last_sent_command = decision

        return self._result(decision, transmit, now_s, reason)

    def _rate_limit_ok(self, now_s):
        if self._last_sent_time is None:
            return True
        return (now_s - self._last_sent_time) >= self.min_command_interval_s

    def _result(self, command, transmit, now_s, reason):
        return {
            "command": command,
            "transmit": transmit,
            "distance_m": self.last_distance_m,
            "cross_track_m": self.last_cross_track_m,
            "cross_track_sign": self.last_cross_track_sign,
            "reason": reason,
        }
