# Navigation Module — Neuro Vision Assist

AI-powered indoor navigation for visually impaired users.
Converts a weighted floor graph into spoken turn-by-turn instructions.

---

## Folder Structure

```
raspberry_pi/
└── navigation/
    ├── __init__.py     # package exports
    ├── graph.py        # NavGraph + Edge dataclass + ISE floor 2 data
    ├── dijkstra.py     # Dijkstra shortest-path + alternative routes
    ├── navigator.py    # path → spoken Instruction list
    ├── speech.py       # TTS output (pyttsx3 + laptop UDP sender)
    └── main.py         # runnable demo
```

---

## How It Works

```
User says: "Take me to LH-202"
        ↓
NavGraph (weighted graph of rooms + corridors)
        ↓
dijkstra(graph, "Student Lounge", "LH-202")
        ↓
PathResult(path=[...], total_distance=23.72, edges=[...])
        ↓
Navigator.generate(result)
        ↓
[Instruction("Walk straight for 2.13 metres..."),
 Instruction("Walk straight for 10.13 metres..."),
 Instruction("Walk straight for 11.46 metres. You have arrived at LH-202.")]
        ↓
Speaker.speak_all(instructions)
        ↓
pyttsx3 TTS  +  UDP → laptop voice_receiver.py
```

---

## Graph Model

Each node is a named location (room, staircase, lift, etc.).
Each edge is a bidirectional walking segment with:

| Field       | Type   | Description                              |
|-------------|--------|------------------------------------------|
| distance    | float  | Walking distance in metres               |
| direction   | str    | `"straight"` / `"left"` / `"right"`      |
| landmark    | str    | Spoken hint, e.g. `"LH-202 on your left"`|
| instruction | str    | Override text (auto-generated if empty)  |
| blocked     | bool   | `True` = temporarily impassable          |

---

## Known Distances (ISE 2nd Floor)

| From                | To                  | Distance (m) |
|---------------------|---------------------|--------------|
| Lift                | Student Lounge      | 8.2615       |
| Student Lounge      | Department Library  | 2.132        |
| Department Library  | LH-201              | 10.127       |
| LH-201              | LH-202              | 11.4595      |
| LH-202              | LH-203              | 8.528        |
| LH-202              | Staff Room          | 2.93         |
| LH-203              | Staff Washroom      | 1.8645       |
| LH-203              | LH-204              | 2.665        |
| LH-204              | Middle Stair        | 13.5915      |
| Staff Washroom      | LH-205              | 2.598        |
| Lift                | Right Stair         | 5.0635       |
| Middle Stair        | LH-213              | 2.7316       |
| LH-213              | LH-212              | 5.99         |
| LH-212              | LH-214              | 6.775        |
| LH-214              | Balcony             | 3.878        |
| Balcony             | LH-210              | 14.7145      |
| LH-213              | LH-208              | 3.798        |
| LH-208              | LH-209              | 5.99         |
| LH-209              | LH-207              | 2.398        |
| LH-207              | LH-206              | 3.465        |
| LH-206              | Washroom            | 2.665        |

---

## Sample Output

```
Route: Student Lounge → LH-201  |  12.26 m  |  2 steps

  → Walk straight for 2.13 metres. You are passing Department Library ahead.
  → Walk straight for 10.13 metres. You have arrived at LH-201.
```

```
Route: LH-201 → LH-202  |  11.46 m  |  1 step

  → Walk straight for 11.46 metres. You have arrived at LH-202.
```

```
Route: Lift → LH-205  |  44.97 m  |  7 steps

  → Walk straight for 8.26 metres. You are passing Student Lounge ahead.
  → Walk straight for 2.13 metres. You are passing Department Library ahead.
  → Walk straight for 10.13 metres. You are passing LH-201 on your left.
  → Walk straight for 11.46 metres. You are passing LH-202 on your left.
  → Walk straight for 8.53 metres. You are passing LH-203 on your left.
  → Turn right and walk 1.86 metres. You are passing Staff Washroom on your right.
  → Walk straight for 2.60 metres. You have arrived at LH-205.
```

---

## Running the Demo

```bash
cd raspberry_pi
python3 -m navigation.main
```

---

## Dynamic Updates

```python
from navigation.graph import build_ise_floor2

graph = build_ise_floor2()

# Block a corridor (obstacle / maintenance)
graph.block("LH-202", "LH-203")

# Unblock when clear
graph.unblock("LH-202", "LH-203")

# Add a new room
graph.add_edge("LH-215", "LH-214", distance=5.0, direction="straight",
               landmark="LH-215 on your left")

# Remove a node permanently
graph.remove_node("Balcony")
```

---

## Alternative Routes

```python
from navigation.dijkstra import find_alternatives

alts = find_alternatives(graph, "Student Lounge", "LH-208", max_routes=3)
for i, route in enumerate(alts, 1):
    print(f"Option {i}: {nav.summary(route)}")
```

---

## Adding a New Floor

```python
from navigation.graph import NavGraph

floor3 = NavGraph(floor_id="ISE-Floor-3")
floor3.add_edge("Lift F3", "Corridor F3", distance=3.0, direction="straight")
# ... add all rooms

result = dijkstra(floor3, "Lift F3", "Lab F3-101")
```

No changes to `dijkstra.py`, `navigator.py`, or `speech.py` are needed.

---

## Integration with main.py

```python
from navigation.graph     import build_ise_floor2
from navigation.dijkstra  import dijkstra
from navigation.navigator import Navigator
from navigation.speech    import Speaker

graph   = build_ise_floor2()
nav     = Navigator(graph)
speaker = Speaker(use_laptop=True)

result       = dijkstra(graph, current_location, destination)
instructions = nav.generate(result)
speaker.speak_all(instructions)
```
