"""
intent.py - Neuro Vision Assist
Classifies user input into one of four intents before any module touches it.

Returns: VISION | SAFETY | NAVIGATION | CHAT | SYSTEM | WAKE | EMPTY
"""

import re

WAKE_WORD = "hey assist"
WAKE_WORD_VARIANTS = [
    "hey assist", "hi assist", "hey assistant",
    "ok assist", "okay assist", "hey system",
]

SYSTEM_COMMANDS = {"quit", "exit", "cancel", "where", "help"}

_PATTERNS = {
    "GUIDANCE": [
        r"what should i do",
        r"where should i go",
        r"which way (should i |do i )?(turn|go|move)",
        r"help me (move|walk|navigate|get through)",
        r"guide me",
        r"i('m| am) stuck",
        r"i can'?t (move|go|walk) forward",
        r"where is (the )?clear path",
        r"which direction is safe",
        r"what direction",
        r"how do i get (past|around|through)",
        r"i moved (left|right|forward|back)",
    ],
    "VISION": [
        r"what (do you |can you )?(see|detect|observe|notice)",
        r"describe",
        r"surroundings|scene|environment",
        r"look around",
        r"scan (surroundings|area|scene|around)",
        r"can you see (anything|something)",
        r"tell me what (you see|is around|is ahead|is there)",
        r"what objects",
        r"any(thing|one) (around|nearby|there|ahead|close)",
        r"give me a description",
        r"what is (in front|nearby|close|ahead)",
    ],
    "SAFETY": [
        r"(is it |am i )safe",
        r"can i (walk|move|go|proceed|continue|step)",
        r"(is the |is my )(path|way|road) (clear|safe|open|free)",
        r"(should i |shall i )(stop|wait|move|walk|go|proceed)",
        r"(is there |are there ).*(ahead|in front|blocking)",
        r"(can i |is it ok to )(walk|move|go) (forward|straight|ahead)",
        r"guide me (around|past|through)",
        r"(am i |is it )(blocked|clear|safe|ok)",
        r"obstacle (ahead|in front|nearby)",
        r"is (my |the )?(path|way|road) (blocked|clear|safe)",
        r"what.* blocking",
        r"(move|go|turn) (left|right|straight)",
        r"which (way|direction|side) (is |should i )(safe|go|move|turn)",
        r"how far can i (walk|go|move)",
    ],
    "NAVIGATION": [
        r"(take me|navigate|go) to",
        r"(guide me|directions?) to",
        r"how (do i|to) get to",
        r"(i want to|i need to) go to",
        r"route to",
        r"shortest path",
        r"campus (map|navigation|route)",
        r"indoor (navigation|nav)",
        r"floor (map|navigation)",
        # In-progress navigation commands
        r"where do i go (now|next)",
        r"next instruction",
        r"continue navigation",
        r"what'?s next",
        r"which way now",
        r"cancel navigation",
        r"stop navigation",
        r"repeat (instruction|that|navigation)",
        r"where am i",
        r"current location",
    ],
}


def detect(text: str) -> str:
    t = text.strip().lower()

    if not t:
        return "EMPTY"

    for variant in WAKE_WORD_VARIANTS:
        if t == variant or t.startswith(variant):
            return "WAKE"

    if t in SYSTEM_COMMANDS:
        return "SYSTEM"

    for intent_name in ("GUIDANCE", "VISION", "SAFETY", "NAVIGATION"):
        for pattern in _PATTERNS[intent_name]:
            if re.search(pattern, t):
                return intent_name

    return "CHAT"


def is_wake_word(text: str) -> bool:
    return detect(text) == "WAKE"


def remainder_after_wake(text: str) -> str:
    """Extract command typed on same line as wake word."""
    t = text.strip().lower()
    for variant in WAKE_WORD_VARIANTS:
        if t.startswith(variant):
            return text[len(variant):].strip()
    return ""
