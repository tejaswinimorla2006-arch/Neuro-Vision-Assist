"""
tts_manager.py
Text-to-Speech through espeak-ng + PipeWire Bluetooth audio.
"""

import os
import subprocess
import tempfile
import threading

_lock = threading.Lock()


def _speak(text: str):
    with _lock:
        wav_file = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav_file = f.name

            subprocess.run(
                ["espeak-ng", "-s", "150", "-w", wav_file, text],
                check=True
            )

            subprocess.run(
                ["pw-play", wav_file],
                check=False
            )

        except Exception as e:
            print(f"[TTS] Audio error: {e}")

        finally:
            if wav_file and os.path.exists(wav_file):
                os.remove(wav_file)


def speak(text: str, blocking: bool = False):
    print(f"[SPEAK] {text}")

    if blocking:
        _speak(text)
    else:
        threading.Thread(
            target=_speak,
            args=(text,),
            daemon=True
        ).start()
