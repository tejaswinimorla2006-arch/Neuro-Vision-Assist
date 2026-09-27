"""
navigation_monitor.py  –  Indoor Navigation, Neuro Vision Assist
=================================================================
Continuous pose-driven waypoint advancement.

Distance tracking architecture
-------------------------------
  SensorFusion.tick(dt)
      → produces current_pose (x, y, z) and pose_delta (dx, dy, dz)

  DistanceTracker.update(pose)
      → accumulates Euclidean distance with MIN_POSE_DISPLACEMENT threshold
      → is the ONLY writer of travelled_distance in the entire project

  NavigationMonitor reads tracker.travelled_distance
      → computes remaining = edge.length - travelled
      → advances waypoint when remaining <= WAYPOINT_TOLERANCE

Debug logging (printed every tick when moving)
----------------------------------------------
  [POSE]  x=0.142  y=1.830  z=0.000  inc=0.047m  travelled=2.640m  remaining=5.620m
  [EDGE]  Student Lounge → Junction at Lounge  target=8.26m

State machine
-------------
  ALIGN   – wait for movement or 5 s timeout; heading guidance active
  WALK    – normal walking; distance cues every PROGRESS_CUE_INTERVAL_M
  APPROACH – remaining <= APPROACHING_M; say "approaching"
  DONE    – segment complete; advance() called once
"""

import math
import threading
import time

import scene_manager
import debug_log
from config import (
    NAV_POLL_S,
    WAYPOINT_TOLERANCE,
    HEADING_ON_TRACK_DEG, HEADING_CORRECT_DEG,
    HEADING_CUE_INTERVAL, HEADING_HYSTERESIS_DEG,
    PROGRESS_CUE_INTERVAL_M, APPROACHING_M,
)
from step_detector import StepDetector
from visual_motion import VisualMotion
from sensor_fusion import SensorFusion
from distance_tracker import DistanceTracker

_S_ALIGN    = "aligning"
_S_WALK     = "walking"
_S_APPROACH = "approaching"
_S_DONE     = "done"

_ALIGN_TIMEOUT = 5.0


def _heading_error(actual: float, expected: float) -> float:
    return (actual - expected + 180) % 360 - 180


class NavigationMonitor:

    def __init__(self, imu_read_fn, state, advance_fn, speak_fn):
        self._imu_read = imu_read_fn
        self._state    = state
        self._advance  = advance_fn
        self._speak    = speak_fn

        self._thread  = None
        self._running = False

        _detector    = StepDetector()
        self._visual = VisualMotion()
        self._fusion = SensorFusion(_detector, self._visual)
        self._tracker = DistanceTracker()

        # Per-segment state
        self._seg_state:        str   = _S_ALIGN
        self._align_start:      float = 0.0
        self._last_cue_at_m:    float = 0.0
        self._approaching_said: bool  = False

        # Heading guidance state
        self._last_heading_cue:  float = 0.0
        self._last_cue_dir:      str   = ""
        self._heading_corrected: bool  = False

        # Latest gz — read by object_detector to pass to visual_motion
        self._current_gz:        float = 0.0
        self._imu_error_logged:  bool  = False

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        debug_log.nav_event("Monitor started — pose-based Euclidean distance tracking.")

    def stop(self) -> None:
        self._running = False

    def reset_segment(self) -> None:
        """Reset for a new segment. Called by controller at each waypoint."""
        self._fusion.reset()
        self._tracker.reset()
        self._seg_state         = _S_ALIGN
        self._align_start       = time.monotonic()
        self._last_cue_at_m     = 0.0
        self._approaching_said  = False
        self._last_heading_cue  = 0.0
        self._last_cue_dir      = ""
        self._heading_corrected = False
        self._imu_error_logged  = False
        debug_log.heading_reset()

    def submit_camera_frame(self, bgr_frame, gz_deg_s: float = 0.0) -> None:
        """Called from YOLO thread. Passes frame + gz to VisualMotion."""
        self._visual.submit_frame(bgr_frame, gz_deg_s)

    @property
    def walked_metres(self) -> float:
        """Authoritative travelled distance from DistanceTracker."""
        return self._tracker.travelled_distance

    @property
    def step_count(self) -> int:
        return self._fusion.step_count

    @property
    def imu_available(self) -> bool:
        return not self._imu_error_logged

    # ── Main loop ──────────────────────────────────────────────────────────────

    def _loop(self) -> None:
        from indoor_nav.navigation_state import NavState
        last_t = time.monotonic()

        while self._running:
            t_start = time.monotonic()
            dt = max(t_start - last_t, 1e-4)
            last_t = t_start

            s = self._state.state
            if s in (NavState.NAVIGATING, NavState.OBSTACLE_PAUSED):
                self._tick(dt, paused=(s == NavState.OBSTACLE_PAUSED))

            elapsed = time.monotonic() - t_start
            time.sleep(max(0.0, NAV_POLL_S - elapsed))

    def _tick(self, dt: float, paused: bool) -> None:
        # ── 1. Read IMU ────────────────────────────────────────────────────────
        try:
            ax, ay, az, gz = self._imu_read()
            self._current_gz = gz
            if self._imu_error_logged:
                debug_log.nav_event("IMU Sensor recovered.")
                self._imu_error_logged = False
        except Exception as exc:
            if not self._imu_error_logged:
                debug_log.nav_event(f"IMU Unavailable: {exc}")
                self._imu_error_logged = True
            return

        # ── 2. Feed IMU sample to step detector ────────────────────────────────
        self._fusion._imu.update(ax, ay, az, gz)

        # ── 3. EKF tick → updated pose ─────────────────────────────────────────
        self._fusion.tick(dt)

        # ── 4. Update DistanceTracker with new pose ────────────────────────────
        #       This is the ONLY place travelled_distance is written.
        pose      = self._fusion.current_pose
        increment = self._tracker.update(pose)

        # ── 5. Read navigation distances ───────────────────────────────────────
        travelled = self._tracker.travelled_distance
        target    = self._state._segment_dist
        remaining = max(0.0, target - travelled)

        # ── 6. Sync into NavigationState (for remaining_in_segment property) ───
        self._state.set_walked_dist(travelled)

        # ── 7. Debug log (only when a real increment was accepted) ─────────────
        if increment > 0.0:
            edge_label = self._current_edge_label()
            x, y, z    = pose
            debug_log.pose_log(x, y, z, increment, travelled, remaining)
            if edge_label:
                debug_log.edge_log(edge_label, target)

        # ── 8. Update shared scene ─────────────────────────────────────────────
        expected_hdg = self._get_edge_heading()
        scene_manager.update_motion(
            self._fusion.motion_state,
            travelled,
            target,
            nav_state        = self._seg_state,
            current_heading  = self._fusion.heading,
            expected_heading = expected_hdg,
        )

        # ── 9. While paused, do not advance or speak ───────────────────────────
        if paused:
            return

        # ── 10. State machine ──────────────────────────────────────────────────
        if self._seg_state == _S_ALIGN:
            self._run_align(travelled, target)
        elif self._seg_state == _S_WALK:
            self._run_walk(travelled, remaining, target)
        elif self._seg_state == _S_APPROACH:
            self._run_approach(remaining, travelled, target)

    # ── State handlers ─────────────────────────────────────────────────────────

    def _run_align(self, travelled: float, target: float) -> None:
        self._check_heading()
        moving  = not self._fusion.is_still
        timeout = (time.monotonic() - self._align_start) >= _ALIGN_TIMEOUT
        if moving or timeout:
            self._seg_state = _S_WALK
            debug_log.nav_event(f"Segment started. Target={target:.2f}m")

    def _run_walk(self, travelled: float, remaining: float, target: float) -> None:
        # Waypoint reached directly from WALK (short segments)
        if target > 0 and remaining <= WAYPOINT_TOLERANCE:
            self._seg_state = _S_DONE
            self._on_segment_complete(travelled, target)
            return

        # Transition to approach zone
        if target > 0 and remaining <= APPROACHING_M:
            self._seg_state = _S_APPROACH
            if not self._approaching_said:
                self._approaching_said = True
                self._speak(f"Approaching waypoint. {remaining:.1f} metres remaining.")
                debug_log.nav_event(f"Approaching. Travelled={travelled:.2f}m Remaining={remaining:.2f}m")
            return

        # Distance progress cue every PROGRESS_CUE_INTERVAL_M
        if (travelled - self._last_cue_at_m) >= PROGRESS_CUE_INTERVAL_M \
                and remaining > APPROACHING_M:
            self._last_cue_at_m = travelled
            self._speak(f"{remaining:.1f} metres remaining.")

        # Heading guidance while moving
        if not self._fusion.is_still:
            self._check_heading()

    def _run_approach(self, remaining: float, travelled: float, target: float) -> None:
        if remaining <= WAYPOINT_TOLERANCE:
            self._seg_state = _S_DONE
            self._on_segment_complete(travelled, target)

    # ── Heading guidance ───────────────────────────────────────────────────────

    def _check_heading(self) -> None:
        expected = self._get_edge_heading()
        if expected is None:
            return

        now     = time.monotonic()
        actual  = self._fusion.heading
        err     = _heading_error(actual, expected)
        abs_err = abs(err)

        if self._heading_corrected:
            if abs_err <= HEADING_ON_TRACK_DEG:
                self._heading_corrected = False
                self._last_cue_dir      = ""
            return

        if abs_err <= HEADING_ON_TRACK_DEG:
            return

        if now - self._last_heading_cue < HEADING_CUE_INTERVAL:
            return

        direction = "left" if err < 0 else "right"
        if direction == self._last_cue_dir and abs_err <= HEADING_CORRECT_DEG:
            return

        if abs_err <= HEADING_CORRECT_DEG:
            cue = f"Veer slightly {direction}."
        elif abs_err <= 90:
            cue = f"Turn {direction}."
        else:
            cue = "You are facing the wrong direction. Please turn around."

        self._speak(cue)
        self._last_heading_cue  = now
        self._last_cue_dir      = direction
        self._heading_corrected = True
        debug_log.heading_log(expected, actual, err, cue)

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _get_edge_heading(self):
        try:
            path = self._state._path
            idx  = self._state._step_index
            if idx + 1 >= len(path):
                return None
            from indoor_nav.path_planner import get_edge
            edge = get_edge(self._state._floor_map, path[idx], path[idx + 1])
            return edge["heading"] if edge and "heading" in edge else None
        except Exception:
            return None

    def _current_edge_label(self) -> str:
        try:
            path  = self._state._path
            idx   = self._state._step_index
            nodes = self._state._floor_map.NODES
            if idx + 1 < len(path):
                a = nodes[path[idx]]["label"]
                b = nodes[path[idx + 1]]["label"]
                return f"{a} → {b}"
        except Exception:
            pass
        return ""

    def _on_segment_complete(self, travelled: float, target: float) -> None:
        debug_log.nav_event(f"Waypoint reached. travelled={travelled:.2f}m target={target:.2f}m")
        with self._state._lock:
            self._state._walked_dist = self._state._segment_dist
        self.reset_segment()
        self._advance()
