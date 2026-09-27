"""
sensor_fusion.py - Neuro Vision Assist
=======================================
EKF-based sensor fusion: IMU step detection gated by IMU motion classifier.

Architecture
------------
The previous design had a critical flaw: it used the camera (is_visually_still)
as the primary gate for distance accumulation.  When the camera is hand-held
and being moved, the camera gate sees real optical flow and reports MOVING,
allowing the EKF to integrate Weinberg step-length freely — even when the
user is not walking.  Camera shake = distance accumulated.

Corrected design
-----------------
  PRIMARY GATE  : IMU motion classifier ("walking" or "running" state).
                  Distance only accumulates when the IMU confirms walking gait.
                  Shaking, rotating, or moving the camera while standing still
                  produces a "shaking" or "still" classifier state, which
                  hard-resets velocity to zero.

  SECONDARY GATE: Camera (is_visually_still) used as a CONFIRMATION gate only.
                  If the camera says STILL but IMU says WALKING, the IMU wins
                  (user may be walking in a featureless corridor).
                  If the camera says STILL AND IMU says STILL, velocity resets.

  DISTANCE SOURCE: Weinberg step-length from confirmed walking steps only.
                   The EKF smooths the velocity between steps.
                   Velocity decays to zero within ~2 steps if no new steps arrive.

  VELOCITY DECAY: Fast enough that velocity reaches ~0 within one step interval
                  (~0.5 s) if no new step arrives.  This prevents phantom
                  accumulation between steps.
                  _VEL_DECAY = 2.0 s^-1 → halves every 0.35 s.

EKF state: scalar forward velocity (m/s)
  Predict:  v = v * exp(-decay * dt)  ≈ v * (1 - decay*dt)
            P = decay^2 * P + Q_vel * dt
  Update:   z = weinberg_step_length / step_interval  (m/s)
            K = P / (P + R_IMU)
            v = v + K * (z - v)
            P = (1 - K) * P
  Gate:     if IMU motion != walking/running → v = 0, P reset

Pose integration (only when walking confirmed):
  delta_m = v * dt
  dx = delta_m * sin(heading)
  dy = delta_m * cos(heading)
  pose += (dx, dy, 0)
"""

import math
import time

from config import (
    EKF_Q_VEL,
    EKF_R_IMU,
    EKF_P0_VEL,
)
import debug_log

# Velocity decay rate (s^-1).  At 50 Hz (dt=0.02 s), each tick multiplies
# velocity by (1 - 2.0*0.02) = 0.96.  After 0.5 s (one step interval) with
# no new step, velocity decays to 0.96^25 ≈ 0.36 of its peak — enough to
# prevent phantom accumulation while still bridging the gap between steps.
_VEL_DECAY = 2.0

# Minimum cadence-confirmed steps before the EKF trusts the walking state.
# Prevents a single accidental step from triggering distance accumulation.
_MIN_STEPS_TO_TRUST = 2


class SensorFusion:

    def __init__(self, step_detector, visual_motion):
        self._imu = step_detector
        self._cam = visual_motion   # confirmation gate only

        self._v = 0.0          # velocity estimate (m/s)
        self._P = EKF_P0_VEL   # scalar covariance ((m/s)^2)

        self._pose  = [0.0, 0.0, 0.0]
        self._delta = [0.0, 0.0, 0.0]
        self._raw_dist_m: float = 0.0

        self._last_step_count: int   = 0
        self._last_imu_dist:   float = 0.0
        self._last_step_t:     float = 0.0

    # ── EKF ────────────────────────────────────────────────────────────────────

    def _predict(self, dt: float) -> None:
        decay    = max(0.0, 1.0 - _VEL_DECAY * dt)
        v_before = self._v
        self._v  = max(0.0, self._v * decay)
        self._P  = decay * decay * self._P + EKF_Q_VEL * dt
        debug_log.ekf_pred(v_before, self._v, self._P, dt)

    def _update(self, z_speed: float, R: float, source: str) -> None:
        if z_speed < 0.0:
            return
        S        = self._P + R
        K        = self._P / S
        v_before = self._v
        self._v  = max(0.0, self._v + K * (z_speed - self._v))
        self._P  = (1.0 - K) * self._P
        debug_log.ekf_update(source, z_speed, K, v_before, self._v, self._P)

    def _reset_velocity(self, reason: str) -> None:
        if self._v > 0.01:
            debug_log.of_gate(reason, self._v, 0.0)
        self._v     = 0.0
        self._P     = EKF_P0_VEL
        self._delta = [0.0, 0.0, 0.0]

    # ── Main tick ──────────────────────────────────────────────────────────────

    def tick(self, dt: float) -> None:
        dt = max(dt, 1e-4)

        # 1. Predict
        self._predict(dt)

        # 2. PRIMARY GATE: IMU motion classifier.
        #    Only "walking" or "running" allows distance to accumulate.
        #    "shaking", "still", or any other state hard-resets velocity.
        #    This is the key fix: camera shake / rotation / device movement
        #    while standing still produces "shaking" or "still" from the IMU
        #    classifier, which prevents any distance from accumulating.
        motion = self._imu.motion_state
        if motion not in ("walking", "running"):
            self._reset_velocity(f"IMU-GATE: motion={motion}, resetting velocity")
            return

        # 3. Require minimum confirmed steps before trusting walking state.
        #    Prevents a single accidental step from triggering accumulation.
        if self._imu.step_count < _MIN_STEPS_TO_TRUST:
            self._reset_velocity("IMU-GATE: insufficient steps to trust walking")
            return

        # 4. SECONDARY GATE: Camera confirmation.
        #    Only applies when BOTH camera AND IMU agree the user is still.
        #    If IMU says walking but camera says still (e.g. featureless wall),
        #    the IMU wins — do not block distance accumulation.
        #    If BOTH say still, reset velocity.
        if self._cam is not None and self._cam.is_visually_still and self._imu.is_still:
            self._reset_velocity("BOTH-STILL-GATE: camera+IMU both still")
            return

        # 5. IMU step update — only on new confirmed steps
        now = time.monotonic()
        current_steps = self._imu.step_count
        if current_steps > self._last_step_count:
            imu_increment = self._imu.distance_m - self._last_imu_dist
            if imu_increment > 0.0:
                step_dt = (now - self._last_step_t) if self._last_step_t > 0 else dt
                step_dt = max(step_dt, dt)
                imu_speed = imu_increment / step_dt
                self._update(imu_speed, EKF_R_IMU, "IMU ")
            self._last_step_count = current_steps
            self._last_step_t     = now
        self._last_imu_dist = self._imu.distance_m

        # 6. Integrate velocity → 3-D pose
        delta_m     = self._v * dt
        heading_rad = math.radians(self._imu.heading)
        dx = delta_m * math.sin(heading_rad)
        dy = delta_m * math.cos(heading_rad)

        self._delta    = [dx, dy, 0.0]
        self._pose[0] += dx
        self._pose[1] += dy
        self._raw_dist_m += delta_m

        if delta_m > 0.001:
            debug_log.ekf_pose(delta_m, self._imu.heading, dx, dy, tuple(self._pose))

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def current_pose(self) -> tuple:
        return (self._pose[0], self._pose[1], self._pose[2])

    @property
    def pose_delta(self) -> tuple:
        return (self._delta[0], self._delta[1], self._delta[2])

    @property
    def fused_distance_m(self) -> float:
        return max(0.0, self._raw_dist_m)

    @property
    def fused_velocity_m_s(self) -> float:
        return max(0.0, self._v)

    @property
    def is_still(self) -> bool:
        return self._imu.is_still

    @property
    def motion_state(self) -> str:
        return self._imu.motion_state

    @property
    def step_count(self) -> int:
        return self._imu.step_count

    @property
    def heading(self) -> float:
        return self._imu.heading

    def reset(self) -> None:
        self._v               = 0.0
        self._P               = EKF_P0_VEL
        self._pose            = [0.0, 0.0, 0.0]
        self._delta           = [0.0, 0.0, 0.0]
        self._raw_dist_m      = 0.0
        self._last_step_count = self._imu.step_count
        self._last_imu_dist   = self._imu.distance_m
        self._last_step_t     = 0.0
        self._imu.reset()
        if self._cam is not None:
            self._cam.reset()
