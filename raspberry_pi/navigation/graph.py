"""
graph.py  –  Navigation Graph, Neuro Vision Assist
===================================================
Stores the weighted, bidirectional navigation graph for one floor.

Design decisions
----------------
* Each node is a plain string ID (e.g. "LH-202").
* Each edge is an Edge dataclass stored in a nested dict:
      graph["LH-202"]["LH-203"] = Edge(...)
* The graph is bidirectional: adding A→B automatically adds B→A
  with the direction flipped (left↔right, straight stays straight).
* Dynamic updates (block/unblock corridors, add rooms) are supported
  without restarting the system.

Extending to multiple floors / buildings
-----------------------------------------
Create a second NavGraph instance with a different floor_id.
The Navigator and Dijkstra modules accept any NavGraph — no changes needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing      import Dict, List, Optional


# ── Edge ──────────────────────────────────────────────────────────────────────

@dataclass
class Edge:
    """A single directed walking segment between two nodes."""

    distance:    float           # metres
    direction:   str             # "straight" | "left" | "right"
    landmark:    str = ""        # spoken landmark hint, e.g. "LH-202 on your left"
    instruction: str = ""        # override instruction; auto-generated if empty
    blocked:     bool = False    # True = temporarily impassable (obstacle / works)

    def __post_init__(self):
        if self.direction not in ("straight", "left", "right"):
            raise ValueError(
                f"direction must be 'straight', 'left', or 'right', got '{self.direction}'"
            )
        if self.distance < 0:
            raise ValueError(f"distance must be non-negative, got {self.distance}")


# ── NavGraph ──────────────────────────────────────────────────────────────────

_FLIP: Dict[str, str] = {"left": "right", "right": "left", "straight": "straight"}

# Type alias for the inner adjacency dict
_AdjDict = Dict[str, Edge]


class NavGraph:
    """
    Weighted bidirectional navigation graph for one floor.

    Usage
    -----
    >>> g = NavGraph(floor_id="ISE-2")
    >>> g.add_edge("LH-201", "LH-202", distance=11.4595, direction="straight",
    ...            landmark="LH-201 on your left")
    >>> g.block("LH-203", "LH-204")          # temporary obstacle
    >>> g.unblock("LH-203", "LH-204")        # obstacle cleared
    """

    def __init__(self, floor_id: str = "floor"):
        self.floor_id: str = floor_id
        # _adj[src][dst] = Edge
        self._adj: Dict[str, _AdjDict] = {}

    # ── Node helpers ──────────────────────────────────────────────────────────

    def add_node(self, node_id: str) -> None:
        """Ensure a node exists (idempotent)."""
        self._adj.setdefault(node_id, {})

    @property
    def nodes(self) -> List[str]:
        return list(self._adj.keys())

    # ── Edge helpers ──────────────────────────────────────────────────────────

    def add_edge(
        self,
        src: str,
        dst: str,
        distance: float,
        direction: str = "straight",
        landmark: str = "",
        instruction: str = "",
    ) -> None:
        """
        Add a bidirectional edge between src and dst.
        The reverse edge has its direction flipped (left↔right).
        """
        self.add_node(src)
        self.add_node(dst)

        fwd = Edge(distance=distance, direction=direction,
                   landmark=landmark, instruction=instruction)
        rev = Edge(distance=distance, direction=_FLIP[direction],
                   landmark=landmark, instruction=instruction)

        self._adj[src][dst] = fwd
        self._adj[dst][src] = rev

    def get_edge(self, src: str, dst: str) -> Optional[Edge]:
        """Return the Edge from src→dst, or None if it doesn't exist."""
        return self._adj.get(src, {}).get(dst)

    def neighbours(self, node: str) -> List[tuple[str, Edge]]:
        """Return [(neighbour_id, Edge), ...] for all unblocked neighbours."""
        return [
            (nb, edge)
            for nb, edge in self._adj.get(node, {}).items()
            if not edge.blocked
        ]

    # ── Dynamic updates ───────────────────────────────────────────────────────

    def block(self, src: str, dst: str) -> None:
        """Mark a corridor segment as temporarily impassable (both directions)."""
        for a, b in ((src, dst), (dst, src)):
            edge = self._adj.get(a, {}).get(b)
            if edge:
                edge.blocked = True

    def unblock(self, src: str, dst: str) -> None:
        """Clear a temporary block (both directions)."""
        for a, b in ((src, dst), (dst, src)):
            edge = self._adj.get(a, {}).get(b)
            if edge:
                edge.blocked = False

    def remove_edge(self, src: str, dst: str) -> None:
        """Permanently remove an edge (both directions)."""
        self._adj.get(src, {}).pop(dst, None)
        self._adj.get(dst, {}).pop(src, None)

    def remove_node(self, node_id: str) -> None:
        """Remove a node and all its edges."""
        self._adj.pop(node_id, None)
        for adj in self._adj.values():
            adj.pop(node_id, None)

    # ── Utility ───────────────────────────────────────────────────────────────

    def __contains__(self, node_id: str) -> bool:
        return node_id in self._adj

    def __repr__(self) -> str:
        n = len(self._adj)
        e = sum(len(v) for v in self._adj.values()) // 2
        return f"NavGraph(floor='{self.floor_id}', nodes={n}, edges={e})"


# ── ISE 2nd Floor graph factory ───────────────────────────────────────────────

def build_ise_floor2() -> NavGraph:
    """
    Build and return the ISE 2nd Floor navigation graph.

    All distances are measured walking distances between room entrances
    along the actual corridor path (not wall-to-wall room widths).

    To add a new room:
        g.add_edge("New Room", "Nearest Node", distance=X.XX,
                   direction="straight", landmark="...")
    """
    g = NavGraph(floor_id="ISE-Floor-2")

    # ── West end: Lift / Lounge / Library cluster ─────────────────────────────
    g.add_edge("Lift",               "Student Lounge",      distance=8.2615,
               direction="straight", landmark="Student Lounge ahead")

    g.add_edge("Student Lounge",     "Department Library",  distance=2.132,
               direction="straight", landmark="Department Library ahead")

    g.add_edge("Department Library", "LH-201",              distance=10.127,
               direction="straight", landmark="LH-201 on your left")

    # ── South corridor: Lecture Hall row ─────────────────────────────────────
    g.add_edge("LH-201", "LH-202",   distance=11.4595,
               direction="straight", landmark="LH-202 on your left")

    g.add_edge("LH-202", "LH-203",   distance=8.528,
               direction="straight", landmark="LH-203 on your left")

    g.add_edge("LH-203", "LH-204",   distance=2.665,
               direction="straight", landmark="LH-204 on your left")

    g.add_edge("LH-204", "Middle Stair", distance=13.5915,
               direction="straight", landmark="Middle Staircase ahead")

    # ── North corridor: Staff area ────────────────────────────────────────────
    g.add_edge("LH-202",        "Staff Room",      distance=2.93,
               direction="right",    landmark="Staff Room on your right")

    g.add_edge("LH-203",        "Staff Washroom",  distance=1.8645,
               direction="right",    landmark="Staff Washroom on your right")

    g.add_edge("Staff Washroom","LH-205",           distance=2.598,
               direction="straight", landmark="LH-205 ahead")

    # ── East end: Right Stair / Middle Stair cluster ──────────────────────────
    g.add_edge("Lift",          "Right Stair",     distance=5.0635,
               direction="straight", landmark="Right Staircase ahead")

    g.add_edge("Middle Stair",  "LH-213",          distance=2.7316,
               direction="straight", landmark="LH-213 on your left")

    # ── East wing: LH-213 row (south side) ───────────────────────────────────
    g.add_edge("LH-213", "LH-212",   distance=5.99,
               direction="straight", landmark="LH-212 on your left")

    g.add_edge("LH-212", "LH-214",   distance=6.775,
               direction="straight", landmark="LH-214 on your left")

    g.add_edge("LH-214", "Balcony",  distance=3.878,
               direction="straight", landmark="Balcony ahead")

    g.add_edge("Balcony", "LH-210",  distance=14.7145,
               direction="straight", landmark="LH-210 on your left")

    # ── East wing: LH-208 row (north side) ───────────────────────────────────
    g.add_edge("LH-213", "LH-208",   distance=3.798,
               direction="left",     landmark="LH-208 on your left")

    g.add_edge("LH-208", "LH-209",   distance=5.99,
               direction="straight", landmark="LH-209 on your left")

    g.add_edge("LH-209", "LH-207",   distance=2.398,
               direction="straight", landmark="LH-207 on your left")

    g.add_edge("LH-207", "LH-206",   distance=3.465,
               direction="straight", landmark="LH-206 on your left")

    g.add_edge("LH-206", "Washroom", distance=2.665,
               direction="straight", landmark="Washroom ahead")

    return g
