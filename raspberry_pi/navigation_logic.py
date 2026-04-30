"""
Module 4: Navigation Logic
Divides frame into Left / Center / Right zones.
Generates navigation instruction based on obstacle position.

Frame zones (normalized x):
  Left   : 0.0 - 0.33
  Center : 0.33 - 0.66
  Right  : 0.66 - 1.0

Decision:
  Center -> STOP
  Left   -> MOVE RIGHT
  Right  -> MOVE LEFT
"""

def get_zone(x_center_normalized):
    if x_center_normalized < 0.33:
        return "left"
    elif x_center_normalized < 0.66:
        return "center"
    else:
        return "right"

def generate_instruction(detections):
    """
    Args:
        detections: list of (label, x_center_normalized, confidence)
    Returns:
        instruction string or None if no obstacles
    """
    if not detections:
        return None

    # Pick the detection with highest confidence
    label, x_center, conf = max(detections, key=lambda d: d[2])
    zone = get_zone(x_center)

    if zone == "center":
        return f"{label} detected ahead, STOP"
    elif zone == "left":
        return f"{label} on left, MOVE RIGHT"
    else:
        return f"{label} on right, MOVE LEFT"


if __name__ == "__main__":
    # Quick test
    test_cases = [
        [("person", 0.2, 0.9)],   # Left
        [("chair", 0.5, 0.85)],   # Center
        [("bottle", 0.8, 0.7)],   # Right
        [],                        # No detection
    ]
    for case in test_cases:
        print(generate_instruction(case))
