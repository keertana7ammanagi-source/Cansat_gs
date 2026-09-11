# Precision-Landing Guidance

Adds closed-loop GLIDE_LEFT / GLIDE_RIGHT / HOVER guidance to the Ground
Station, following the existing architecture: dashboards only *display*
what `LandingController` decides. Nothing here changes telemetry parsing,
logging, or the other dashboards.

## Files

```
guidance/
  coordinate_utils.py    GPS -> local (east, north) metres, distance,
                          bearing, cross-track error
  wind_estimator.py      GPS-history drift estimate (deterministic,
                          Phase 1 -- no ML). Imported in main_window.py
                          as GuidanceWindEstimator to avoid clashing
                          with core.ai.wind_drift.WindEstimator, which
                          is kept unchanged and still drives the
                          Mission tab's AI panel.
  landing_controller.py  Deterministic decision logic: hysteresis,
                          altitude gate, flight-state gate, command
                          rate limiting
  command_generator.py   Optional structured "CMD,<seq>,<cmd>,<checksum>"
                          packets with ACK tracking -- NOT wired into
                          main_window.py by default, since the existing
                          command channel (self._send_cmd / SerialLink)
                          already sends plain strings like CXON/CAL and
                          firmware/flight_transmitter.ino now expects
                          plain "HOVER"/"GLIDE_LEFT"/"GLIDE_RIGHT". Use
                          this only if you want checksum/sequence
                          protection and are willing to update the
                          firmware parser to match.

ui/dashboards/guidance_dashboard.py
    New "Guidance" tab: target lat/lon entry + SET TARGET, AUTO/MANUAL
    mode toggle, manual override buttons, live display of distance,
    cross-track error, wind/drift, current command and reason.

firmware/flight_transmitter.ino
    Extended handleCommand() to accept HOVER / GLIDE_LEFT / GLIDE_RIGHT,
    gated to flightState == 6 (SECONDARY_DEPLOY), with servo angle
    clamping and a 5s failsafe timeout back to HOVER if no further
    guidance command arrives.

tests/test_guidance.py
    17 unit tests for coordinate math, hysteresis, altitude gate,
    flight-state gate, rate limiting, and command packet round-trip.
    Run: python3 -m unittest tests.test_guidance -v
```

## FLIGHT_STATE convention (important)

`core/telemetry/constants.FLIGHT_STATES` is:

```
0 BOOT, 1 TEST_MODE, 2 LAUNCH_PAD, 3 ASCENT, 4 PRIMARY_DEPLOY,
5 DESCENT, 6 SECONDARY_DEPLOY, 7 IMPACT, 8 RECOVERY
```

`packet.get("FLIGHT_STATE")` is the **numeric index as a string**
(`"6"`), not the name — confirmed from `simulation/simulator.py`
(`str(state)`) and the existing `_update_ai()` wind-estimation gate
(`state_int in (5, 6)`). `landing_controller.ALLOWED_GLIDE_STATES`
and `firmware/flight_transmitter.ino`'s `GUIDANCE_ALLOWED_STATE` are
both set to `6` (SECONDARY_DEPLOY) to match. If your actual CanSat
firmware changes flight states differently, or you want glide allowed
during `DESCENT` (5) too, update both sides together — they must
agree, since the GS and the CanSat each independently enforce the
gate as a safety redundancy.

## How a packet flows through guidance now

```
SerialLink line
      |
parse_packet()                          (unchanged)
      |
MainWindow._handle_line()
      |
      +-- existing dashboards/AI (unchanged)
      |
      +-- MainWindow._update_guidance(packet)   <- new
              |
              +-- first GPS fix -> set_reference() + set_origin()
              |                    + create GuidanceWindEstimator
              +-- GuidanceWindEstimator.update() -> guidance_dashboard.update_wind()
              +-- if AUTO and armed:
                    LandingController.update() -> result dict
                    guidance_dashboard.update_guidance(packet, result)
                    if result["transmit"]:
                        self._send_cmd(result["command"])   (same path as CXON/CAL)
```

The controller only **arms** once the operator enters a target lat/lon
in the Guidance tab and presses **SET TARGET** — before that, or in
MANUAL mode, it never transmits.

## What you still need to do before flight

1. **Calibrate the servo/cam mechanism.** `CAM_POS_HOVER/LEFT/RIGHT`
   and `SERVO_MIN/MAX` in `firmware/flight_transmitter.ino` are
   placeholders (90°/60°/120°, clamped 60–120°). Measure your actual
   rod-extension-vs-servo-angle relationship and update these.
2. **Confirm your real CanSat firmware's flight-state numbering**
   matches `core/telemetry/constants.FLIGHT_STATES` — if the real
   flight computer (not this fake-sensor simulator) assigns states
   differently, the `6` in both `landing_controller.py` and
   `flight_transmitter.ino` needs to change together.
3. **Tune the guidance thresholds** in `MainWindow.__init__`
   (`start_glide_threshold_m`, `stop_glide_threshold_m`,
   `glide_disable_altitude_m`, `min_command_interval_s`) based on your
   actual descent rate and rod response time.
4. **Bench test the firmware command handling** (serial monitor,
   typing `HOVER` / `GLIDE_LEFT` / `GLIDE_RIGHT`) before connecting it
   to the Ground Station's automatic output.
5. **Test in simulation first.** Use the Simulation tab with fabricated
   GPS drift (see `tests/test_guidance.py` for example coordinates) to
   confirm AUTO mode arms, transmits, and holds the way you expect,
   before ever using a live GPS + LoRa link.
