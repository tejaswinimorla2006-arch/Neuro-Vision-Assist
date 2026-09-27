"""
campus_graph.py
Loads campus_graph.json and exposes:
  - NODES  : {node_id: {label, type}}
  - GRAPH  : {node_id: [{to, distance, direction}]}
  - ALIASES: {alias_str: node_id}
  - resolve(name) -> node_id or None
"""

import json
import os

_JSON_PATH = os.path.join(os.path.dirname(__file__), "campus_graph.json")


def _load():
    with open(_JSON_PATH, "r") as f:
        data = json.load(f)

    nodes   = data["nodes"]
    aliases = {k.lower(): v for k, v in data["aliases"].items()}
    fence   = data["outdoor_gps_fence"]

    # Build bidirectional adjacency list
    graph = {nid: [] for nid in nodes}
    for edge in data["edges"]:
        src, dst = edge["from"], edge["to"]
        dist, direction = edge["distance"], edge["direction"]
        graph[src].append({"to": dst, "distance": dist, "direction": direction})
        # Reverse edge — direction is flipped
        reverse_dir = {"left": "right", "right": "left", "straight": "straight"}.get(direction, "straight")
        graph[dst].append({"to": src, "distance": dist, "direction": reverse_dir})

    return nodes, graph, aliases, fence


NODES, GRAPH, ALIASES, GPS_FENCE = _load()


def resolve(name: str) -> str | None:
    """
    Resolve a user-typed name to a node_id.
    Tries: exact node_id → exact label match → alias → partial label match.
    Returns None if no match found.
    """
    name_lower = name.strip().lower()

    # 1. Exact node_id
    if name_lower in NODES:
        return name_lower

    # 2. Exact label match
    for nid, meta in NODES.items():
        if meta["label"].lower() == name_lower:
            return nid

    # 3. Alias
    if name_lower in ALIASES:
        return ALIASES[name_lower]

    # 4. Partial label match (e.g. "block a" matches "Block A")
    for nid, meta in NODES.items():
        if name_lower in meta["label"].lower():
            return nid

    return None


def all_location_names() -> list[str]:
    """Return sorted list of all canonical location labels."""
    return sorted(meta["label"] for meta in NODES.values())
