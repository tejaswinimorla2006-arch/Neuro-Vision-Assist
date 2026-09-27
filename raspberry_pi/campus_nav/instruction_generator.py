"""
instruction_generator.py
Converts a node-id path into a list of natural spoken navigation steps.

Each step is a plain string ready for TTS or terminal print.

Example output:
  ["Start at Reception.",
   "Walk straight for 15 meters to Admin Office.",
   "Turn left. Walk 20 meters to Block A.",
   "Turn right. Walk 10 meters to Lift.",
   "You have arrived at Lift."]
"""

from campus_nav.campus_graph import GRAPH, NODES


def _edge_between(src: str, dst: str) -> dict | None:
    for edge in GRAPH.get(src, []):
        if edge["to"] == dst:
            return edge
    return None


def generate_steps(path: list[str]) -> list[str]:
    """
    Args:
        path: list of node_ids e.g. ["reception", "block_a", "library"]
    Returns:
        list of instruction strings
    """
    if not path:
        return ["No route found."]

    if len(path) == 1:
        return [f"You are already at {NODES[path[0]]['label']}."]

    steps = [f"Starting navigation from {NODES[path[0]]['label']}."]

    for i in range(len(path) - 1):
        src, dst  = path[i], path[i + 1]
        edge      = _edge_between(src, dst)
        dst_label = NODES[dst]["label"]

        if edge is None:
            steps.append(f"Proceed to {dst_label}.")
            continue

        dist      = edge["distance"]
        direction = edge["direction"]

        if direction == "straight":
            steps.append(f"Walk straight for {dist} meters to {dst_label}.")
        elif direction == "left":
            steps.append(f"Turn left. Walk {dist} meters to {dst_label}.")
        elif direction == "right":
            steps.append(f"Turn right. Walk {dist} meters to {dst_label}.")
        else:
            steps.append(f"Proceed {dist} meters to {dst_label}.")

    steps.append(f"You have arrived at {NODES[path[-1]]['label']}.")
    return steps
