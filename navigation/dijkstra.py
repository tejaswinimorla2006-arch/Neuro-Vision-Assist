"""
dijkstra.py - Shortest path finder using Dijkstra's algorithm.

Skips blocked edges automatically.
Returns the shortest path and total distance.
"""

import heapq
from dataclasses import dataclass
from typing import Optional

from navigation.graph import Graph


@dataclass
class PathResult:
    """Result of a shortest-path query."""
    path: list[str]           # ordered list of node names
    total_distance: float     # total distance in meters
    found: bool               # False if no path exists


def dijkstra(graph: Graph, start: str, end: str) -> PathResult:
    """
    Find the shortest path between two nodes using Dijkstra's algorithm.

    Args:
        graph: The navigation graph.
        start: Starting location name.
        end:   Destination location name.

    Returns:
        PathResult with path, total_distance, and found flag.
    """
    if start not in graph:
        raise ValueError(f"Start node '{start}' not in graph.")
    if end not in graph:
        raise ValueError(f"End node '{end}' not in graph.")

    # Min-heap: (cumulative_distance, current_node)
    heap: list[tuple[float, str]] = [(0.0, start)]
    dist: dict[str, float] = {start: 0.0}
    prev: dict[str, Optional[str]] = {start: None}

    while heap:
        current_dist, current = heapq.heappop(heap)

        if current == end:
            break

        # Skip stale heap entries
        if current_dist > dist.get(current, float("inf")):
            continue

        for neighbor, edge in graph[current].items():
            if edge.blocked:
                continue

            new_dist = current_dist + edge.distance
            if new_dist < dist.get(neighbor, float("inf")):
                dist[neighbor] = new_dist
                prev[neighbor] = current
                heapq.heappush(heap, (new_dist, neighbor))

    if end not in dist:
        return PathResult(path=[], total_distance=0.0, found=False)

    return PathResult(
        path=_reconstruct_path(prev, start, end),
        total_distance=round(dist[end], 4),
        found=True
    )


def _reconstruct_path(prev: dict[str, Optional[str]], start: str, end: str) -> list[str]:
    """Trace back through the prev map to build the ordered path."""
    path: list[str] = []
    node: Optional[str] = end
    while node is not None:
        path.append(node)
        node = prev.get(node)
    path.reverse()
    return path
