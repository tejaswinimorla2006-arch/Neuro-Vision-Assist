"""
instruction_generator.py  –  Indoor Navigation, Neuro Vision Assist
Converts a node-id path into direction-only spoken instructions.

Instructions describe turns and landmarks only — no distances are spoken.
The user's actual progress is tracked by the IMU (StepDetector) in real time.

Example output
--------------
[
  "Walk straight ahead.",
  "Turn right and continue.",
  "Walk straight. Staff Room will be on your right.",
  "Turn left. LH-202 will be on your left.",
  "You have arrived at LH-202. The entrance is ahead of you."
]
"""

from indoor_nav.path_planner import get_edge


def _direction_phrase(direction: str, dist: float) -> str:
    d = f"{dist:.1f} metres" if dist >= 1.0 else f"{dist*100:.0f} centimetres"
    if direction == "left":
        return f"Turn left and walk {d}."
    if direction == "right":
        return f"Turn right and walk {d}."
    return f"Walk straight for {d}."


def generate_steps(floor_map, path: list[str]) -> list[str]:
    """
    Args
    ----
    floor_map : the floor_map module (floor_map.py or any future floor)
    path      : list of node_ids from start to destination

    Returns
    -------
    list of instruction strings.  Last element = arrival message.
    """
    if not path:
        return ["No route found."]

    nodes = floor_map.NODES

    if len(path) == 1:
        return [f"You are already at {nodes[path[0]]['label']}."]

    steps = []

    for i in range(len(path) - 1):
        src, dst  = path[i], path[i + 1]
        edge      = get_edge(floor_map, src, dst)
        dst_label = nodes[dst]["label"]

        if edge is None:
            steps.append(f"Proceed to {dst_label}.")
            continue

        dist      = edge["distance"]
        direction = edge["direction"]
        landmark  = edge.get("landmark", "")

        instr = _direction_phrase(direction, dist)

        # Append landmark hint if present
        if landmark:
            instr = instr.rstrip(".") + f". {landmark}."

        # On the last walking segment, tell the user where the destination is
        if i == len(path) - 2:
            side = {"left": "left", "right": "right"}.get(direction, "ahead")
            instr = instr.rstrip(".") + f". {dst_label} will be on your {side}."

        steps.append(instr)

    # Arrival message
    dest_label = nodes[path[-1]]["label"]
    dest_type  = nodes[path[-1]].get("type", "room")
    if dest_type in ("room", "lab"):
        arrival = f"You have arrived at {dest_label}. The entrance is ahead of you."
    elif dest_type == "staircase":
        arrival = f"You have reached the {dest_label}. The staircase is directly ahead."
    elif dest_type == "lift":
        arrival = f"You have reached the Lift. The lift doors are directly ahead."
    else:
        arrival = f"You have arrived at {dest_label}."

    steps.append(arrival)
    return steps


def route_preview(floor_map, path: list[str]) -> str:
    """
    Returns a formatted multi-line route preview string.
    Example:
        Navigation Route
        Student Lounge
        ↓  Walk 8.26 m
        ↓  Turn Left, Walk 10.13 m
        LH-202
    """
    if not path or len(path) < 2:
        return ""
    nodes  = floor_map.NODES
    lines  = ["Navigation Route:", f"  Start: {nodes[path[0]]['label']}", "  ─────────────────"]
    for i in range(len(path) - 1):
        edge = get_edge(floor_map, path[i], path[i + 1])
        if edge:
            d   = edge["distance"]
            dir = edge["direction"].capitalize()
            if dir == "Straight":
                lines.append(f"  ↓  Walk {d:.2f} m")
            else:
                lines.append(f"  ↓  Turn {dir}, Walk {d:.2f} m")
        else:
            lines.append(f"  ↓  Proceed")
    lines.append(f"  ─────────────────")
    lines.append(f"  End:   {nodes[path[-1]]['label']}")
    return "\n".join(lines)


def segment_distance(floor_map, path: list[str], step_index: int) -> float:
    """
    Return the walking distance for the segment at step_index.
    step_index 0 = first walking segment (path[0] → path[1]).
    """
    if step_index >= len(path) - 1:
        return 0.0
    edge = get_edge(floor_map, path[step_index], path[step_index + 1])
    return edge["distance"] if edge else 0.0
