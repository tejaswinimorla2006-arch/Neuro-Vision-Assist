"""
step_detector.py - Neuro Vision Assist
=======================================
Production-quality walking detector and step counter for the MPU9250.

Why the old detector failed
----------------------------
The previous implementation applied a single threshold to the raw accel
magnitude (including gravity).  Any jerk — picking up the device, shaking
it, rotating it — crosses 1.08 g and registers as a step.

This module fixes every one of those failure modes:

Signal pipeline (per sample at 50 Hz)
--------------------------------------
  raw (ax, ay, az, gz)
      │
      ▼
  1. Gravity removal          — subtract the low-pass-filtered gravity vector
                                so only dynamic acceleration remains
      │
      ▼
  2. Magnitude                — |a_dynamic| = sqrt(ax²+ay²+az²)
      │
      ▼
  3. High-pass filter         — removes slow tilts (< STEP_BP_LOW_HZ)
      │
      ▼
  4. Moving-average smoother  — removes high-frequency vibration
      │
      ▼
  5. Peak detection           — rising-edge crossing of STEP_THRESHOLD_G
      │
      ▼
  6. Prominence filter        — peak must exceed local baseline by
                                STEP_PROMINENCE_G (rejects small bumps)
      │
      ▼
  7. Debounce                 — minimum STEP_DEBOUNCE_S between steps
      │
      ▼
  8. Gyro validation          — reject if |gz| > GYRO_SHAKE_THRESH
                                (device is rotating, not walking)
      │
      ▼
  9. Motion classifier gate   — only count steps when state == WALKING
      │
      ▼
  10. Cadence validation      — inter-step intervals must fall in
                                [1/CADENCE_MAX_HZ, 1/CADENCE_MIN_HZ]
      │
      ▼
  Confirmed step → Weinberg adaptive step length → accumulate distance

Motion classifier
-----------------
Runs on a 0.5 s sliding window (MOTION_WINDOW samples).
Computes RMS of gravity-removed accel and RMS of gyro.

  RMS_accel < MOTION_STILL_RMS              → STILL
  RMS_gyro  > MOTION_GYRO_RMS               → SHAKING / ROTATING
  MOTION_STILL_RMS ≤ RMS_accel ≤ WALK_MAX   → WALKING (cadence confirmed)
  RMS_accel > WALK_MAX                       → RUNNING

Public API
----------
  StepDetector()
    .update(ax, ay, az, gz) → bool   (True = confirmed step)
    .reset()                          reset segment counters
    .step_count             → int
    .distance_m             → float
    .motion_state           → str    "still"|"walking"|"running"|"shaking"
    .is_still               → bool
    .heading                → float  degrees
"""

import math
import time
from collections import deque

from config import (
    GRAVITY_G,
    STEP_BP_LOW_HZ, STEP_BP_HIGH_HZ,
    STEP_FILTER_WINDOW,
    STEP_PROMINENCE_G, STEP_THRESHOLD_G,
    STEP_DEBOUNCE_S,
    CADENCE_WINDOW, CADENCE_MIN_HZ, CADENCE_MAX_HZ,
    GYRO_SHAKE_THRESH,
    STILL_TIMEOUT_S,
    STEP_LENGTH_K, STEP_LENGTH_MIN, STEP_LENGTH_MAX,
    MOTION_STILL_RMS, MOTION_WALK_RMS_MAX, MOTION_GYRO_RMS, MOTION_WINDOW,
    HEADING_ALPHA,
    NAV_POLL_S,
)
import debug_log

# ── IIR filter coefficients (computed once at import) ─────────────────────────
# Simple first-order IIR filters derived from cut-off frequencies.
# alpha = dt / (dt + RC),  RC = 1 / (2π * fc)
_DT = NAV_POLL_S  # 0.02 s at 50 Hz

def _alpha(fc: float) -> float:
    rc = 1.0 / (2.0 * math.pi * fc)
    return _DT / (_DT + rc)

_LP_ALPHA  = _alpha(STEP_BP_HIGH_HZ)   # low-pass  for gravity estimation
_HP_ALPHA  = 1.0 - _alpha(STEP_BP_LOW_HZ)  # high-pass complement


class MotionClassifier:
    """
    Classifies device motion from a sliding window of IMU samples.

    States
    ------
    still    : device is stationary
    walking  : rhythmic gait detected
    running  : high-intensity motion
    shaking  : high gyro rate — device being shaken or rotated
    """

    def __init__(self):
        self._accel_buf: deque[float] = deque(maxlen=MOTION_WINDOW)
        self._gyro_buf:  deque[float] = deque(maxlen=MOTION_WINDOW)
        self._state = "still"

    def update(self, dyn_mag: float, gyro_mag: float) -> str:
        """
        Feed one sample (gravity-removed accel magnitude, gyro magnitude).
        Returns current motion state string.
        """
        self._accel_buf.append(dyn_mag)
        self._gyro_buf.append(gyro_mag)

        if len(self._accel_buf) < MOTION_WINDOW:
            return self._state  # not enough data yet

        rms_a = math.sqrt(sum(x*x for x in self._accel_buf) / MOTION_WINDOW)
        rms_g = math.sqrt(sum(x*x for x in self._gyro_buf)  / MOTION_WINDOW)

        if rms_g > MOTION_GYRO_RMS:
            self._state = "shaking"
        elif rms_a < MOTION_STILL_RMS:
            self._state = "still"
        elif rms_a > MOTION_WALK_RMS_MAX:
            self._state = "running"
        else:
            self._state = "walking"

        return self._state

    @property
    def state(self) -> str:
        return self._state


class StepDetector:
    """
    Full signal-processing pipeline for robust step detection.
    See module docstring for the complete algorithm description.
    """

    def __init__(self):
        # ── Gravity estimation (low-pass on raw accel vector) ──────────────────
        self._grav_x = 0.0
        self._grav_y = 0.0
        self._grav_z = GRAVITY_G   # initial assumption: device upright

        # ── High-pass filter state (on dynamic magnitude) ──────────────────────
        self._hp_prev_in  = 0.0
        self._hp_prev_out = 0.0

        # ── Moving-average smoother ────────────────────────────────────────────
        self._smooth_buf: deque[float] = deque(maxlen=STEP_FILTER_WINDOW)

        # ── Valley tracker for prominence filter ───────────────────────────────
        # Tracks the minimum smoothed value since the last confirmed step
        self._valley_min: float = 0.0

        # ── Peak detection state ───────────────────────────────────────────────
        self._above_threshold: bool  = False
        self._peak_value:      float = 0.0   # highest value seen in current peak

        # ── Weinberg window (peak/valley of dynamic mag since last step) ───────
        self._win_max: float = 0.0
        self._win_min: float = float("inf")

        # ── Debounce ───────────────────────────────────────────────────────────
        self._last_step_t: float = 0.0

        # ── Cadence validation ─────────────────────────────────────────────────
        # Ring buffer of the last CADENCE_WINDOW inter-step intervals (seconds)
        self._intervals: deque[float] = deque(maxlen=CADENCE_WINDOW)

        # ── Step / distance counters ───────────────────────────────────────────
        self._step_count: int   = 0
        self._distance_m: float = 0.0

        # ── Motion classifier ──────────────────────────────────────────────────
        self._classifier = MotionClassifier()

        # ── Heading (complementary filter: gyro + mag) ─────────────────────────
        self._heading:  float = 0.0
        self._last_t:   float = time.monotonic()

    # ── Public API ─────────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Reset segment counters (step count + distance).  Heading is preserved."""
        self._step_count      = 0
        self._distance_m      = 0.0
        self._last_step_t     = 0.0
        self._above_threshold = False
        self._peak_value      = 0.0
        self._win_max         = 0.0
        self._win_min         = float("inf")
        self._valley_min      = 0.0
        self._intervals.clear()
        self._smooth_buf.clear()

    def update(self, ax: float, ay: float, az: float, gz: float = 0.0) -> bool:
        """
        Feed one calibrated IMU sample at 50 Hz.

        Parameters
        ----------
        ax, ay, az : calibrated accel in g-units (gravity removed by calibration
                     offsets in imu_reader.py, but we re-estimate here for robustness)
        gz         : calibrated yaw rate in °/s

        Returns
        -------
        True if a confirmed walking step was detected this sample.
        """
        now = time.monotonic()
        dt  = now - self._last_t
        self._last_t = now

        # ── 1. Update heading ──────────────────────────────────────────────────
        self._heading = (self._heading + gz * dt) % 360.0

        # ── 2. Gravity estimation via low-pass filter on raw accel ─────────────
        self._grav_x += _LP_ALPHA * (ax - self._grav_x)
        self._grav_y += _LP_ALPHA * (ay - self._grav_y)
        self._grav_z += _LP_ALPHA * (az - self._grav_z)

        # ── 3. Dynamic acceleration (gravity removed) ──────────────────────────
        dyn_x = ax - self._grav_x
        dyn_y = ay - self._grav_y
        dyn_z = az - self._grav_z
        dyn_mag = math.sqrt(dyn_x*dyn_x + dyn_y*dyn_y + dyn_z*dyn_z)

        # Gyro magnitude for classifier and shake detection
        gyro_mag = abs(gz)

        # ── 4. Motion classifier ───────────────────────────────────────────────
        motion = self._classifier.update(dyn_mag, gyro_mag)

        # ── 5. High-pass filter (removes slow tilts) ───────────────────────────
        hp_out = _HP_ALPHA * (self._hp_prev_out + dyn_mag - self._hp_prev_in)
        self._hp_prev_in  = dyn_mag
        self._hp_prev_out = hp_out
        filtered = abs(hp_out)

        # ── 6. Moving-average smoother ─────────────────────────────────────────
        self._smooth_buf.append(filtered)
        smoothed = sum(self._smooth_buf) / len(self._smooth_buf)

        # Track Weinberg window
        self._win_max = max(self._win_max, dyn_mag)
        self._win_min = min(self._win_min, dyn_mag)

        # Track valley for prominence
        self._valley_min = min(self._valley_min, smoothed)

        # ── 7. Peak detection ──────────────────────────────────────────────────
        step_detected = False

        if smoothed > STEP_THRESHOLD_G:
            if not self._above_threshold:
                # Rising edge — start of a potential peak
                self._above_threshold = True
                self._peak_value      = smoothed
            else:
                self._peak_value = max(self._peak_value, smoothed)
        else:
            if self._above_threshold:
                # Falling edge — evaluate the completed peak
                self._above_threshold = False
                step_detected = self._evaluate_peak(now, gyro_mag, motion)
                # Reset valley tracker for next inter-step window
                self._valley_min = smoothed

        return step_detected

    def _evaluate_peak(self, now: float, gyro_mag: float, motion: str) -> bool:
        """
        Called on the falling edge of each peak.
        Applies all validation gates in order.
        Logs the reason for every rejection.
        Returns True only if all gates pass.
        """
        peak = self._peak_value
        prominence = peak - self._valley_min

        # Gate 1: Prominence
        if prominence < STEP_PROMINENCE_G:
            debug_log.step_rej(peak, "low_prominence",
                               f"prominence={prominence:.4f}g < {STEP_PROMINENCE_G}")
            return False

        # Gate 2: Debounce
        elapsed = now - self._last_step_t
        if elapsed < STEP_DEBOUNCE_S:
            debug_log.step_rej(peak, "debounce",
                               f"elapsed={elapsed:.3f}s < {STEP_DEBOUNCE_S}")
            return False

        # Gate 3: Gyro shake rejection
        if gyro_mag > GYRO_SHAKE_THRESH:
            debug_log.step_rej(peak, "gyro_shake",
                               f"gyro={gyro_mag:.1f}°/s > {GYRO_SHAKE_THRESH}")
            return False

        # Gate 4: Motion classifier
        if motion not in ("walking", "running"):
            debug_log.step_rej(peak, "classifier_not_walking",
                               f"motion={motion}")
            return False

        # Gate 5: Cadence validation
        if self._last_step_t > 0.0:
            self._intervals.append(elapsed)
            if len(self._intervals) >= CADENCE_WINDOW:
                avg_interval = sum(self._intervals) / len(self._intervals)
                cadence_hz   = 1.0 / avg_interval if avg_interval > 0 else 0.0
                if not (CADENCE_MIN_HZ <= cadence_hz <= CADENCE_MAX_HZ):
                    debug_log.step_rej(peak, "cadence",
                                       f"cadence={cadence_hz:.2f}Hz not in [{CADENCE_MIN_HZ},{CADENCE_MAX_HZ}]")
                    self._intervals.clear()
                    return False

        # All gates passed
        step_length = self._weinberg_step_length()
        cadence     = self._current_cadence()
        self._last_step_t = now
        self._step_count += 1
        self._distance_m += step_length

        self._win_max = 0.0
        self._win_min = float("inf")

        debug_log.step_ok(self._step_count, peak, prominence, step_length,
                          self._distance_m, cadence, motion, gyro_mag)
        return True

    def _weinberg_step_length(self) -> float:
        """L = K * (a_max - a_min)^0.25 on the gravity-removed dynamic signal."""
        accel_range = max(0.0, self._win_max - self._win_min)
        if accel_range < 1e-6:
            return (STEP_LENGTH_MIN + STEP_LENGTH_MAX) / 2.0
        length = STEP_LENGTH_K * (accel_range ** 0.25)
        return max(STEP_LENGTH_MIN, min(STEP_LENGTH_MAX, length))

    def _current_cadence(self) -> float:
        if not self._intervals:
            return 0.0
        avg = sum(self._intervals) / len(self._intervals)
        return 1.0 / avg if avg > 0 else 0.0

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def step_count(self) -> int:
        return self._step_count

    @property
    def distance_m(self) -> float:
        return self._distance_m

    @property
    def motion_state(self) -> str:
        return self._classifier.state

    @property
    def heading(self) -> float:
        return self._heading

    @property
    def is_still(self) -> bool:
        # Use the motion classifier as the primary stillness signal.
        # The classifier operates on a sliding window of IMU samples and
        # correctly identifies "still" vs "walking" vs "shaking".
        # The step-recency timeout is kept as a fallback: if the classifier
        # says "walking" but no step has arrived for STILL_TIMEOUT_S, the
        # user has stopped and the classifier window hasn't caught up yet.
        if self._classifier.state not in ("walking", "running"):
            return True
        if self._last_step_t == 0.0:
            return True
        return (time.monotonic() - self._last_step_t) >= STILL_TIMEOUT_S
