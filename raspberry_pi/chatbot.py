"""
chatbot.py - Neuro Vision Assist
AI chatbot powered by Google Gemini (free API).
Falls back to rule-based if offline.

Get free API key: https://aistudio.google.com/app/apikey
Set it below in GEMINI_API_KEY.
"""

import threading
import time
import queue
import os

# ─── CONFIG ───────────────────────────────────────────────────────────────────


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

WAKE_WORD      = "hey assist"
LISTEN_TIMEOUT = 5
PHRASE_LIMIT   = 100

# ─── DEPENDENCIES ─────────────────────────────────────────────────────────────
try:
    import requests
    _requests_ok = True
except ImportError:
    _requests_ok = False

try:
    import speech_recognition as sr
    _sr = sr.Recognizer()
    _sr.energy_threshold = 300
    _sr.dynamic_energy_threshold = True
    MIC_AVAILABLE = True
except Exception:
    MIC_AVAILABLE = False

INPUT_MODE = "text" if not MIC_AVAILABLE else "mic"

# ─── CONVERSATION HISTORY (makes it feel like ChatGPT) ────────────────────────

_history = []   # list of {"role": "user"/"model", "parts": [{"text": "..."}]}
_last_gemini_call = 0
_MIN_INTERVAL = 4.0   # seconds between Gemini calls (free tier: 15 req/min)

_SYSTEM_PROMPT = (
    "You are an intelligent AI navigation assistant built into a wearable device for visually impaired people. "
    "You have access to a live camera that detects objects around the user. "
    "Answer any question the user asks — general knowledge, navigation, safety, or anything else. "
    "When the user asks what you see or about their surroundings, use the scene context provided. "
    "Keep responses concise (2-3 sentences max) and always prioritize the user's safety. "
    "Be friendly, natural, and conversational like ChatGPT."
)

# ─── GEMINI API ───────────────────────────────────────────────────────────────

_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

def _gemini_response(user_text: str, scene: str) -> str | None:
    global _last_gemini_call
    if not _requests_ok or GEMINI_API_KEY in ("YOUR_GEMINI_API_KEY", ""):
        return None
    elapsed = time.time() - _last_gemini_call
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    try:
        full_text = user_text
        if scene:
            full_text = f"[Current scene: {scene}]\nUser: {user_text}"

        _history.append({"role": "user", "parts": [{"text": full_text}]})

        payload = {
            "system_instruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
            "contents": _history
        }
        r = requests.post(
            f"{_GEMINI_URL}?key={GEMINI_API_KEY}",
            json=payload, timeout=10
        )
        _last_gemini_call = time.time()
        if r.status_code == 200:
            reply = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            _history.append({"role": "model", "parts": [{"text": reply}]})
            # Keep history to last 10 exchanges to avoid token overflow
            if len(_history) > 20:
                _history.pop(0)
                _history.pop(0)
            return reply
        elif r.status_code == 429:
            pass   # quota exceeded — silently fall through to fallback
        else:
            print(f"[CHATBOT] Gemini error {r.status_code}: {r.text[:100]}")
    except Exception as e:
        print(f"[CHATBOT] Gemini request failed: {e}")
    return None

# ─── RULE-BASED FALLBACK (offline) ────────────────────────────────────────────

def _fallback_response(text: str, scene: str) -> str:
    t = text.lower()
    has_scene = bool(scene and "clear" not in scene.lower())

    if any(w in t for w in ["what do you see", "describe", "what is ahead", "see anything", "detecting", "around me", "in front"]):
        return scene if scene else "The path ahead looks clear, no obstacles detected."

    if any(w in t for w in ["where should i go", "where should i move", "which way", "which direction", "should i move"]):
        if has_scene:
            if "left" in scene.lower():
                return f"{scene} I suggest moving to the right to avoid it."
            elif "right" in scene.lower():
                return f"{scene} I suggest moving to the left to avoid it."
            elif "ahead" in scene.lower() or "stop" in scene.lower():
                return f"{scene} Please stop and wait before proceeding."
        return "The path looks clear. You can move forward carefully."

    if any(w in t for w in ["safe", "is it safe", "clear", "can i walk", "can i move"]):
        if has_scene:
            return f"Caution — {scene} Please navigate carefully."
        return "Path looks clear. You can proceed forward safely."

    if any(w in t for w in ["stop", "halt"]):
        return "Stopping. Stay in place until I give you the all clear."

    if any(w in t for w in ["hello", "hi", "hey"]):
        return "Hello! I am your navigation assistant. How can I help you today?"

    if any(w in t for w in ["help", "what can you do"]):
        return "I can detect obstacles, describe your surroundings, guide your movement, and answer questions. Just ask me anything."

    if any(w in t for w in ["how many", "count"]):
        if has_scene:
            return f"Currently I can see: {scene}"
        return "No objects detected in the current frame."

    if any(w in t for w in ["thank", "thanks"]):
        return "You are welcome! Stay safe."

    if any(w in t for w in ["bye", "goodbye"]):
        return "Goodbye! Take care and stay safe."

    # Generic navigation-aware fallback
    if has_scene:
        return f"Currently I can see: {scene} Let me know if you need guidance."
    return "I am your navigation assistant. The path looks clear. Ask me about your surroundings or where to go."

# ─── EXTERNAL HOOKS (set from main.py) ────────────────────────────────────────

send_to_laptop        = None   # enqueue_message from sender.py
get_scene_description = None   # returns current detection string

# ─── CORE ─────────────────────────────────────────────────────────────────────

def speak_local(text: str):
    print(f"\n🤖 Assistant: {text}\n")

def _handle_query(user_text: str):
    scene = get_scene_description() if get_scene_description else ""
    response = _gemini_response(user_text, scene) or _fallback_response(user_text, scene)
    speak_local(response)
    if send_to_laptop:
        send_to_laptop(f"[AI] {response}")

# ─── INPUT ────────────────────────────────────────────────────────────────────

_text_input_queue = None

def _listen_once() -> str | None:
    if INPUT_MODE == "mic" and MIC_AVAILABLE:
        with sr.Microphone() as source:
            _sr.adjust_for_ambient_noise(source, duration=0.5)
            try:
                audio = _sr.listen(source, timeout=LISTEN_TIMEOUT, phrase_time_limit=PHRASE_LIMIT)
                return _sr.recognize_google(audio).lower().strip()
            except Exception:
                return None
    else:
        try:
            return _text_input_queue.get(timeout=LISTEN_TIMEOUT)
        except Exception:
            return None

def _text_input_thread(q):
    while True:
        try:
            text = input()
            if text.strip():
                q.put(text.strip())
        except EOFError:
            break

# ─── MAIN LOOP ────────────────────────────────────────────────────────────────

_chatbot_active = False

def chatbot_loop():
    """
    Legacy loop kept for standalone testing only.
    When running inside main.py, input is fed via handle_text_input().
    """
    global _chatbot_active, _text_input_queue
    _chatbot_active = True
    ai_status = "Gemini AI" if GEMINI_API_KEY != "YOUR_GEMINI_API_KEY" else "offline fallback"
    print(f"[CHATBOT] Ready ({ai_status}). Input handled by main thread.")

    # Standalone mode only: spin waiting for handle_text_input calls
    while _chatbot_active:
        time.sleep(0.5)
        if False:  # placeholder to keep loop structure
            text = None
            if not text:
                continue

        if INPUT_MODE == "mic":
            if WAKE_WORD in text.lower():
                query = text.lower().replace(WAKE_WORD, "").strip()
                if not query:
                    speak_local("Yes, I am listening.")
                    query = _listen_once()
                if query:
                    _handle_query(query)
        else:
            _handle_query(text)

        time.sleep(0.05)

def stop_chatbot():
    global _chatbot_active
    _chatbot_active = False

# ─── STANDALONE TEST ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Neuro Vision Assist — Chatbot Test ===")
    try:
        chatbot_loop()
    except KeyboardInterrupt:
        print("\n[OK] Chatbot stopped.")

def handle_text_input(text: str):
    """
    Called by main thread to pass a query directly to the chatbot.
    Bypasses stdin — no input() conflict with campus nav.
    """
    if text.strip():
        _handle_query(text.strip())
