"""
speech.py  –  Navigation, Neuro Vision Assist
==============================================
TTS output layer.

Supports two output channels simultaneously:
    1. Local pyttsx3 (Raspberry Pi speaker / headphones)
    2. Laptop sender (UDP socket via existing sender.py)

Both channels are optional — the system degrades gracefully if either
is unavailable (e.g. no audio device, no network connection).

Usage
-----
    from navigation.speech import Speaker
    from navigation.navigator import Instruction

    speaker = Speaker(rate=150, volume=1.0, use_laptop=True)
    speaker.speak("Walk straight for 8.26 metres.")
    speaker.speak_all(instructions)   # list of Instruction objects
    speaker.close()
"""

from __future__ import annotations

import threading
from typing import Callable, List, Optional

from navigation.navigator import Instruction


class Speaker:
    """
    Thread-safe TTS speaker with optional laptop forwarding.

    Parameters
    ----------
    rate        : pyttsx3 speech rate (words per minute, default 150)
    volume      : pyttsx3 volume 0.0–1.0 (default 1.0)
    use_laptop  : if True, also forward text via enqueue_message()
    enqueue_fn  : callable(str) — the sender.enqueue_message function.
                  Pass None to auto-import from sender.py if available.
    """

    def __init__(
        self,
        rate:       int                       = 150,
        volume:     float                     = 1.0,
        use_laptop: bool                      = True,
        enqueue_fn: Optional[Callable[[str], None]] = None,
    ):
        self._lock   = threading.Lock()
        self._engine = None
        self._enqueue: Optional[Callable[[str], None]] = None

        # ── Local TTS ─────────────────────────────────────────────────────────
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate",   rate)
            self._engine.setProperty("volume", volume)
        except Exception as e:
            print(f"[Speaker] pyttsx3 unavailable: {e}. Text-only mode.")

        # ── Laptop sender ─────────────────────────────────────────────────────
        if use_laptop:
            if enqueue_fn is not None:
                self._enqueue = enqueue_fn
            else:
                try:
                    from sender import enqueue_message
                    self._enqueue = enqueue_message
                except ImportError:
                    pass   # sender.py not available — silent fallback

    # ── Public API ────────────────────────────────────────────────────────────

    def speak(self, text: str) -> None:
        """
        Speak one text string.
        Prints to console, sends to laptop, and plays via TTS in a daemon thread.
        """
        print(f"\n[NAV] {text}")

        if self._enqueue:
            try:
                self._enqueue(text)
            except Exception:
                pass

        if self._engine:
            threading.Thread(target=self._tts_run, args=(text,), daemon=True).start()

    def speak_all(self, instructions: List[Instruction]) -> None:
        """
        Speak a list of Instruction objects sequentially.
        Each instruction is spoken in its own daemon thread so the caller
        is not blocked; instructions are queued via the TTS lock.
        """
        for instr in instructions:
            self.speak(str(instr))

    def speak_fn(self) -> Callable[[str], None]:
        """
        Return a plain callable(str) suitable for passing to NavigationMonitor
        or IndoorNavController as speak_fn.
        """
        return self.speak

    def close(self) -> None:
        """Release the pyttsx3 engine."""
        if self._engine:
            try:
                self._engine.stop()
            except Exception:
                pass
            self._engine = None

    # ── Internal ──────────────────────────────────────────────────────────────

    def _tts_run(self, text: str) -> None:
        with self._lock:
            try:
                self._engine.say(text)
                self._engine.runAndWait()
            except Exception as e:
                print(f"[Speaker] TTS error: {e}")
