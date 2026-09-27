"""
vision_reasoner.py - Neuro Vision Assist
Converts raw scene data into human-friendly natural language answers.

Fully OFFLINE — no API, no internet, no cloud.
Runs entirely on Raspberry Pi using rule-based NLU + scene reasoning.

Input  : user question (string) + current scene (from scene_manager)
Output : conversational answer (string)

Future: replace answer() with an LLM call — zero other changes needed.
"""

import re
from distance_estimator import distance_to_words


# ── Intent patterns ────────────────────────────────────────────────────────────
# Each intent maps to a list of keyword patterns (regex)

_INTENTS = {
    "describe":      [r"what.*(see|around|ahead|front|detect|there)",
                      r"describe", r"surroundings", r"tell me what",
                      r"what is (in front|nearby|close)", r"any(thing|one) (there|around|nearby)"],

    "safe_forward":  [r"(is it |can i |should i ).*(safe|walk|move|go|proceed|forward|straight)",
                      r"path (clear|safe|open)", r"can i (walk|go|move)",
                      r"is (it |the path |my way )?(clear|safe|open|free)"],

    "direction":     [r"which (way|direction|side)", r"where should i (go|move|turn)",
                      r"should i (turn|move|go) (left|right|straight)",
                      r"(move|go|turn) (left|right|straight)\??$"],

    "left_check":    [r"(anything|something|obstacle|object).*(left|my left)",
                      r"(left side|on the left)", r"what.*left"],

    "right_check":   [r"(anything|something|obstacle|object).*(right|my right)",
                      r"(right side|on the right)", r"what.*right"],

    "closest":       [r"(closest|nearest|closest obstacle|what is closest)",
                      r"(how close|how near)", r"what is (right |directly )?in front"],

    "count":         [r"how many", r"count (the |all )?", r"number of"],

    "specific_obj":  [r"where is (the |a )?(\w+)", r"(find|locate) (the |a )?(\w+)",
                      r"is there (a |an )?(\w+)"],

    "walkable_dist": [r"how far (can i|should i|do i) (walk|go|move)",
                      r"how much (space|room|distance)", r"walkable distance",
                      r"how many meters"],

    "guidance":      [r"what should i do", r"which way", r"guide me",
                      r"i('m| am) stuck", r"i can'?t (move|go|walk) forward",
                      r"where (is the |is a )?clear path", r"what direction"],

    "navigation":    [r"(navigate|guide|help me)", r"which way (is |to )?safe",
                      r"safe path", r"best (direction|way|path)"],

    "stop":          [r"^stop$", r"halt", r"wait"],

    "greeting":      [r"^(hi|hello|hey)[\s!?]*$", r"good (morning|afternoon|evening)"],

    "help":          [r"what can you do", r"help", r"commands", r"how do you work"],
}


def _match_intent(text: str) -> str:
    t = text.lower().strip()
    for intent, patterns in _INTENTS.items():
        for pat in patterns:
            if re.search(pat, t):
                return intent
    return "unknown"


def _extract_object_name(text: str) -> str | None:
    """Extract object name from 'where is the chair' type queries."""
    m = re.search(r"(?:where is|find|locate|is there)(?: the| a| an)? (\w+)", text.lower())
    return m.group(1) if m else None


# ── Scene summarisers ──────────────────────────────────────────────────────────

def _describe_scene(scene: dict) -> str:
    from guidance import describe_scene as _rich_describe
    return _rich_describe(scene)


def _safe_forward_answer(scene: dict) -> str:
    from guidance import is_path_clear
    return is_path_clear(scene)


def _direction_answer(scene: dict, query: str) -> str:
    safe = scene["safe_direction"]
    blocked = scene["blocked_zones"]

    # User asking about a specific direction
    if "left" in query.lower():
        if "left" in blocked:
            obj = next((o for o in scene["objects"] if o["x_center"] < 0.33), None)
            if obj:
                return (f"No, do not move left. There is a {obj['label']} "
                        f"{distance_to_words(obj['distance_m'])} on your left.")
        return "Left side looks clear. You can move left."

    if "right" in query.lower():
        if "right" in blocked:
            obj = next((o for o in scene["objects"] if o["x_center"] > 0.66), None)
            if obj:
                return (f"No, do not move right. There is a {obj['label']} "
                        f"{distance_to_words(obj['distance_m'])} on your right.")
        return "Right side looks clear. You can move right."

    # General direction advice
    if safe == "forward":
        return "The path ahead is clear. You can continue walking straight."
    if safe == "left":
        return "Move to your left. The left side is clear and safer."
    if safe == "right":
        return "Move to your right. The right side is clear and safer."
    if safe == "stop":
        return "Obstacles are blocking all directions. Please stop and wait for the path to clear."
    return "Continue straight carefully."


def _side_check(scene: dict, side: str) -> str:
    threshold = 0.33 if side == "left" else 0.66
    if side == "left":
        side_objs = [o for o in scene["objects"] if o["x_center"] < threshold]
    else:
        side_objs = [o for o in scene["objects"] if o["x_center"] > threshold]

    if not side_objs:
        return f"Nothing detected on your {side}. That side is clear."

    parts = []
    for o in side_objs:
        parts.append(f"a {o['label']} {distance_to_words(o['distance_m'])}")
    return f"On your {side} I can see: {', '.join(parts)}."


def _closest_answer(scene: dict) -> str:
    if not scene["objects"]:
        return "No obstacles detected. The area around you appears clear."
    c = scene["closest"]
    dist = distance_to_words(c["distance_m"])
    return (f"The closest object is a {c['label']}, "
            f"{dist} to your {c['position']}.")


def _count_answer(scene: dict, query: str) -> str:
    objects = scene["objects"]
    if not objects:
        return "I don't see any objects right now."

    # Check if asking about a specific type
    for label in set(o["label"] for o in objects):
        if label in query.lower():
            count = sum(1 for o in objects if o["label"] == label)
            return f"I can see {count} {label}{'s' if count > 1 else ''}."

    counts = {}
    for o in objects:
        counts[o["label"]] = counts.get(o["label"], 0) + 1

    parts = [f"{v} {k}{'s' if v > 1 else ''}" for k, v in counts.items()]
    total = len(objects)
    return f"I can see {total} object{'s' if total > 1 else ''}: {', '.join(parts)}."


def _find_object(scene: dict, obj_name: str) -> str:
    if not obj_name:
        return "Please specify which object you are looking for."

    matches = [o for o in scene["objects"] if obj_name.lower() in o["label"].lower()]
    if not matches:
        return f"I don't see any {obj_name} in the current view."

    parts = []
    for o in matches:
        parts.append(f"{distance_to_words(o['distance_m'])} to your {o['position']}")
    return f"I can see a {obj_name}: {'; '.join(parts)}."


def _walkable_answer(scene: dict) -> str:
    w = scene["walkable_meters"]
    if w is None:
        if scene["path_clear"]:
            return "The path ahead is open. I estimate you can walk several meters safely."
        return "I cannot estimate the walkable distance right now."
    if w == 0.0:
        return "There is an obstacle very close ahead. You should stop immediately."
    return f"You can walk approximately {w} meters before reaching an obstacle."


def _navigation_answer(scene: dict) -> str:
    safe = scene["safe_direction"]
    objects = scene["objects"]

    if not objects:
        return "The path is completely clear. You can navigate freely in any direction."

    if safe == "forward":
        w = scene["walkable_meters"]
        dist_str = f" for about {w} meters" if w else ""
        return f"Safe to continue straight{dist_str}. No obstacles blocking your path."

    if safe in ("left", "right"):
        blocking = [o for o in objects if o["position"] in ("center", "front left", "front right")]
        if blocking:
            b = blocking[0]
            return (f"There is a {b['label']} {distance_to_words(b['distance_m'])} ahead. "
                    f"The safest path is to your {safe}.")
        return f"Move to your {safe} for the clearest path."

    return "All directions appear blocked. Stop and wait for the path to clear."


# ── Public API ─────────────────────────────────────────────────────────────────

def answer(question: str, scene: dict) -> str:
    """
    Main entry point.
    Takes a natural language question and current scene snapshot.
    Returns a conversational answer string.
    Zero API calls — fully offline.
    """
    if not scene or scene["timestamp"] == 0:
        return ("I don't have a live camera view yet. "
                "Please wait a moment for the camera to initialise.")

    import time
    age = time.time() - scene["timestamp"]
    if age > 5.0:
        return ("My camera view is a few seconds old. "
                "The scene may have changed — please proceed carefully.")

    intent = _match_intent(question)

    if intent == "describe":
        return _describe_scene(scene)

    if intent == "safe_forward":
        return _safe_forward_answer(scene)

    if intent == "direction":
        return _direction_answer(scene, question)

    if intent == "left_check":
        return _side_check(scene, "left")

    if intent == "right_check":
        return _side_check(scene, "right")

    if intent == "closest":
        return _closest_answer(scene)

    if intent == "count":
        return _count_answer(scene, question)

    if intent == "specific_obj":
        obj = _extract_object_name(question)
        return _find_object(scene, obj)

    if intent == "walkable_dist":
        return _walkable_answer(scene)

    if intent == "navigation":
        return _navigation_answer(scene)

    if intent == "guidance":
        from guidance import generate_guidance
        return generate_guidance(scene)

    if intent == "stop":
        return "Stopping. Stay in place."

    if intent == "greeting":
        return ("Hello! I am your Neuro Vision Assist navigation assistant. "
                "I can see your surroundings through the camera. "
                "Ask me what I see, if it is safe to walk, or which direction to go.")

    if intent == "help":
        return ("I can answer questions like: What do you see? Is it safe ahead? "
                "Which direction should I go? How far can I walk? "
                "Is there anything on my left? Where is the chair?")

    # Unknown intent — give a scene-aware generic response
    return _describe_scene(scene)
