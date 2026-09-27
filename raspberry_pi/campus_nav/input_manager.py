"""
input_manager.py
Handles user input for destination entry.

INPUT_MODE = "keyboard"  →  reads from terminal (current)
INPUT_MODE = "voice"     →  uses SpeechRecognition (future)

To switch to voice: change INPUT_MODE = "voice" — no other file needs editing.
"""

import threading

INPUT_MODE = "keyboard"   # change to "voice" when USB headset is connected


# ── Voice mode (future) ────────────────────────────────────────────────────────

def _listen_voice(prompt: str) -> str:
    """
    Listens for a spoken destination via USB microphone.
    Requires: pip install SpeechRecognition pyaudio
    """
    try:
        import speech_recognition as sr
        recognizer = sr.Recognizer()
        with sr.Microphone() as source:
            print(f"[MIC] {prompt}")
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=5)
        text = recognizer.recognize_google(audio)
        print(f"[MIC] Heard: {text}")
        return text.strip()
    except Exception as e:
        print(f"[MIC ERROR] {e}")
        return ""


# ── Keyboard mode (current) ────────────────────────────────────────────────────

def _listen_keyboard(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return ""


# ── Public API ─────────────────────────────────────────────────────────────────

def get_destination(prompt: str = "\nEnter destination: ") -> str:
    """
    Returns the raw user-typed or user-spoken destination string.
    Caller is responsible for resolving it to a node_id via campus_graph.resolve().
    """
    if INPUT_MODE == "voice":
        return _listen_voice(prompt)
    return _listen_keyboard(prompt)


def get_destination_async(callback, prompt: str = "\nEnter destination: "):
    """
    Non-blocking version. Calls callback(destination_str) when input is ready.
    Useful when running inside a thread alongside the camera loop.
    """
    def _worker():
        result = get_destination(prompt)
        if result:
            callback(result)

    threading.Thread(target=_worker, daemon=True).start()
