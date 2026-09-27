"""
scene_manager.py - Neuro Vision Assist
Shared scene object continuously updated by YOLO and NavigationMonitor.
All other modules READ from this — zero camera impact.

Updated by : object_detector.py  (obstacle/path fields, after every inference)
             navigation_monitor.py (motion fields, at 50 Hz)
Read by    : vision_reasoner.py, chat_interface.py, chatbot.py, guidance.py
"""

import time
import threading

_lock = threading.Lock()

_scene = {
    "timestamp":           0.0,
    "objects":             [],
    "closest":             None,
    "path_clear":          True,
    "safe_direction":      "forward",   # "forward"|"left"|"right"|"stop"
    "blocked_zones":       set(),
    "walkable_meters":     None,
    # Motion / navigation state — updated by NavigationMonitor via update_motion()
    "user_state":          "still",     # "still"|"walking"|"running"|"shaking"
    "estimated_distance":  0.0,         # metres walked in current segment (fused)
    "navigation_progress": 0.0,         # 0.0–1.0 fraction of current segment
    "remaining_distance":  0.0,         # metres remaining in current segment
    "segment_distance":    0.0,         # total metres in current segment
    "navigation_state":    "idle",      # monitor sub-state string
    "current_heading":     0.0,         # degrees from IMU
    "expected_heading":    None,        # degrees from edge, or None
}


def update(detections: list, instruction: str) -> None:
    """
    Called by object_detector after every YOLO inference.
    Updates obstacle/path fields only.  Motion fields updated by update_motion().
    """
    from distance_estimator import estimate_distance

    objects = []
    for d in detections:
        dist = estimate_distance(d["proximity"], d["confidence"])
        pos  = _fine_position(d["x_center"])
        objects.append({
            "label":      d["label"],
            "position":   pos,
            "proximity":  d["proximity"],
            "distance_m": dist,
            "confidence": d["confidence"],
            "x_center":   d["x_center"],
        })

    objects.sort(key=lambda o: o["distance_m"])

    closest    = objects[0] if objects else None
    path_clear = not any(
        o["position"] == "center" and o["proximity"] != "far" for o in objects
    )

    blocked = set()
    for o in objects:
        if o["proximity"] != "far" or o["position"] == "center":
            zone = "left" if o["x_center"] < 0.33 else \
                   "right" if o["x_center"] > 0.66 else "center"
            blocked.add(zone)

    safe_dir = _safe_direction(blocked)
    walkable = _walkable_distance(objects)

    with _lock:
        _scene["timestamp"]       = time.time()
        _scene["objects"]         = objects
        _scene["closest"]         = closest
        _scene["path_clear"]      = path_clear
        _scene["safe_direction"]  = safe_dir
        _scene["blocked_zones"]   = blocked
        _scene["walkable_meters"] = walkable


def update_motion(user_state: str, estimated_distance: float, segment_dist: float,
                  nav_state: str = "idle", current_heading: float = 0.0,
                  expected_heading=None) -> None:
    """
    Called by NavigationMonitor at 50 Hz with fused motion data.

    user_state         : motion classifier output
    estimated_distance : metres walked in current segment (fused IMU + camera)
    segment_dist       : total metres in current segment (from floor map)
    nav_state          : monitor sub-state string
    current_heading    : current compass heading from IMU (degrees)
    expected_heading   : expected edge heading (degrees) or None
    """
    progress  = (estimated_distance / segment_dist) if segment_dist > 0 else 0.0
    remaining = max(0.0, segment_dist - estimated_distance)
    with _lock:
        _scene["user_state"]          = user_state
        _scene["estimated_distance"]  = round(estimated_distance, 2)
        _scene["navigation_progress"] = round(min(1.0, progress), 3)
        _scene["remaining_distance"]  = round(remaining, 2)
        _scene["segment_distance"]    = round(segment_dist, 2)
        _scene["navigation_state"]    = nav_state
        _scene["current_heading"]     = round(current_heading, 1)
        _scene["expected_heading"]    = expected_heading


def get() -> dict:
    """Return a snapshot of the current scene. Thread-safe."""
    with _lock:
        return {
            "timestamp":           _scene["timestamp"],
            "objects":             list(_scene["objects"]),
            "closest":             _scene["closest"],
            "path_clear":          _scene["path_clear"],
            "safe_direction":      _scene["safe_direction"],
            "blocked_zones":       set(_scene["blocked_zones"]),
            "walkable_meters":     _scene["walkable_meters"],
            "user_state":          _scene["user_state"],
            "estimated_distance":  _scene["estimated_distance"],
            "navigation_progress": _scene["navigation_progress"],
            "remaining_distance":  _scene["remaining_distance"],
            "segment_distance":    _scene["segment_distance"],
            "navigation_state":    _scene["navigation_state"],
            "current_heading":     _scene["current_heading"],
            "expected_heading":    _scene["expected_heading"],
        }


def is_fresh(max_age_seconds: float = 3.0) -> bool:
    """Returns True if scene was updated within max_age_seconds."""
    with _lock:
        return (time.time() - _scene["timestamp"]) < max_age_seconds


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fine_position(x: float) -> str:
    if x < 0.20:   return "far left"
    if x < 0.33:   return "left"
    if x < 0.45:   return "front left"
    if x <= 0.55:  return "center"
    if x <= 0.66:  return "front right"
    if x <= 0.80:  return "right"
    return "far right"


def _safe_direction(blocked: set) -> str:
    if not blocked:
        return "forward"
    if "center" in blocked:
        if "left" not in blocked:
            return "left"
        if "right" not in blocked:
            return "right"
        return "stop"
    if "left" in blocked and "right" not in blocked:
        return "right"
    if "right" in blocked and "left" not in blocked:
        return "left"
    return "forward"


def _walkable_distance(objects: list) -> float | None:
    center_objects = [
        o for o in objects
        if o["position"] in ("center", "front left", "front right")
    ]
    if not center_objects:
        return None
    nearest = min(center_objects, key=lambda o: o["distance_m"])
    return max(0.0, round(nearest["distance_m"] - 0.5, 1))
