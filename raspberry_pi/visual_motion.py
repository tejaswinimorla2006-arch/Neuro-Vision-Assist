"""
visual_motion.py - Neuro Vision Assist
=======================================
Camera-based motion detection using sparse Lucas-Kanade optical flow.

Role after root-cause fix
--------------------------
This module is now a MOTION GATE only.  It no longer produces metric
displacement estimates.  The EKF reads is_visually_still to decide
whether to suppress velocity integration.

Reason: the camera is chest-mounted and forward-facing.  Optical flow
from forward motion produces radial expansion of the scene, not lateral
translation.  Multiplying mean radial flow by OF_M_PER_PX (a lateral-
motion factor) overestimates forward distance by 2-14x depending on
scene depth.  Distance is now provided solely by the IMU step detector.

What this module still does
----------------------------
- Tracks sparse corners with Lucas-Kanade.
- Classifies each frame as MOVING or STILL based on corrected flow magnitude.
- Exposes is_visually_still for the EKF motion gate.
- get_displacement() returns 0.0 always (kept for API compatibility).
"""

import cv2
import threading
import numpy as np

from config import (
    OF_SCALE, OF_MOTION_THRESH, OF_STILL_FRAMES,
    OF_GYRO_GATE_DEG_S, OF_MIN_CORNERS,
    NAV_POLL_S,
)
try:
    from config import OF_MOVING_FRAMES
except ImportError:
    OF_MOVING_FRAMES = 4
import debug_log

_nav_monitor = None

_CORNER_PARAMS = dict(
    maxCorners=150,        # increased from 100 for more robust tracking
    qualityLevel=0.01,
    minDistance=5,         # tighter packing for more features
    blockSize=7,
)

# Improved LK parameters: larger window + more pyramid levels
_LK_PARAMS = dict(
    winSize=(21, 21),      # was (15,15) — larger window tracks faster motion
    maxLevel=3,            # was 2 — extra pyramid level for large displacements
    criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 15, 0.03),
)

_FOCAL_PX_SCALED = 133.0   # focal length at 0.25x scale (160px wide)

# Redetect features when tracked count drops below this fraction of maxCorners
_REDETECT_FRAC = 0.4   # redetect when < 40% of max corners remain


class VisualMotion:

    def __init__(self):
        self._lock          = threading.Lock()
        self._prev_gray     = None
        self._prev_pts      = None
        self._still_count   = 0
        self._moving_count  = 0   # MOVING-side hysteresis counter
        self._is_still      = True
        self._last_t        = None

    def submit_frame(self, bgr_frame: np.ndarray, gz_deg_s: float = 0.0) -> None:
        import time
        now = time.monotonic()

        small = cv2.resize(bgr_frame, (0, 0), fx=OF_SCALE, fy=OF_SCALE,
                           interpolation=cv2.INTER_LINEAR)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

        with self._lock:
            dt = (now - self._last_t) if self._last_t is not None else NAV_POLL_S
            dt = max(dt, 1e-4)
            self._last_t = now

            # Gate 1: gyro shake rejection
            if abs(gz_deg_s) > OF_GYRO_GATE_DEG_S:
                debug_log.of_init(f"GYRO-GATE  gz={gz_deg_s:.1f}°/s > {OF_GYRO_GATE_DEG_S}  frame skipped")
                self._prev_gray    = gray
                self._prev_pts     = self._detect_corners(gray)
                self._still_count += 1
                self._moving_count = 0
                self._is_still = self._still_count >= OF_STILL_FRAMES
                return

            # Gate 2: need a previous frame with enough features
            n_prev = len(self._prev_pts) if self._prev_pts is not None else 0
            if self._prev_gray is None or n_prev < OF_MIN_CORNERS:
                debug_log.of_init("INIT  detecting corners...", n_prev)
                self._prev_gray = gray
                self._prev_pts  = self._detect_corners(gray)
                return

            # Optical flow
            next_pts, status, err = cv2.calcOpticalFlowPyrLK(
                self._prev_gray, gray, self._prev_pts, None, **_LK_PARAMS
            )

            if next_pts is None or status is None:
                debug_log.of_init("LK FAILED  redetecting")
                self._prev_gray = gray
                self._prev_pts  = self._detect_corners(gray)
                return

            good_mask = status.ravel() == 1
            good_prev = self._prev_pts[good_mask]
            good_next = next_pts[good_mask]
            n_good    = len(good_next)
            n_total   = len(self._prev_pts)

            if n_good < OF_MIN_CORNERS:
                debug_log.of_init(f"TOO FEW  good={n_good}/{n_total}  redetecting")
                self._prev_gray = gray
                self._prev_pts  = self._detect_corners(gray)
                return

            # Flow magnitude
            dx = good_next[:, 0, 0] - good_prev[:, 0, 0]
            dy = good_next[:, 0, 1] - good_prev[:, 0, 1]
            magnitudes = np.sqrt(dx * dx + dy * dy)
            mean_flow  = float(np.mean(magnitudes))

            # Rotation compensation
            gz_rad_s  = abs(gz_deg_s) * (3.14159265 / 180.0)
            rot_flow  = gz_rad_s * _FOCAL_PX_SCALED * dt
            corrected = max(0.0, mean_flow - rot_flow)

            # Use VERTICAL flow component as primary motion signal.
            # Forward-facing chest-mounted camera: floor features flow downward
            # during forward walking (radial expansion has a strong downward
            # component).  Pure lateral flow (dx) is near-zero for forward motion.
            mean_dy = float(np.mean(np.abs(dy)))

            # Rotation compensation on vertical component
            gz_rad_s_v = abs(gz_deg_s) * (3.14159265 / 180.0)
            rot_flow_v = gz_rad_s_v * _FOCAL_PX_SCALED * dt
            corrected_v = max(0.0, mean_dy - rot_flow_v)

            # Stillness classification with two-sided hysteresis.
            # STILL side: require OF_STILL_FRAMES consecutive below-threshold frames.
            # MOVING side: require OF_MOVING_FRAMES consecutive above-threshold frames
            #              before exiting STILL — prevents single noisy frames from
            #              prematurely releasing the EKF gate.
            if corrected_v < OF_MOTION_THRESH:
                self._still_count  += 1
                self._moving_count  = 0
                self._is_still = self._still_count >= OF_STILL_FRAMES
                debug_log.of_state_change("STILL", n_good, n_total,
                                          mean_flow, corrected_v, 0.0, 0.0, gz_deg_s)
            else:
                self._moving_count += 1
                self._still_count   = 0
                if self._moving_count >= OF_MOVING_FRAMES:
                    self._is_still = False
                debug_log.of_state_change("MOVING", n_good, n_total,
                                          mean_flow, corrected_v, 0.0, 0.0, gz_deg_s)

            # Redetect features when count drops below threshold
            redetect_thresh = int(_CORNER_PARAMS["maxCorners"] * _REDETECT_FRAC)
            if n_good < redetect_thresh:
                debug_log.of_low_features(n_good, n_total, "redetecting")
                self._prev_pts = self._detect_corners(gray)
            else:
                self._prev_pts = good_next.reshape(-1, 1, 2)
            self._prev_gray = gray

    def get_displacement(self) -> float:
        """Returns 0.0 — camera no longer provides metric displacement.
        Kept for API compatibility. Distance comes from IMU only."""
        return 0.0

    def reset(self) -> None:
        with self._lock:
            self._still_count  = 0
            self._moving_count = 0
            self._is_still     = True
            self._prev_gray    = None
            self._prev_pts     = None
            self._last_t       = None
            debug_log.of_reset()

    @property
    def is_visually_still(self) -> bool:
        with self._lock:
            return self._is_still

    @staticmethod
    def _detect_corners(gray: np.ndarray):
        pts = cv2.goodFeaturesToTrack(gray, mask=None, **_CORNER_PARAMS)
        n = len(pts) if pts is not None else 0
        debug_log.of_init("DETECT", n)
        return pts
