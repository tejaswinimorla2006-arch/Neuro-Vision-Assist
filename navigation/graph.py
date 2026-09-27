"""
graph.py - Weighted navigation graph for indoor navigation.

Each node is a location (room, staircase, etc.).
Each edge contains: distance, direction, landmark, instruction.

Designed to be extended with multiple floors and buildings.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Edge:
    """Represents a walkable path between two locations."""
    distance: float          # in meters
    direction: str           # e.g. "straight", "left", "right"
    landmark: str            # nearby landmark to orient the user
    instruction: str         # human-readable navigation instruction
    blocked: bool = False    # True if corridor is temporarily blocked


# Type alias for the full graph structuretell
Graph = dict[str, dict[str, Edge]]


def build_graph() -> Graph:
    """
    Build and return the weighted navigation graph for Floor 2.

    Returns:
        Graph: Bidirectional adjacency dict of Edge objects.
    """
    raw: dict[str, dict[str, dict]] = {
        "Lift": {
            "Student Lounge": {
                "distance": 8.2615,
                "direction": "straight",
                "landmark": "Lift",
                "instruction": "Walk straight from the Lift"
            },
            "Right Stair": {
                "distance": 5.0635,
                "direction": "right",
                "landmark": "Lift",
                "instruction": "Turn right from the Lift"
            }
        },
        "Student Lounge": {
            "Department Library": {
                "distance": 2.132,
                "direction": "straight",
                "landmark": "Student Lounge",
                "instruction": "Continue straight past the Student Lounge"
            }
        },
        "Department Library": {
            "LH-201": {
                "distance": 10.127,
                "direction": "straight",
                "landmark": "Department Library",
                "instruction": "Continue straight past the Department Library"
            }
        },
        "LH-201": {
            "LH-202": {
                "distance": 11.4595,
                "direction": "straight",
                "landmark": "LH-201",
                "instruction": "Continue straight past LH-201"
            }
        },
        "LH-202": {
            "LH-203": {
                "distance": 8.528,
                "direction": "straight",
                "landmark": "LH-202",
                "instruction": "Continue straight past LH-202"
            },
            "Staff Room": {
                "distance": 2.93,
                "direction": "right",
                "landmark": "LH-202",
                "instruction": "Turn right at LH-202"
            }
        },
        "LH-203": {
            "Staff Washroom": {
                "distance": 1.8645,
                "direction": "right",
                "landmark": "LH-203",
                "instruction": "Turn right at LH-203"
            },
            "LH-204": {
                "distance": 2.665,
                "direction": "straight",
                "landmark": "LH-203",
                "instruction": "Continue straight past LH-203"
            }
        },
        "LH-204": {
            "Middle Stair": {
                "distance": 13.5915,
                "direction": "straight",
                "landmark": "LH-204",
                "instruction": "Continue straight past LH-204"
            }
        },
        "Staff Washroom": {
            "LH-205": {
                "distance": 2.598,
                "direction": "straight",
                "landmark": "Staff Washroom",
                "instruction": "Continue straight past the Staff Washroom"
            }
        },
        "Middle Stair": {
            "LH-213": {
                "distance": 2.7316,
                "direction": "left",
                "landmark": "Middle Stair",
                "instruction": "Turn left at the Middle Stair"
            }
        },
        "LH-213": {
            "LH-212": {
                "distance": 5.99,
                "direction": "straight",
                "landmark": "LH-213",
                "instruction": "Continue straight past LH-213"
            },
            "LH-208": {
                "distance": 3.798,
                "direction": "right",
                "landmark": "LH-213",
                "instruction": "Turn right at LH-213"
            }
        },
        "LH-212": {
            "LH-214": {
                "distance": 6.775,
                "direction": "straight",
                "landmark": "LH-212",
                "instruction": "Continue straight past LH-212"
            }
        },
        "LH-214": {
            "Balcony": {
                "distance": 3.878,
                "direction": "straight",
                "landmark": "LH-214",
                "instruction": "Continue straight past LH-214"
            }
        },
        "Balcony": {
            "LH-210": {
                "distance": 14.7145,
                "direction": "straight",
                "landmark": "Balcony",
                "instruction": "Continue straight past the Balcony"
            }
        },
        "LH-208": {
            "LH-209": {
                "distance": 5.99,
                "direction": "straight",
                "landmark": "LH-208",
                "instruction": "Continue straight past LH-208"
            }
        },
        "LH-209": {
            "LH-207": {
                "distance": 2.398,
                "direction": "straight",
                "landmark": "LH-209",
                "instruction": "Continue straight past LH-209"
            }
        },
        "LH-207": {
            "LH-206": {
                "distance": 3.465,
                "direction": "straight",
                "landmark": "LH-207",
                "instruction": "Continue straight past LH-207"
            }
        },
        "LH-206": {
            "Washroom": {
                "distance": 2.665,
                "direction": "straight",
                "landmark": "LH-206",
                "instruction": "Continue straight past LH-206"
            }
        }
    }

    return _make_bidirectional(raw)


def _make_bidirectional(raw: dict[str, dict[str, dict]]) -> Graph:
    """Convert a one-directional raw dict into a bidirectional Edge graph."""
    graph: Graph = {}

    for src, neighbors in raw.items():
        graph.setdefault(src, {})
        for dst, attrs in neighbors.items():
            graph[src][dst] = Edge(**attrs)

            # Add reverse edge with mirrored direction
            graph.setdefault(dst, {})
            if src not in graph[dst]:
                reverse_direction = _reverse_direction(attrs["direction"])
                graph[dst][src] = Edge(
                    distance=attrs["distance"],
                    direction=reverse_direction,
                    landmark=dst,
                    instruction=f"{attrs['instruction']} (reverse)"
                )

    return graph


def _reverse_direction(direction: str) -> str:
    """Return the opposite of a given direction."""
    return {"left": "right", "right": "left"}.get(direction, direction)


def block_edge(graph: Graph, src: str, dst: str) -> None:
    """Mark an edge as blocked (e.g. corridor under maintenance)."""
    if src in graph and dst in graph[src]:
        graph[src][dst].blocked = True
    if dst in graph and src in graph[dst]:
        graph[dst][src].blocked = True


def unblock_edge(graph: Graph, src: str, dst: str) -> None:
    """Unblock a previously blocked edge."""
    if src in graph and dst in graph[src]:
        graph[src][dst].blocked = False
    if dst in graph and src in graph[dst]:
        graph[dst][src].blocked = False


def add_edge(graph: Graph, src: str, dst: str, edge: Edge) -> None:
    """Dynamically add a new bidirectional edge (e.g. new room added)."""
    graph.setdefault(src, {})[dst] = edge
    graph.setdefault(dst, {})[src] = Edge(
        distance=edge.distance,
        direction=_reverse_direction(edge.direction),
        landmark=dst,
        instruction=f"{edge.instruction} (reverse)"
    )
