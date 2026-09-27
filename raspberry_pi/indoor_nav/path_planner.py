"""
path_planner.py  –  Indoor Navigation, Neuro Vision Assist
Dijkstra shortest-path on any floor graph.

Usage
-----
    from indoor_nav.path_planner import plan
    from indoor_nav import floor_map

    path, dist = plan(floor_map, "l210", "lh202")
    # path = ["l210", "jn_l210", "jn_l209", ...]
    # dist = total metres

To add a new floor: pass a different map module — no changes needed here.
"""

import heapq


def _build_graph(floor_map) -> dict:
    """
    Build bidirectional adjacency dict from a floor_map module's EDGES list.
    Returns {node_id: [{"to", "distance", "direction", "heading", "landmark"}, ...]}
    """
    graph = {nid: [] for nid in floor_map.NODES}

    _flip = {"left": "right", "right": "left", "straight": "straight"}

    for e in floor_map.EDGES:
        src, dst    = e["from"], e["to"]
        dist        = e["distance"]
        fwd_dir     = e["direction"]
        rev_dir     = _flip.get(fwd_dir, "straight")
        lm          = e.get("landmark", "")
        fwd_heading = e.get("heading", 0)
        rev_heading = (fwd_heading + 180) % 360

        graph.setdefault(src, []).append(
            {"to": dst, "distance": dist, "direction": fwd_dir,
             "heading": fwd_heading, "landmark": lm}
        )
        graph.setdefault(dst, []).append(
            {"to": src, "distance": dist, "direction": rev_dir,
             "heading": rev_heading, "landmark": lm}
        )

    return graph


def resolve(floor_map, name: str) -> str | None:
    """
    Resolve a spoken/typed name to a node_id.
    Order: exact node_id → exact label → alias → partial label.
    """
    n = name.strip().lower()

    if n in floor_map.NODES:
        return n

    for nid, meta in floor_map.NODES.items():
        if meta["label"].lower() == n:
            return nid

    if n in floor_map.ALIASES:
        return floor_map.ALIASES[n]

    for nid, meta in floor_map.NODES.items():
        if n in meta["label"].lower():
            return nid

    return None


def plan(floor_map, start: str, end: str) -> tuple[list[str], float]:
    """
    Dijkstra shortest path.

    Returns
    -------
    (path, total_distance)
        path            : list of node_ids start→end
        total_distance  : float metres
    Returns ([], -1) if unreachable.
    """
    if start == end:
        return [start], 0.0

    graph = _build_graph(floor_map)

    dist = {n: float("inf") for n in graph}
    prev = {}
    dist[start] = 0.0
    heap = [(0.0, start)]

    while heap:
        cost, node = heapq.heappop(heap)
        if cost > dist[node]:
            continue
        if node == end:
            break
        for edge in graph.get(node, []):
            nb       = edge["to"]
            new_cost = cost + edge["distance"]
            if new_cost < dist.get(nb, float("inf")):
                dist[nb] = new_cost
                prev[nb] = node
                heapq.heappush(heap, (new_cost, nb))

    if dist.get(end, float("inf")) == float("inf"):
        return [], -1.0

    path, cur = [], end
    while cur in prev:
        path.append(cur)
        cur = prev[cur]
    path.append(start)
    path.reverse()

    return path, round(dist[end], 4)


def get_edge(floor_map, src: str, dst: str) -> dict | None:
    """Return the edge dict between two adjacent nodes, or None."""
    graph = _build_graph(floor_map)
    for e in graph.get(src, []):
        if e["to"] == dst:
            return e
    return None
