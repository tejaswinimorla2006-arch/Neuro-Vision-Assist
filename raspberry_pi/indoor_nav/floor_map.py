"""
floor_map.py  –  ISE 2nd Floor, CMR Institute of Technology
All distances are taken directly from the handwritten measurements on the
annotated floor map (ISE_FloorMap.png).  Do NOT change any value without
re-measuring on the physical floor.

Graph structure
---------------
NODES  : {node_id: {"label": str, "type": str}}
EDGES  : list of {"from", "to", "distance", "direction", "heading", "landmark"}
ALIASES: {alias_str: node_id}   – for fuzzy voice matching

Node types: room | lab | junction | staircase | lift |
            washroom | lounge | library | balcony | staffroom

Coordinate system
  x increases left→right (west→east on map)
  y increases top→bottom (north→south on map)

Compass heading convention (matches MPU9250 magnetometer output)
  0°   = North  (up on map, decreasing y)
  90°  = East   (right on map, increasing x)
  180° = South  (down on map, increasing y)
  270° = West   (left on map, decreasing x)

Building layout (derived from ISE_FloorMap.png, 1816×1087 px)
  Scale: ≈ 0.02445 m/px  (26.65 m north corridor / 1090 px)
  ┌─────────────────────────────────────────────────────────┐  ← North corridor
  │  LH-207  LH-206  WC  ║  Staff  StaffWC  LH-205  Stairs │
  │  jn_top_w ──────────── jn_top_mid ──── jn_top_stair    │
  │  ║                          ║                  ║        │
  │  jn_l208                jn_lh203/202        jn_lounge   │
  │  ║                          ║                  ║        │
  │  jn_l209              jn_lh204 ─── jn_lh203 ─ jn_lh201 │
  │  ║                                                       │
  │  jn_l210 ── jn_lift_w                                   │
  └─────────────────────────────────────────────────────────┘  ← South corridor

To add a new floor: create floor3_map.py with the same NODES/EDGES/ALIASES
structure.  path_planner.py accepts any graph dict — no other file changes.
"""

# ── Nodes ──────────────────────────────────────────────────────────────────────
NODES = {
    # ── Lecture Halls (south corridor) ────────────────────────────────────────
    "lh201":        {"label": "LH-201",          "type": "room"},
    "lh202":        {"label": "LH-202",          "type": "room"},
    "lh203":        {"label": "LH-203",          "type": "room"},
    "lh204":        {"label": "LH-204",          "type": "room"},
    "lh205":        {"label": "LH-205",          "type": "room"},
    "lh206":        {"label": "LH-206",          "type": "room"},
    "lh207":        {"label": "LH-207",          "type": "room"},

    # ── Labs (west corridor) ───────────────────────────────────────────────────
    "l208":         {"label": "L-208",           "type": "lab"},
    "l209":         {"label": "L-209",           "type": "lab"},
    "l210":         {"label": "L-210",           "type": "lab"},
    "l211":         {"label": "L-211",           "type": "lab"},
    "l212":         {"label": "L-212",           "type": "lab"},
    "l213":         {"label": "L-213",           "type": "lab"},

    # ── Special rooms ─────────────────────────────────────────────────────────
    "staff_room":   {"label": "Staff Room",      "type": "staffroom"},
    "staff_wc":     {"label": "Staff Washroom",  "type": "washroom"},
    "washroom":     {"label": "Washroom",        "type": "washroom"},
    "library":      {"label": "Department Library", "type": "library"},
    "lounge":       {"label": "Student Lounge",  "type": "lounge"},
    "balcony":      {"label": "Balcony",         "type": "balcony"},

    # ── Vertical access ───────────────────────────────────────────────────────
    "lift":         {"label": "Lift",            "type": "lift"},
    "stairs_west":  {"label": "Stairs (West)",   "type": "staircase"},
    "stairs_east1": {"label": "Stairs (East, Up)",   "type": "staircase"},
    "stairs_east2": {"label": "Stairs (East, Down)", "type": "staircase"},

    # ── Corridor junctions / turning points ───────────────────────────────────
    # Main east–west corridor (top / north side)
    "jn_top_w":     {"label": "North Corridor West Junction",  "type": "junction"},
    "jn_top_mid":   {"label": "North Corridor Mid Junction",   "type": "junction"},
    "jn_top_stair": {"label": "North Corridor Stair Junction", "type": "junction"},

    # South corridor (in front of LH row)
    "jn_lh204":     {"label": "Junction at LH-204",  "type": "junction"},
    "jn_lh203":     {"label": "Junction at LH-203",  "type": "junction"},
    "jn_lh202":     {"label": "Junction at LH-202",  "type": "junction"},
    "jn_lh201":     {"label": "Junction at LH-201",  "type": "junction"},
    "jn_lounge":    {"label": "Junction at Lounge",  "type": "junction"},

    # West vertical corridor (in front of labs)
    "jn_l208":      {"label": "Junction at L-208/L-213", "type": "junction"},
    "jn_l209":      {"label": "Junction at L-209/L-212", "type": "junction"},
    "jn_l210":      {"label": "Junction at L-210/L-211", "type": "junction"},
    "jn_lift_w":    {"label": "West Lift/Stair Junction","type": "junction"},
}

# ── Edges ──────────────────────────────────────────────────────────────────────
# Every edge is stored once; path_planner adds the reverse automatically.
# direction : "straight" | "left" | "right"
# heading   : compass bearing in degrees (0=N, 90=E, 180=S, 270=W)
#             This is the bearing when travelling FROM → TO.
#             path_planner reverses it automatically for the return direction.
# landmark  : optional spoken landmark hint (empty string = none)
EDGES = [

    # ══ NORTH (top) CORRIDOR  ══════════════════════════════════════════════════
    # Runs EAST–WEST.  Travelling east = heading 90°.
    # LH-207 is on the NORTH side of the north corridor, west end.
    # From LH-207 door, walk SOUTH (180°) to reach the corridor.
    {"from": "lh207",        "to": "jn_top_w",     "distance": 13.0585, "direction": "straight", "heading": 180, "landmark": ""},
    # LH-206 is on the NORTH side near jn_top_w.
    {"from": "lh206",        "to": "jn_top_w",     "distance": 2.665,   "direction": "straight", "heading": 180, "landmark": ""},
    # Washroom is on the NORTH side near jn_top_w.
    {"from": "washroom",     "to": "jn_top_w",     "distance": 1.066,   "direction": "straight", "heading": 180, "landmark": ""},
    # North corridor spine: jn_top_w → jn_top_mid (26.65 m, heading EAST = 90°)
    {"from": "jn_top_w",     "to": "jn_top_mid",   "distance": 26.65,   "direction": "straight", "heading": 90,  "landmark": "Staff Room on your right"},
    # Staff Room is on the SOUTH side of the north corridor at jn_top_mid.
    # From Staff Room door, walk NORTH (0°) to reach the corridor.
    {"from": "staff_room",   "to": "jn_top_mid",   "distance": 2.132,   "direction": "straight", "heading": 0,   "landmark": ""},
    # Staff Washroom is on the SOUTH side near jn_top_mid.
    {"from": "staff_wc",     "to": "jn_top_mid",   "distance": 1.865,   "direction": "straight", "heading": 0,   "landmark": ""},
    # LH-205 is on the SOUTH side of the north corridor at jn_top_mid.
    {"from": "lh205",        "to": "jn_top_mid",   "distance": 2.5183,  "direction": "straight", "heading": 0,   "landmark": ""},
    # North corridor continues EAST to stair/lift area.
    {"from": "jn_top_mid",   "to": "jn_top_stair", "distance": 3.4645,  "direction": "straight", "heading": 90,  "landmark": "Lift on your right"},
    # Stairs east (up/down) are on the NORTH side of the stair junction.
    {"from": "stairs_east1", "to": "jn_top_stair", "distance": 5.0635,  "direction": "straight", "heading": 180, "landmark": ""},
    {"from": "stairs_east2", "to": "jn_top_stair", "distance": 5.0635,  "direction": "straight", "heading": 180, "landmark": ""},
    # Lift is on the SOUTH side of the stair junction.
    {"from": "lift",         "to": "jn_top_stair", "distance": 3.4645,  "direction": "straight", "heading": 0,   "landmark": ""},

    # ══ SOUTH CORRIDOR  (in front of LH row)  ══════════════════════════════════
    # Runs EAST–WEST.  Travelling east = heading 90°.
    # jn_lh204 is 16.3231 m EAST of jn_top_w along the south corridor.
    # Travelling from jn_lh204 toward jn_top_w = heading WEST (270°).
    {"from": "jn_lh204",     "to": "jn_top_w",     "distance": 16.3231, "direction": "straight", "heading": 270, "landmark": "Staircase on your left"},
    # South corridor spine going EAST.
    {"from": "jn_lh204",     "to": "jn_lh203",     "distance": 3.9975,  "direction": "straight", "heading": 90,  "landmark": ""},
    {"from": "jn_lh203",     "to": "jn_lh202",     "distance": 5.5965,  "direction": "straight", "heading": 90,  "landmark": ""},
    {"from": "jn_lh202",     "to": "jn_lh201",     "distance": 5.5965,  "direction": "straight", "heading": 90,  "landmark": ""},
    {"from": "jn_lh201",     "to": "jn_lounge",    "distance": 2.132,   "direction": "straight", "heading": 90,  "landmark": ""},
    # Room stubs — LH rooms are on the SOUTH side of the south corridor.
    # From LH door, walk NORTH (0°) to reach the corridor.
    {"from": "lh204",        "to": "jn_lh204",     "distance": 4.5305,  "direction": "straight", "heading": 0,   "landmark": ""},
    {"from": "lh203",        "to": "jn_lh203",     "distance": 2.9315,  "direction": "straight", "heading": 0,   "landmark": ""},
    {"from": "lh202",        "to": "jn_lh202",     "distance": 2.9315,  "direction": "straight", "heading": 0,   "landmark": ""},
    {"from": "lh201",        "to": "jn_lh201",     "distance": 2.9315,  "direction": "straight", "heading": 0,   "landmark": ""},
    # Library is on the NORTH side of the south corridor at jn_lounge.
    # From Library door, walk SOUTH (180°) to reach the corridor.
    {"from": "library",      "to": "jn_lounge",    "distance": 3.4645,  "direction": "straight", "heading": 180, "landmark": ""},
    # Student Lounge is on the SOUTH side at jn_lounge.
    {"from": "lounge",       "to": "jn_lounge",    "distance": 8.2615,  "direction": "straight", "heading": 0,   "landmark": ""},
    # jn_lounge → jn_top_stair: cross-corridor going NORTH (0°).
    {"from": "jn_lounge",    "to": "jn_top_stair", "distance": 8.528,   "direction": "straight", "heading": 0,   "landmark": "Lift ahead"},

    # ══ WEST VERTICAL CORRIDOR  (in front of labs)  ════════════════════════════
    # Runs NORTH–SOUTH.  Travelling south = heading 180°.
    {"from": "jn_top_w",     "to": "jn_l208",      "distance": 2.3985,  "direction": "straight", "heading": 180, "landmark": ""},
    # L-208 is on the WEST side of the corridor; from its door walk EAST (90°).
    {"from": "l208",         "to": "jn_l208",      "distance": 1.0,     "direction": "straight", "heading": 90,  "landmark": ""},
    # L-213 is on the EAST side of the corridor; from its door walk WEST (270°).
    {"from": "l213",         "to": "jn_l208",      "distance": 1.0,     "direction": "straight", "heading": 270, "landmark": ""},
    {"from": "jn_l208",      "to": "jn_l209",      "distance": 3.198,   "direction": "straight", "heading": 180, "landmark": ""},
    {"from": "l209",         "to": "jn_l209",      "distance": 1.0,     "direction": "straight", "heading": 90,  "landmark": ""},
    {"from": "l212",         "to": "jn_l209",      "distance": 1.0,     "direction": "straight", "heading": 270, "landmark": ""},
    {"from": "jn_l209",      "to": "jn_l210",      "distance": 15.99,   "direction": "straight", "heading": 180, "landmark": ""},
    {"from": "l210",         "to": "jn_l210",      "distance": 1.0,     "direction": "straight", "heading": 90,  "landmark": ""},
    {"from": "l211",         "to": "jn_l210",      "distance": 1.0,     "direction": "straight", "heading": 270, "landmark": ""},
    {"from": "jn_l210",      "to": "jn_lift_w",    "distance": 0.7975,  "direction": "straight", "heading": 180, "landmark": ""},
    # West stairs are on the EAST side of the west corridor bottom.
    {"from": "stairs_west",  "to": "jn_lift_w",    "distance": 5.065,   "direction": "straight", "heading": 90,  "landmark": ""},
    # Balcony extends WEST from jn_l210; from balcony walk EAST (90°) to corridor.
    {"from": "balcony",      "to": "jn_l210",      "distance": 18.0687, "direction": "straight", "heading": 90,  "landmark": ""},

    # ══ CROSS-CORRIDORS  (north–south, heading 0° going north)  ════════════════
    # These connect the south corridor to the north corridor.
    {"from": "jn_lh203",     "to": "jn_top_mid",   "distance": 8.528,   "direction": "straight", "heading": 0,   "landmark": ""},
    {"from": "jn_lh202",     "to": "jn_top_mid",   "distance": 8.528,   "direction": "straight", "heading": 0,   "landmark": ""},
    {"from": "jn_lh201",     "to": "jn_top_stair", "distance": 8.528,   "direction": "straight", "heading": 0,   "landmark": ""},
]

# ── Aliases  (voice → node_id) ─────────────────────────────────────────────────
ALIASES = {
    # Lecture halls — with hyphen
    "lh 201": "lh201", "lecture hall 201": "lh201", "hall 201": "lh201",
    "lh 202": "lh202", "lecture hall 202": "lh202", "hall 202": "lh202",
    "lh 203": "lh203", "lecture hall 203": "lh203", "hall 203": "lh203",
    "lh 204": "lh204", "lecture hall 204": "lh204", "hall 204": "lh204",
    "lh 205": "lh205", "lecture hall 205": "lh205", "hall 205": "lh205",
    "lh 206": "lh206", "lecture hall 206": "lh206", "hall 206": "lh206",
    "lh 207": "lh207", "lecture hall 207": "lh207", "hall 207": "lh207",
    # Lecture halls — no hyphen (voice recognition often drops it)
    "lh201": "lh201", "lh202": "lh202", "lh203": "lh203", "lh204": "lh204",
    "lh205": "lh205", "lh206": "lh206", "lh207": "lh207",
    "201": "lh201", "202": "lh202", "203": "lh203", "204": "lh204",
    "205": "lh205", "206": "lh206", "207": "lh207",
    # Labs — with hyphen
    "l 208": "l208", "lab 208": "l208", "laboratory 208": "l208",
    "l 209": "l209", "lab 209": "l209", "laboratory 209": "l209",
    "l 210": "l210", "lab 210": "l210", "laboratory 210": "l210",
    "l 211": "l211", "lab 211": "l211", "laboratory 211": "l211",
    "l 212": "l212", "lab 212": "l212", "laboratory 212": "l212",
    "l 213": "l213", "lab 213": "l213", "laboratory 213": "l213",
    # Labs — no hyphen
    "l208": "l208", "l209": "l209", "l210": "l210",
    "l211": "l211", "l212": "l212", "l213": "l213",
    "208": "l208", "209": "l209", "210": "l210",
    "211": "l211", "212": "l212", "213": "l213",
    # Special rooms
    "staff":              "staff_room",
    "staffroom":          "staff_room",
    "staff room":         "staff_room",
    "staff washroom":     "staff_wc",
    "ladies washroom":    "staff_wc",
    "toilet":             "washroom",
    "restroom":           "washroom",
    "dept library":       "library",
    "department library": "library",
    "ise library":        "library",
    "student lounge":     "lounge",
    "common room":        "lounge",
    "balcony":            "balcony",
    # Vertical access
    "elevator":           "lift",
    "west stairs":        "stairs_west",
    "east stairs":        "stairs_east1",
    "staircase":          "stairs_west",
    "stairs":             "stairs_west",
}
