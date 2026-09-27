"""
chat_interface.py - Neuro Vision Assist
Terminal-based chat interface for keyboard input mode.

Reads user questions from keyboard.
Passes them to vision_reasoner (offline) or chatbot (Gemini/fallback).
Never touches the camera or YOLO — only reads scene_manager.

Future: replace _get_input() with speech input — zero other changes needed.
"""

import threading
import time
import scene_manager
import vision_reasoner

# ── Config ─────────────────────────────────────────────────────────────────────
INPUT_MODE = "keyboard"   # change to "voice" when USB headset connected

_BANNER = """
==============================
  Neuro Vision Assist
  AI Navigation Assistant
==============================
Ask me anything about your surroundings.
Type 'exit' or 'quit' to stop.
------------------------------"""

# ── Input layer (swap this for voice later) ────────────────────────────────────

def _get_input(prompt: str = "You: ") -> str:
    """
    Keyboard mode: reads from terminal.
    Voice mode (future): call speech recogniser here instead.
    Returns empty string on error.
    """
    if INPUT_MODE == "keyboard":
        try:
            return input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            return ""
    # Future voice mode stub
    return ""


# ── Output layer ───────────────────────────────────────────────────────────────

def _print_response(text: str):
    print(f"\nAssistant: {text}\n")


# ── Core chat loop ─────────────────────────────────────────────────────────────

_running = False
_thread  = None

# Optional hook: if set, unknown/complex queries also go to Gemini chatbot
_chatbot_hook = None   # set from main.py: chat_interface._chatbot_hook = chatbot.handle_text_input


def _chat_loop():
    global _running
    print(_BANNER)

    while _running:
        question = _get_input("You: ")

        if not question:
            time.sleep(0.1)
            continue

        if question.lower() in ("exit", "quit"):
            _running = False
            print("\n[CHAT] Goodbye!\n")
            break

        # Always get the freshest scene snapshot — zero camera impact
        scene = scene_manager.get()

        # Vision reasoner handles it offline first
        response = vision_reasoner.answer(question, scene)

        # If reasoner returns a generic fallback AND chatbot hook is set,
        # also send to Gemini for richer answers (optional, non-blocking)
        _print_response(response)

        if _chatbot_hook:
            threading.Thread(
                target=_chatbot_hook,
                args=(question,),
                daemon=True
            ).start()


def start(chatbot_hook=None):
    """
    Start the chat interface in a background thread.
    chatbot_hook: optional function(text) to also send queries to Gemini.
    """
    global _running, _thread, _chatbot_hook
    _chatbot_hook = chatbot_hook
    _running      = True
    _thread       = threading.Thread(target=_chat_loop, daemon=True)
    _thread.start()


def stop():
    global _running
    _running = False


def handle_question(question: str) -> str:
    """
    Synchronous API — answer a single question immediately.
    Used when main thread wants to route a question here directly.
    Returns the answer string.
    """
    scene = scene_manager.get()
    return vision_reasoner.answer(question, scene)
