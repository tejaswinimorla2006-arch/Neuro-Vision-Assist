"""
distance_tracker.py - Neuro Vision Assist
==========================================
Accumulates travelled distance from consecutive 3-D pose estimates.

Why Euclidean pose-based accumulation
--------------------------------------
The previous approach fed per-tick displacement deltas directly into the
EKF as position measurements.  Because the EKF state was cumulative
position but the measurements were tiny deltas, the innovation was always
large and negative, causing the filter to fight its own prediction.

This module decouples distance accumulation from the EKF entirely:

  1. SensorFusion produces a pose (x, y, z) each tick.
  2. DistanceTracker computes the Euclidean step between consecutive poses.
  3. Steps below MIN_POSE_DISPLACEMENT are discarded (noise rejection).
  4. Valid steps are summed into travelled_distance.

This is the ONLY location in the project that writes to travelled_distance.
NavigationMonitor reads it and computes remaining = edge.length - travelled.

Noise rejection
---------------
Even when the user is stationary, optical flow and IMU integration produce
small random pose jitter (~1–5 mm per tick).  At 50 Hz this accumulates to
~0.15 m/min of phantom distance.  The MIN_POSE_DISPLACEMENT threshold
(default 3 cm) eliminates this: a 3 cm step at 1.2 m/s walking speed
occurs every 25 ms, which is above the 20 ms tick rate, so real steps
are never filtered out.

Public API
----------
  DistanceTracker()
    .update(pose: tuple)     → float   last accepted increment (0 if rejected)
    .get_distance()          → float   total travelled_distance
    .reset()
    .travelled_distance      → float   property alias for get_distance()
    .current_pose            → tuple   last accepted pose (x, y, z)
    .last_increment          → float   last accepted step distance
"""

import math
from config import MIN_POSE_DISPLACEMENT
import debug_log


class DistanceTracker:
    """
    Accumulates Euclidean distance between consecutive 3-D pose estimates.
    Thread-safe: all state is written only from NavigationMonitor's loop thread.
    """

    def __init__(self):
        self._prev_pose:       tuple = (0.0, 0.0, 0.0)
        self._current_pose:    tuple = (0.0, 0.0, 0.0)
        self._travelled:       float = 0.0
        self._last_increment:  float = 0.0

    def update(self, pose: tuple) -> float:
        """
        Feed the latest (x, y, z) pose from SensorFusion.

        Returns the accepted increment in metres (0.0 if below threshold).

        Parameters
        ----------
        pose : (x, y, z) in metres from segment start
        """
        px, py, pz = self._prev_pose
        cx, cy, cz = pose

        dx = cx - px
        dy = cy - py
        dz = cz - pz
        step = math.sqrt(dx*dx + dy*dy + dz*dz)

        if step < MIN_POSE_DISPLACEMENT:
            # Jitter — do not accumulate, do not update prev_pose
            self._last_increment = 0.0
            return 0.0

        self._travelled      += step
        self._last_increment  = step
        self._prev_pose       = pose
        self._current_pose    = pose

        debug_log.dist_progress(cx, cy, cz, step, self._travelled)
        return step

    def get_distance(self) -> float:
        """Total accumulated travelled distance in metres."""
        return self._travelled

    def reset(self) -> None:
        """Reset for a new navigation segment."""
        self._prev_pose      = (0.0, 0.0, 0.0)
        self._current_pose   = (0.0, 0.0, 0.0)
        self._travelled      = 0.0
        self._last_increment = 0.0
        debug_log.dist_reset()

    @property
    def travelled_distance(self) -> float:
        return self._travelled

    @property
    def current_pose(self) -> tuple:
        return self._current_pose

    @property
    def last_increment(self) -> float:
        return self._last_increment
