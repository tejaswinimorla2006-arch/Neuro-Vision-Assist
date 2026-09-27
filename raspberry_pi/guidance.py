"""
guidance.py - Neuro Vision Assist
Real-time directional guidance for visually impaired users.

Analyses the latest YOLO detections, divides the frame into LEFT/CENTER/RIGHT
zones, scores each zone by obstruction, and returns actionable spoken guidance.

Public API
----------
describe_scene(scene)        -> str   rich natural language scene description
is_path_clear(scene)         -> str   safety answer with walkable distance
find_best_direction(scene)   -> str   "left" | "right" | "forward" | "turn_around"
generate_guidance(scene)     -> str   full spoken guidance paragraph
generate_scene_description(scene) -> str  alias for describe_scene
"""

from distance_estimator import distance_to_words

# Zone x-boundaries (normalised 0-1)
_LEFT_MAX   = 0.33
_RIGHT_MIN  = 0.66

# Proximity weights for obstruction scoring (higher = more blocking)
_PROX_WEIGHT = {"close": 1.0, "medium": 0.5, "far": 0.15}

# Approximate turn angles based on how blocked the preferred zone is
_TURN_ANGLES = {
    "left":  {0: "slightly left", 1: "left about 30 degrees", 2: "left about 45 degrees"},
    "right": {0: "slightly right", 1: "right about 30 degrees", 2: "right about 45 degrees"},
}


# ── Zone helpers ───────────────────────────────────────────────────────────────

def _zone(x_center: float) -> str:
    if x_center < _LEFT_MAX:
        return "left"
    if x_center > _RIGHT_MIN:
        return "right"
    return "center"


def _zone_score(objects: list, zone: str) -> float:
    """
    Obstruction score for a zone.
    Higher score = more blocked.
    Score is weighted sum of (proximity_weight / distance_m) for each object in zone.
    """
    score = 0.0
    for o in objects:
        if _zone(o["x_center"]) == zone:
            w = _PROX_WEIGHT.get(o["proximity"], 0.1)
            score += w / max(o["distance_m"], 0.3)
    return score


def _zone_nearest(objects: list, zone: str):
    """Return the nearest object in a zone, or None."""
    zoned = [o for o in objects if _zone(o["x_center"]) == zone]
    return min(zoned, key=lambda o: o["distance_m"]) if zoned else None


def _turn_angle_str(direction: str, center_score: float) -> str:
    """Map center obstruction score to a turn angle description."""
    if center_score < 0.5:
        level = 0
    elif center_score < 1.5:
        level = 1
    else:
        level = 2
    return _TURN_ANGLES.get(direction, {}).get(level, direction)


# ── Core algorithm ─────────────────────────────────────────────────────────────

def find_best_direction(scene: dict) -> str:
    """
    Evaluate LEFT / CENTER / RIGHT zones and return the safest direction.
    Returns: "forward" | "left" | "right" | "turn_around"
    """
    objects = scene.get("objects", [])
    if not objects:
        return "forward"

    scores = {
        "left":   _zone_score(objects, "left"),
        "center": _zone_score(objects, "center"),
        "right":  _zone_score(objects, "right"),
    }

    # Forward is safe if center score is low
    if scores["center"] < 0.3:
        return "forward"

    # Pick the least obstructed side
    if scores["left"] <= scores["right"]:
        best = "left"
    else:
        best = "right"

    # If even the best side is heavily blocked, turn around
    if scores[best] > 1.5 and scores["center"] > 1.5:
        return "turn_around"

    return best


# ── Natural language generators ────────────────────────────────────────────────

def describe_scene(scene: dict) -> str:
    """
    Rich natural language description of everything visible.
    Example: "There is a chair about 80 centimetres ahead slightly to your right.
              A person is walking about 2 metres to your left."
    """
    objects = scene.get("objects", [])
    if not objects:
        return "The path ahead is completely clear. I don't see any obstacles."

    lines = []
    seen = {}

    for o in objects:
        lbl  = o["label"]
        dist = distance_to_words(o["distance_m"])
        pos  = o["position"]

        seen[lbl] = seen.get(lbl, 0) + 1
        total = sum(1 for x in objects if x["label"] == lbl)

        if seen[lbl] == 1:
            article = f"{total}" if total > 1 else "a"
            noun    = f"{lbl}s" if total > 1 else lbl
            lines.append(f"There is {article} {noun} {dist} to your {pos}.")

    return " ".join(lines)


# Alias
generate_scene_description = describe_scene


def is_path_clear(scene: dict) -> str:
    """
    Safety answer with walkable distance and recommended action.
    """
    objects  = scene.get("objects", [])
    walkable = scene.get("walkable_meters")
    direction = find_best_direction(scene)

    if direction == "forward":
        if walkable:
            return (f"The next {walkable} metres ahead appear clear. "
                    "You may continue walking.")
        return "The path ahead is clear. You may continue walking."

    # Build a description of what is blocking
    center_objs = [o for o in objects if _zone(o["x_center"]) == "center"]
    if center_objs:
        nearest = center_objs[0]
        dist    = distance_to_words(nearest["distance_m"])
        block_str = f"There is a {nearest['label']} {dist} directly ahead."
    else:
        block_str = "There is an obstacle ahead."

    if direction == "turn_around":
        return (f"{block_str} "
                "All directions appear blocked. "
                "Turn around slowly and scan again.")

    angle = _turn_angle_str(direction, _zone_score(objects, "center"))
    return (f"No. {block_str} "
            f"Move {angle}.")


def generate_guidance(scene: dict) -> str:
    """
    Full spoken guidance: analyse all three zones, describe what is blocking,
    and give a precise directional instruction.
    """
    objects = scene.get("objects", [])
    direction = find_best_direction(scene)

    scores = {
        "left":   _zone_score(objects, "left"),
        "center": _zone_score(objects, "center"),
        "right":  _zone_score(objects, "right"),
    }

    # ── All clear ─────────────────────────────────────────────────────────────
    if direction == "forward":
        walkable = scene.get("walkable_meters")
        if walkable:
            return (f"The path is clear for about {walkable} metres. "
                    "Keep facing forward.")
        return "The path ahead is clear. Keep facing forward."

    # ── Turn around ───────────────────────────────────────────────────────────
    if direction == "turn_around":
        parts = []
        for zone in ("left", "center", "right"):
            nearest = _zone_nearest(objects, zone)
            if nearest:
                parts.append(
                    f"a {nearest['label']} {distance_to_words(nearest['distance_m'])} "
                    f"on your {zone}"
                )
        block_desc = (", ".join(parts) + ". ") if parts else ""
        return (f"All directions ahead appear blocked. "
                f"{block_desc}"
                "Turn around slowly and scan again.")

    # ── Directional guidance ──────────────────────────────────────────────────
    lines = []

    # Describe what is blocking center
    center_nearest = _zone_nearest(objects, "center")
    if center_nearest:
        dist = distance_to_words(center_nearest["distance_m"])
        lines.append(
            f"There is a {center_nearest['label']} {dist} directly ahead."
        )

    # Describe what is on the blocked side (opposite of recommended)
    blocked_side = "right" if direction == "left" else "left"
    blocked_nearest = _zone_nearest(objects, blocked_side)
    if blocked_nearest and scores[blocked_side] > 0.2:
        dist = distance_to_words(blocked_nearest["distance_m"])
        lines.append(
            f"The {blocked_side} side has a {blocked_nearest['label']} "
            f"{dist}."
        )

    # Confirm the recommended side is clear
    free_nearest = _zone_nearest(objects, direction)
    if not free_nearest or free_nearest["distance_m"] > 2.0:
        lines.append(f"The {direction} side is clear.")

    # Give the turn instruction
    angle = _turn_angle_str(direction, scores["center"])
    lines.append(f"Turn {angle}.")

    return " ".join(lines)
