"""
debug_graph.py  -  Indoor Navigation Graph Debugger
Prints every node, every edge, shortest paths, and duplicate edge warnings.

Usage:
    cd raspberry_pi
    python3 debug_graph.py
"""

import sys
import heapq

sys.path.insert(0, ".")
from indoor_nav import floor_map
from indoor_nav.path_planner import _build_graph

g = _build_graph(floor_map)
lbl = lambda n: floor_map.NODES.get(n, {}).get("label", n)


# ── 1. Full graph adjacency ────────────────────────────────────────────────────

def print_graph():
    print("=" * 64)
    print("FULL GRAPH ADJACENCY")
    print("=" * 64)
    for node in sorted(g):
        print(f"{lbl(node)} ({node})")
        for e in sorted(g[node], key=lambda x: x["distance"]):
            print(f"    -> {lbl(e['to'])} ({e['to']}) : {e['distance']}")
        print()


# ── 2. Dijkstra with step trace ────────────────────────────────────────────────

def dijkstra_steps(start, end):
    dist = {n: float("inf") for n in g}
    prev = {}
    dist[start] = 0.0
    heap = [(0.0, start)]
    while heap:
        cost, node = heapq.heappop(heap)
        if cost > dist[node]:
            continue
        for e in g.get(node, []):
            nc = cost + e["distance"]
            if nc < dist.get(e["to"], float("inf")):
                dist[e["to"]] = nc
                prev[e["to"]] = (node, e["distance"])
                heapq.heappush(heap, (nc, e["to"]))
    if dist.get(end, float("inf")) == float("inf"):
        return [], -1.0
    steps, cur = [], end
    while cur in prev:
        n, d = prev[cur]
        steps.append((n, cur, d))
        cur = n
    steps.reverse()
    return steps, dist[end]


def print_route(src, dst, expected=None):
    steps, total = dijkstra_steps(src, dst)
    tag = ""
    if expected is not None:
        tag = "  [OK]" if abs(total - expected) < 0.01 else f"  [FAIL  expected={expected}]"
    print(f"  {lbl(src)} -> {lbl(dst)}: {total:.4f} m{tag}")
    if not steps:
        print("    NO PATH FOUND")
    for a, b, d in steps:
        print(f"    {lbl(a)} -> {lbl(b)} : {d}")
    print()


def print_paths():
    print("=" * 64)
    print("SHORTEST PATH AUDIT")
    print("=" * 64)
    routes = [
        ("lounge",  "lh201", 13.325),
        ("lounge",  "lh202", None),
        ("lounge",  "lh203", None),
        ("lounge",  "lh204", None),
        ("lh201",   "lh202", 11.4595),
        ("lh202",   "lh203", 11.4595),
        ("lh203",   "lh204", 11.4595),
        ("lh201",   "lh205", None),
        ("lh201",   "l210",  None),
        ("lh204",   "lounge",None),
        ("lounge",  "lift",  None),
        ("l210",    "lh202", None),
    ]
    for src, dst, exp in routes:
        print_route(src, dst, exp)


# ── 3. Duplicate / asymmetric edge audit ──────────────────────────────────────

def print_edge_audit():
    print("=" * 64)
    print("DUPLICATE / ASYMMETRIC EDGE AUDIT")
    print("=" * 64)
    seen = {}
    for node in g:
        for e in g[node]:
            key = tuple(sorted([node, e["to"]]))
            seen.setdefault(key, []).append((node, e["to"], e["distance"]))

    warnings = 0
    for key, edges in seen.items():
        fwd = [e for e in edges if e[0] == key[0]]
        rev = [e for e in edges if e[0] == key[1]]
        if len(fwd) > 1:
            print(f"  WARNING duplicate fwd {key[0]}->{key[1]}: {[e[2] for e in fwd]}")
            warnings += 1
        if len(rev) > 1:
            print(f"  WARNING duplicate rev {key[1]}->{key[0]}: {[e[2] for e in rev]}")
            warnings += 1
        if fwd and rev and abs(fwd[0][2] - rev[0][2]) > 1e-9:
            print(f"  WARNING asymmetric {key[0]}<->{key[1]}: fwd={fwd[0][2]} rev={rev[0][2]}")
            warnings += 1

    if warnings == 0:
        print("  No issues found.")
    else:
        print(f"\n  {warnings} warning(s) total.")
    print()


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print_graph()
    print_paths()
    print_edge_audit()
