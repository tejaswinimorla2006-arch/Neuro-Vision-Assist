"""
dijkstra.py  –  Navigation, Neuro Vision Assist
================================================
Dijkstra shortest-path algorithm on a NavGraph.

Returns a PathResult dataclass containing:
    path           : ordered list of node IDs from start to end
    total_distance : total walking distance in metres
    edges          : the Edge objects along the path (for instruction generation)

Blocked edges are automatically skipped.
Returns an empty PathResult if no route exists.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing      import List, Optional

from navigation.graph import NavGraph, Edge


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class PathResult:
    """Result of a Dijkstra shortest-path query."""

    path:           List[str]        # node IDs from start to end
    total_distance: float            # metres
    edges:          List[Edge]       # Edge objects along the path

    @property
    def found(self) -> bool:
        """True if a valid route was found."""
        return len(self.path) >= 1 and self.total_distance >= 0

    @property
    def hop_count(self) -> int:
        return max(0, len(self.path) - 1)

    def __repr__(self) -> str:
        if not self.found:
            return "PathResult(no route)"
        route = " → ".join(self.path)
        return f"PathResult({route}, {self.total_distance:.2f} m)"


# ── Empty sentinel ────────────────────────────────────────────────────────────

def _no_route() -> PathResult:
    return PathResult(path=[], total_distance=-1.0, edges=[])


# ── Dijkstra ──────────────────────────────────────────────────────────────────

def dijkstra(graph: NavGraph, start: str, end: str) -> PathResult:
    """
    Find the shortest walkable path from start to end using Dijkstra's algorithm.

    Parameters
    ----------
    graph : NavGraph
        The navigation graph to search.
    start : str
        Starting node ID.
    end : str
        Destination node ID.

    Returns
    -------
    PathResult
        Contains path, total_distance, and edges.
        PathResult.found is False if no route exists.

    Notes
    -----
    * Blocked edges are skipped automatically.
    * If start == end, returns a single-node path with distance 0.
    * Raises KeyError if start or end are not in the graph.
    """
    if start not in graph:
        raise KeyError(f"Start node '{start}' not found in graph.")
    if end not in graph:
        raise KeyError(f"End node '{end}' not found in graph.")

    if start == end:
        return PathResult(path=[start], total_distance=0.0, edges=[])

    # dist[node] = best known distance from start
    dist: dict[str, float] = {n: float("inf") for n in graph.nodes}
    dist[start] = 0.0

    # prev[node] = (previous_node, edge_used)
    prev: dict[str, tuple[str, Edge]] = {}

    # Min-heap: (cost, node)
    heap: list[tuple[float, str]] = [(0.0, start)]

    while heap:
        cost, node = heapq.heappop(heap)

        # Stale entry — skip
        if cost > dist[node]:
            continue

        # Reached destination
        if node == end:
            break

        for nb, edge in graph.neighbours(node):
            new_cost = cost + edge.distance
            if new_cost < dist[nb]:
                dist[nb] = new_cost
                prev[nb] = (node, edge)
                heapq.heappush(heap, (new_cost, nb))

    # No route found
    if dist[end] == float("inf"):
        return _no_route()

    # Reconstruct path and collect edges
    path:  list[str]  = []
    edges: list[Edge] = []
    cur = end

    while cur in prev:
        prev_node, edge = prev[cur]
        path.append(cur)
        edges.append(edge)
        cur = prev_node

    path.append(start)
    path.reverse()
    edges.reverse()

    return PathResult(
        path=path,
        total_distance=round(dist[end], 4),
        edges=edges,
    )


# ── Alternative routes ────────────────────────────────────────────────────────

def find_alternatives(
    graph: NavGraph,
    start: str,
    end: str,
    max_routes: int = 3,
    penalty_factor: float = 1.5,
) -> List[PathResult]:
    """
    Find up to max_routes alternative paths using edge-penalty re-routing.

    Each subsequent route penalises the edges used in the previous best route,
    forcing Dijkstra to explore different corridors.

    Parameters
    ----------
    graph          : NavGraph to search
    start          : starting node ID
    end            : destination node ID
    max_routes     : maximum number of alternatives to return
    penalty_factor : multiply edge distances on used path by this factor

    Returns
    -------
    List of PathResult, ordered shortest-first.
    The original edge distances are restored after the call.
    """
    results: list[PathResult] = []
    penalised: list[tuple[str, str, float]] = []  # (src, dst, original_dist)

    for _ in range(max_routes):
        result = dijkstra(graph, start, end)
        if not result.found:
            break

        # Avoid exact duplicate paths
        if any(r.path == result.path for r in results):
            break

        results.append(result)

        # Penalise edges on this path so next iteration finds a different route
        for i in range(len(result.path) - 1):
            src, dst = result.path[i], result.path[i + 1]
            edge_fwd = graph.get_edge(src, dst)
            edge_rev = graph.get_edge(dst, src)
            if edge_fwd and edge_rev:
                orig = edge_fwd.distance
                penalised.append((src, dst, orig))
                edge_fwd.distance *= penalty_factor
                edge_rev.distance *= penalty_factor

    # Restore original distances
    for src, dst, orig in penalised:
        e_fwd = graph.get_edge(src, dst)
        e_rev = graph.get_edge(dst, src)
        if e_fwd:
            e_fwd.distance = orig
        if e_rev:
            e_rev.distance = orig

    return results
