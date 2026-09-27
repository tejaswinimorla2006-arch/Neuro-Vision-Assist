"""
dijkstra.py
Dijkstra's shortest path on the campus graph.

Usage:
    from campus_nav.dijkstra import shortest_path
    path, total_dist = shortest_path("reception", "library")
    # path = ["reception", "block_a", "library"]  total_dist = 60
"""

import heapq
from campus_nav.campus_graph import GRAPH


def shortest_path(start: str, end: str) -> tuple[list[str], int]:
    """
    Returns (path, total_distance).
    path is a list of node_ids from start to end.
    Returns ([], -1) if no path exists.
    """
    if start == end:
        return [start], 0

    # dist[node] = best known distance from start
    dist    = {node: float("inf") for node in GRAPH}
    prev    = {}
    dist[start] = 0
    heap    = [(0, start)]   # (cost, node_id)

    while heap:
        cost, node = heapq.heappop(heap)

        if cost > dist[node]:
            continue

        if node == end:
            break

        for edge in GRAPH.get(node, []):
            neighbour = edge["to"]
            new_cost  = cost + edge["distance"]
            if new_cost < dist[neighbour]:
                dist[neighbour] = new_cost
                prev[neighbour] = node
                heapq.heappush(heap, (new_cost, neighbour))

    if dist[end] == float("inf"):
        return [], -1

    # Reconstruct path
    path, cursor = [], end
    while cursor in prev:
        path.append(cursor)
        cursor = prev[cursor]
    path.append(start)
    path.reverse()

    return path, dist[end]
