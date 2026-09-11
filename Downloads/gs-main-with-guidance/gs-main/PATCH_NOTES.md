# Guidance Integration — Patch Notes

Everything below was tested against your actual repo (not a
reconstruction) — see "How this was verified" at the end.

## New files

```
guidance/__init__.py
guidance/coordinate_utils.py       GPS -> local metres, distance, bearing, cross-track error
guidance/landing_controller.py     Deterministic GLIDE/HOVER decision logic
guidance/wind_estimator.py         GPS-history drift estimate (imported as GuidanceWindEstimator)
guidance/command_generator.py      Optional structured command packets (NOT wired in by default)
guidance/README.md                 Full explanation of the FLIGHT_STATE convention and data flow

ui/dashboards/guidance_dashboard.py   New "Guidance" tab widget

tests/test_guidance.py             19 unit tests
scripts/guidance_e2e_smoke_test.py End-to-end test driving the real MainWindow
```

## Modified files

**`ui/dashboards/__init__.py`**
Added `from .guidance_dashboard import GuidanceDashboard`.

**`ui/main_window.py`**
- Added `import time`.
- Added imports: `LandingController`, `GuidanceWindEstimator` (aliased
  from `guidance.wind_estimator.WindEstimator` to avoid clashing with
  your existing `core.ai.wind_drift.WindEstimator`), `GuidanceDashboard`.
- `__init__`: creates `self.landing_controller`, initializes
  `self.guidance_wind_estimator = None` (created lazily on first GPS
  fix), `self._guidance_reference_set = False`,
  `self._guidance_auto_mode = True`.
- `_build_ui`: creates `self.guidance_dashboard`, adds it as a
  "Guidance" tab, calls `self._wire_guidance_ui()` after `_build_ui()`
  in `__init__`.
- New methods: `_wire_guidance_ui`, `_on_set_guidance_target`,
  `_on_guidance_mode_toggled`, `_send_manual_guidance_command`,
  `_update_guidance`.
- `_handle_line`: added one line, `self._update_guidance(packet)`,
  right after the existing `self._update_ai(packet)` call. Nothing
  else in this method changed.

**`firmware/flight_transmitter.ino`**
- Added `#include <Servo.h>` and a `Servo servo2` object.
- Added `SERVO2_PIN`, `CAM_POS_HOVER/LEFT/RIGHT`, `SERVO_MIN/MAX`
  (all placeholders — see "What you still need to do").
- Added `GUIDANCE_ALLOWED_STATE 6` (SECONDARY_DEPLOY) and
  `GUIDANCE_TIMEOUT_MS 5000`.
- `setup()`: attaches the servo and sets it to `CAM_POS_HOVER`.
- `loop()`: added a call to `guidanceFailsafeCheck()`.
- Added `safeServoPosition()`, `executeHover/GlideLeft/GlideRight()`,
  `guidanceFailsafeCheck()`.
- `handleCommand()`: added an `else if` branch handling `HOVER`,
  `GLIDE_LEFT`, `GLIDE_RIGHT`, gated to `flightState ==
  GUIDANCE_ALLOWED_STATE`. Your existing `CXON`/`CXOFF`/`CAL` handling
  is untouched.

## Nothing else was touched

`core/`, `ui/dashboards/telemetry_dashboard.py` and the other existing
dashboards, `ui/graphs/`, `ui/commands/`, `ui/reports/`,
`ui/simulation_tab.py`, `simulation/`, `firmware/ground_receiver.ino`,
and all AI modules are unmodified.

## A bug I found and fixed while testing (worth knowing about)

The first version of `landing_controller.py` applied the same
2-second command rate limit to *every* command change, including the
altitude-gate's forced `HOVER`. In the end-to-end test this meant: if
the CanSat had just been sent `GLIDE_LEFT` and then dropped below the
50m altitude gate less than 2 seconds later, the safety `HOVER` would
be silently held back until the rate-limit window passed. Fixed by
adding an `urgent` flag so the altitude-gate and flight-state-gate
`HOVER` transitions always transmit immediately, while normal
`GLIDE_LEFT`/`GLIDE_RIGHT` corrections still respect the rate limit.
Covered by two new regression tests
(`test_altitude_gate_hover_bypasses_rate_limit`,
`test_flight_state_gate_hover_bypasses_rate_limit`).

## What you still need to do before this flies

1. **Calibrate the servo/cam mechanism** and replace the placeholder
   `CAM_POS_*` / `SERVO_MIN` / `SERVO_MAX` values in
   `firmware/flight_transmitter.ino`.
2. **Confirm your real flight computer's FLIGHT_STATE numbering**
   matches `core/telemetry/constants.FLIGHT_STATES` (this repo's fake
   sensor firmware never actually advances `flightState` — it's
   hardcoded to `2`, so you can't fully exercise the gate on real
   hardware until your actual flight firmware sets it correctly).
3. **Tune thresholds** (`start_glide_threshold_m`,
   `stop_glide_threshold_m`, `glide_disable_altitude_m`,
   `min_command_interval_s`) in `MainWindow.__init__` for your real
   descent rate.
4. **Bench test the firmware command handling** over serial before
   connecting it to the GS's automatic output.

## How this was verified

- `python3 -m unittest tests.test_guidance -v` — 19/19 pass.
- `python3 -m pytest tests/ -q` — all 23 tests in the repo (including
  your existing `test_packet.py`, `test_ai.py`, `test_graphs.py`)
  pass unmodified.
- `python3 scripts/guidance_e2e_smoke_test.py` — instantiates the
  **real** `MainWindow`, stubs only the serial transport, and feeds
  fabricated telemetry lines through the actual `_handle_line()` path.
  Confirms: reference point set from first GPS fix, target arming via
  the dashboard's actual button/fields, `GLIDE_LEFT` transmitted once
  cross-track error exceeds threshold, immediate `HOVER` transmitted
  the instant altitude drops below the gate (not delayed by rate
  limiting), flight-state gate forcing `HOVER`, and MANUAL mode
  correctly blocking automatic transmission while still accepting
  manual override button presses.
- `python3 -c "import main"` — the app's real entry point imports
  cleanly with the new code in place.
