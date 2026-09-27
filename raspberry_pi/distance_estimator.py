"""
distance_estimator.py - Neuro Vision Assist
Estimates real-world distance in meters from YOLO bounding box proximity.

Uses a calibrated lookup table based on bounding box height ratio.
No depth sensor required — works purely from monocular camera.

Proximity bands (from config.py):
  close  : box_h / frame_h >= 0.35  → object is very near
  medium : box_h / frame_h >= 0.15  → object at walking distance
  far    : below 0.15               → object is distant

Calibration assumes average object sizes at known distances
(person ~1.7m tall, chair ~0.9m, bottle ~0.3m).
"""

# Distance range (min, max) in meters for each proximity band
# Confidence is used to interpolate within the range
_DISTANCE_TABLE = {
    "close":  (0.4, 1.2),
    "medium": (1.2, 3.5),
    "far":    (3.5, 8.0),
}

# Per-label size correction factors (larger objects appear closer)
_SIZE_FACTOR = {
    "person":       1.0,
    "car":          0.6,   # cars are large — appear closer than they are
    "bus":          0.5,
    "truck":        0.5,
    "bicycle":      0.9,
    "motorcycle":   0.85,
    "chair":        1.1,
    "dining table": 0.8,
    "couch":        0.75,
    "bed":          0.7,
    "bottle":       1.4,   # small — appears farther than it is
    "cup":          1.5,
    "cell phone":   1.6,
    "book":         1.4,
    "backpack":     1.1,
    "dog":          1.1,
    "cat":          1.3,
    "obstacle":     1.0,
}

_DEFAULT_FACTOR = 1.0


def estimate_distance(proximity: str, confidence: float, label: str = "") -> float:
    """
    Returns estimated distance in meters.

    Args:
        proximity  : "close" | "medium" | "far"
        confidence : YOLO confidence 0.0–1.0
        label      : object class name (optional, improves accuracy)

    Returns:
        float — estimated distance in meters, rounded to 1 decimal
    """
    low, high = _DISTANCE_TABLE.get(proximity, (1.0, 5.0))

    # Higher confidence → more certain about proximity → use midpoint
    # Lower confidence → could be farther → bias toward far end
    t = 0.5 + (confidence - 0.5) * 0.4   # maps conf 0.3–1.0 → t 0.42–0.7
    t = max(0.0, min(1.0, t))

    raw_dist = low + t * (high - low)

    # Apply per-label size correction
    factor = _SIZE_FACTOR.get(label.lower(), _DEFAULT_FACTOR)
    corrected = raw_dist * factor

    return round(max(0.3, corrected), 1)


def distance_to_words(meters: float) -> str:
    """Convert a distance in meters to a natural spoken phrase."""
    if meters < 0.6:
        return "less than half a meter"
    if meters < 1.0:
        return f"about {int(meters * 100)} centimeters"
    if meters < 2.0:
        return f"about {meters:.1f} meters"
    return f"approximately {round(meters)} meters"
