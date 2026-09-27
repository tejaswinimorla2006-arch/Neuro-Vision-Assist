"""
navigation_logic.py - Neuro Vision Assist
Analyses ALL stable detections to find the clearest path and speak it.
"""

_PASSABLE = {"door"}
_PRIORITY = {"close": 0, "medium": 1, "far": 2}


def _lbl(d):
    """Return 'Person (87%)' style label with confidence."""
    pct = int(round(d["confidence"] * 100))
    return f"{d['label'].capitalize()} ({pct}%)"


def _zone(x: float) -> str:
    if x < 0.33:  return "left"
    if x <= 0.66: return "center"
    return "right"


def _blocked_zones(detections):
    """Return set of zones that have a non-passable obstacle."""
    blocked = set()
    for d in detections:
        if d["label"] in _PASSABLE:
            continue
        z = _zone(d["x_center"])
        # far objects on sides are not a real block
        if d["proximity"] == "far" and z != "center":
            continue
        blocked.add(z)
    return blocked


def _worst_in_zone(detections, zone):
    """Return the highest-priority (closest, most confident) detection in a zone."""
    candidates = [d for d in detections if _zone(d["x_center"]) == zone
                  and d["label"] not in _PASSABLE]
    if not candidates:
        return None
    return sorted(candidates, key=lambda d: (_PRIORITY[d["proximity"]], -d["confidence"]))[0]


def generate_instruction(detections, tilt_alert=False):
    if tilt_alert:
        return "Warning. Please adjust the device position."

    if not detections:
        return "Path is clear. Continue straight."

    blocked = _blocked_zones(detections)

    if not blocked:
        return "Path is clear. Continue straight."

    center_blocked = "center" in blocked
    left_blocked   = "left"   in blocked
    right_blocked  = "right"  in blocked

    # ── All three zones blocked ──────────────────────────────────────────────
    if center_blocked and left_blocked and right_blocked:
        top = _worst_in_zone(detections, "center")
        label = _lbl(top) if top else "Obstacle"
        return f"{label} blocking all sides. Stop and wait."

    # ── Center blocked — guide to clearest side ──────────────────────────────
    if center_blocked:
        top = _worst_in_zone(detections, "center")
        label = _lbl(top) if top else "Obstacle"
        prox  = top["proximity"] if top else "medium"

        if not left_blocked and not right_blocked:
            return f"{label} directly ahead. Move left or right to avoid."
        elif not right_blocked:
            return f"{label} ahead. Move right, path is clear on the right."
        elif not left_blocked:
            return f"{label} ahead. Move left, path is clear on the left."

    # ── Center clear — warn about sides ─────────────────────────────────────
    if not center_blocked:
        if left_blocked and not right_blocked:
            top = _worst_in_zone(detections, "left")
            label = _lbl(top) if top else "Obstacle"
            prox  = top["proximity"] if top else "medium"
            if prox == "close":
                return f"{label} very close on your left. Move right."
            return f"{label} on your left. Keep right."

        if right_blocked and not left_blocked:
            top = _worst_in_zone(detections, "right")
            label = _lbl(top) if top else "Obstacle"
            prox  = top["proximity"] if top else "medium"
            if prox == "close":
                return f"{label} very close on your right. Move left."
            return f"{label} on your right. Keep left."

        if left_blocked and right_blocked:
            return "Obstacles on both sides. Continue straight carefully."

    return "Path is clear. Continue straight."
