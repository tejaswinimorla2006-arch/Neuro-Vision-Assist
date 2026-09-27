"""
navigator.py  –  Navigation, Neuro Vision Assist
=================================================
Converts a PathResult into a list of natural spoken instructions
ready for TTS output.

Example output
--------------
    Walk straight for 8.26 metres.
    You are passing the Student Lounge.
    Continue straight for 2.13 metres.
    You are passing the Department Library.
    Walk straight for 10.13 metres.
    You have arrived at LH-201.

Design
------
* Each walking segment produces one instruction string.
* Landmark hints are appended when present.
* The final instruction is always an arrival announcement.
* Direction changes produce "Turn left/right and walk..." phrasing.
* A route summary (total distance, hop count) is available separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing      import List

from navigation.graph    import NavGraph, Edge
from navigation.dijkstra import PathResult


# ── Instruction dataclass ─────────────────────────────────────────────────────

@dataclass
class Instruction:
    """A single spoken navigation instruction."""

    text:     str    # full spoken text
    distance: float  # metres for this segment (0 for arrival)
    node:     str    # destination node of this segment
    is_final: bool   # True for the arrival instruction

    def __str__(self) -> str:
        return self.text


# ── Navigator ─────────────────────────────────────────────────────────────────

class Navigator:
    """
    Converts a PathResult into spoken navigation instructions.

    Usage
    -----
    >>> from navigation.graph    import build_ise_floor2
    >>> from navigation.dijkstra import dijkstra
    >>> from navigation.navigator import Navigator
    >>>
    >>> graph  = build_ise_floor2()
    >>> result = dijkstra(graph, "Student Lounge", "LH-201")
    >>> nav    = Navigator(graph)
    >>> for instr in nav.generate(result):
    ...     print(instr)
    """

    def __init__(self, graph: NavGraph):
        self._graph = graph

    # ── Public API ────────────────────────────────────────────────────────────

    def generate(self, result: PathResult) -> List[Instruction]:
        """
        Convert a PathResult into a list of Instruction objects.

        Parameters
        ----------
        result : PathResult from dijkstra()

        Returns
        -------
        List[Instruction] — ready to pass to Speaker.speak_all()
        """
        if not result.found:
            return [Instruction(
                text="Sorry, I could not find a route to your destination.",
                distance=0.0, node="", is_final=True,
            )]

        if len(result.path) == 1:
            return [Instruction(
                text=f"You are already at {result.path[0]}.",
                distance=0.0, node=result.path[0], is_final=True,
            )]

        instructions: list[Instruction] = []

        for i, edge in enumerate(result.edges):
            src  = result.path[i]
            dst  = result.path[i + 1]
            last = (i == len(result.edges) - 1)

            text = self._segment_text(edge, dst, last)
            instructions.append(Instruction(
                text=text,
                distance=edge.distance,
                node=dst,
                is_final=last,
            ))

        return instructions

    def summary(self, result: PathResult) -> str:
        """
        Return a one-line route summary.

        Example: "Route: Student Lounge → LH-201  |  10.26 m  |  2 steps"
        """
        if not result.found:
            return "No route found."
        route = " → ".join(result.path)
        return (
            f"Route: {route}  |  "
            f"{result.total_distance:.2f} m  |  "
            f"{result.hop_count} step{'s' if result.hop_count != 1 else ''}"
        )

    def preview(self, result: PathResult) -> str:
        """
        Return a formatted multi-line route preview for console display.

        Example:
            ┌─ Navigation Route ──────────────────────────────┐
            │  Start : Student Lounge                         │
            │  ↓  Walk straight  8.26 m  (Student Lounge)    │
            │  ↓  Walk straight  2.13 m  (Dept Library)      │
            │  ↓  Walk straight 10.13 m  (LH-201)            │
            │  End   : LH-201                                 │
            └─────────────────────────────────────────────────┘
        """
        if not result.found or len(result.path) < 2:
            return "No route to display."

        lines = [
            "┌─ Navigation Route " + "─" * 40 + "┐",
            f"│  Start : {result.path[0]}",
        ]
        for i, edge in enumerate(result.edges):
            dst  = result.path[i + 1]
            turn = _turn_word(edge.direction)
            lines.append(
                f"│  ↓  {turn:<14} {edge.distance:6.2f} m  →  {dst}"
            )
        lines.append(f"│  End   : {result.path[-1]}")
        lines.append(f"│  Total : {result.total_distance:.2f} m")
        lines.append("└" + "─" * 59 + "┘")
        return "\n".join(lines)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _segment_text(self, edge: Edge, dst: str, is_last: bool) -> str:
        """Build the spoken text for one walking segment."""

        # Use custom instruction if provided on the edge
        if edge.instruction:
            text = edge.instruction
        else:
            text = _movement_phrase(edge.direction, edge.distance)

        # Append landmark hint for intermediate steps
        if edge.landmark and not is_last:
            text += f" You are passing {edge.landmark}."

        # Arrival announcement on the final segment
        if is_last:
            text += f" You have arrived at {dst}."

        return text


# ── Phrase helpers ────────────────────────────────────────────────────────────

def _movement_phrase(direction: str, distance: float) -> str:
    """
    Build the movement phrase for a segment.

    Examples
    --------
    straight → "Walk straight for 8.26 metres."
    left     → "Turn left and walk 2.93 metres."
    right    → "Turn right and walk 1.86 metres."
    """
    dist_str = f"{distance:.2f} metres"
    if direction == "straight":
        return f"Walk straight for {dist_str}."
    if direction == "left":
        return f"Turn left and walk {dist_str}."
    if direction == "right":
        return f"Turn right and walk {dist_str}."
    return f"Walk {dist_str}."


def _turn_word(direction: str) -> str:
    return {"straight": "Walk straight", "left": "Turn left", "right": "Turn right"}.get(
        direction, "Walk"
    )
