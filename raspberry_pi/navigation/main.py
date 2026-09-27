"""
main.py  –  Navigation, Neuro Vision Assist
============================================
Example entry point demonstrating the full navigation pipeline:

    graph  →  dijkstra  →  navigator  →  speaker

Run from the raspberry_pi/ directory:
    python3 -m navigation.main
or:
    cd raspberry_pi && python3 navigation/main.py
"""

from __future__ import annotations

from navigation.graph     import build_ise_floor2
from navigation.dijkstra  import dijkstra, find_alternatives
from navigation.navigator import Navigator
from navigation.speech    import Speaker


def run_demo():
    # ── 1. Build graph ────────────────────────────────────────────────────────
    graph = build_ise_floor2()
    print(graph)
    print()

    nav     = Navigator(graph)
    speaker = Speaker(use_laptop=False)   # set True when running on Pi with sender

    # ── 2. Example routes ─────────────────────────────────────────────────────
    demo_routes = [
        ("Student Lounge", "LH-201"),
        ("Student Lounge", "LH-202"),
        ("Student Lounge", "LH-204"),
        ("Lift",           "LH-205"),
        ("LH-201",         "LH-202"),
        ("LH-202",         "LH-203"),
        ("LH-203",         "LH-204"),
        ("Student Lounge", "LH-208"),
        ("Lift",           "Washroom"),
    ]

    for start, end in demo_routes:
        print("=" * 60)
        result = dijkstra(graph, start, end)

        # Route preview
        print(nav.preview(result))
        print()

        # Spoken instructions
        instructions = nav.generate(result)
        for instr in instructions:
            print(f"  → {instr}")
        print()

    # ── 3. Blocked corridor demo ──────────────────────────────────────────────
    print("=" * 60)
    print("BLOCKED CORRIDOR DEMO: LH-202 ↔ LH-203 blocked")
    print()
    graph.block("LH-202", "LH-203")

    result = dijkstra(graph, "Student Lounge", "LH-203")
    print(nav.preview(result))
    instructions = nav.generate(result)
    for instr in instructions:
        print(f"  → {instr}")
    print()

    graph.unblock("LH-202", "LH-203")
    print("Corridor unblocked.")
    print()

    # ── 4. Alternative routes demo ────────────────────────────────────────────
    print("=" * 60)
    print("ALTERNATIVE ROUTES: Student Lounge → LH-208")
    print()
    alts = find_alternatives(graph, "Student Lounge", "LH-208", max_routes=2)
    for i, alt in enumerate(alts, 1):
        print(f"  Option {i}: {nav.summary(alt)}")
    print()

    speaker.close()


if __name__ == "__main__":
    run_demo()
