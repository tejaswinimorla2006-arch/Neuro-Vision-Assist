"""
run_campus_nav.py
Standalone runner for campus navigation — no camera or IMU required.

Run:
    cd raspberry_pi
    python3 run_campus_nav.py

Type a destination when prompted. Type 'cancel' to stop current route.
Type 'where' to see current location. Type 'quit' to exit.
"""

import sys
import os
import re
import signal
import shutil
import struct
import subprocess
import tempfile
import time
import threading
import wave

sys.path.insert(0, os.path.dirname(__file__))

from campus_nav.navigation_controller import NavigationController
from campus_nav.campus_graph import resolve, all_location_names, NODES
from campus_nav.gps_manager import GPSManager
from campus_nav.mapbox_navigation import MapboxError, reverse_geocode
from campus_nav.tts_manager import speak


_VOICE_RECORD_SECONDS = 8
_VOICE_MAX_ATTEMPTS = 2
_VOICE_RETRY_DELAY_S = 0.5
_VOICE_MICROPHONE_MAC = "18:95:52:A7:28:7D"


class _VoiceMicrophoneUnavailable(Exception):
    pass


def _pipewire_microphone_source():
    if not shutil.which("wpctl"):
        return None
    try:
        result = subprocess.run(
            ["wpctl", "status", "--name"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None

    microphone_mac = re.sub(r"[^0-9a-f]", "", _VOICE_MICROPHONE_MAC.lower())
    for line in result.stdout.splitlines():
        line = line.strip().lstrip("│").strip()
        match = re.match(r"(?:\*\s*)?\d+\.\s+(\S+)", line)
        if not match:
            continue
        source_name = match.group(1)
        if not source_name.startswith("bluez_input."):
            continue
        source_mac = re.sub(r"[^0-9a-f]", "", source_name.split(".", 1)[1].lower())
        if microphone_mac in source_mac:
            return source_name
    return None


def _wav_audio_state(wav_file):
    try:
        with wave.open(wav_file, "rb") as recording:
            if (recording.getnchannels() != 1 or recording.getsampwidth() != 2
                    or recording.getframerate() != 16000 or recording.getnframes() == 0):
                return None
            frames = recording.readframes(recording.getnframes())
    except (OSError, EOFError, wave.Error):
        return None
    if not frames:
        return None

    total_squared = 0
    sample_count = 0
    for (sample,) in struct.iter_unpack("<h", frames[:len(frames) - len(frames) % 2]):
        total_squared += sample * sample
        sample_count += 1
    if not sample_count:
        return None
    return (total_squared / sample_count) ** 0.5 >= 100


def _stop_pw_record(process):
    if process.poll() is not None:
        return
    try:
        process.send_signal(signal.SIGINT)
        process.wait(timeout=2)
        return
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        process.terminate()
        process.wait(timeout=1)
        return
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        process.kill()
        process.wait(timeout=1)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _record_pipewire_wav(wav_file, source_name):
    process = None
    recording_window_elapsed = False
    try:
        if not shutil.which("pw-record"):
            return False
        process = subprocess.Popen(
            [
                "pw-record", "--target", source_name,
                "--rate", "16000", "--channels", "1", "--format", "s16",
                wav_file,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            process.wait(timeout=_VOICE_RECORD_SECONDS)
        except subprocess.TimeoutExpired:
            recording_window_elapsed = True
    except KeyboardInterrupt:
        raise
    except Exception:
        return False
    finally:
        if process is not None:
            _stop_pw_record(process)
    return recording_window_elapsed and _wav_audio_state(wav_file) is not None


def get_voice_input(prompt="[VOICE] Speak your destination or command..."):
    print(prompt)
    try:
        import speech_recognition as sr

        recognizer = sr.Recognizer()
        recognizer.operation_timeout = 8
        for attempt in range(_VOICE_MAX_ATTEMPTS):
            wav_file = None
            try:
                source_name = _pipewire_microphone_source()
                if source_name is None:
                    raise _VoiceMicrophoneUnavailable
                file_descriptor, wav_file = tempfile.mkstemp(
                    prefix="neuro-voice-", suffix=".wav"
                )
                os.close(file_descriptor)
                if not _record_pipewire_wav(wav_file, source_name):
                    raise _VoiceMicrophoneUnavailable
                if _pipewire_microphone_source() != source_name:
                    raise _VoiceMicrophoneUnavailable

                audio_state = _wav_audio_state(wav_file)
                if audio_state is None:
                    raise _VoiceMicrophoneUnavailable
                if not audio_state:
                    print("[VOICE] No speech detected.")
                    return ""
                with sr.AudioFile(wav_file) as source:
                    audio = recognizer.record(source)
                text = recognizer.recognize_google(audio)
                print(f"[VOICE] You said: {text}")
                return text.strip()
            except _VoiceMicrophoneUnavailable:
                if attempt + 1 < _VOICE_MAX_ATTEMPTS:
                    print("[VOICE] Microphone unavailable. Retrying...")
                    time.sleep(_VOICE_RETRY_DELAY_S)
                    continue
                print("[VOICE] Microphone unavailable. Please try again.")
                return ""
            except sr.UnknownValueError:
                print("[VOICE] Could not understand speech.")
                return ""
            except sr.RequestError:
                print("[VOICE] Speech recognition error.")
                return ""
            except KeyboardInterrupt:
                raise
            except Exception as error:
                message = " ".join(str(error).split())[:200]
                print(f"[VOICE] Error: {message}")
                return ""
            finally:
                if wav_file is not None:
                    try:
                        os.unlink(wav_file)
                    except FileNotFoundError:
                        pass
    except KeyboardInterrupt:
        raise
    except Exception as error:
        message = " ".join(str(error).split())[:200]
        print(f"[VOICE] Error: {message}")
        return ""
    return ""

def main():
    print("=" * 55)
    print("   NEURO VISION ASSIST — Campus Navigation")
    print("=" * 55)
    print(f"Known locations: {', '.join(all_location_names())}")
    print("Commands: cancel | where | quit")
    print("=" * 55)

    nav = NavigationController(start_location="main_gate", enqueue_fn=None)
    def on_gps_update(fix):
        nav.set_latest_gps_fix(fix)
        nav.update_gps_position(fix)

    gps_manager = GPSManager(on_position_update=on_gps_update)
    nav.set_gps_provider(gps_manager.get_latest_fix)
    gps_manager.start()

    # Override input loop — we handle input here directly for clarity
    nav._input_loop_active = False  # disable auto input loop from controller

    speak("Campus navigation system ready. Please enter your destination.")

    while True:
        try:
            raw = get_voice_input()
            if raw.lower() in ["where am i", "where am i?", "where"]:
             raw = "where"
        except (EOFError, KeyboardInterrupt):
            print("\n[OK] Exiting.")
            gps_manager.stop()
            break

        if not raw:
            continue

        cmd = raw.lower()

        if cmd == "quit":
            speak("Goodbye.")
            gps_manager.stop()
            break

        if cmd == "cancel":
            nav.cancel()
            continue

        if cmd == "start":
            nav.handle_input("start")
            continue

        if cmd == "where":
            fix = nav._current_valid_fix()
            if (fix is not None and fix.valid and fix.latitude is not None
                    and fix.longitude is not None):
                print(f"[NAV] Current GPS: {fix.latitude:.6f}, {fix.longitude:.6f}")
                try:
                    location = reverse_geocode(fix.latitude, fix.longitude)
                except Exception:
                    location = None
                if location:
                    print(f"[NAV] Current location: {location}")
                    speak(f"You are currently at {location}.")
                else:
                    speak(f"Your current location is latitude {fix.latitude:.6f}, "
                          f"longitude {fix.longitude:.6f}.")
                continue

            print("[NAV] Phone GPS unavailable.")
            speak("Phone GPS is currently unavailable.")
            continue

        # Treat as destination
        nav._handle_destination(raw)

        if nav._external_route is not None and not nav._external_active:
            while nav._external_route is not None and not nav._external_active:
                confirmation = get_voice_input(
                    "[VOICE] Say start to begin navigation..."
                )
                if confirmation.lower() == "start":
                    nav.handle_input(confirmation)

        # Wait for navigation to finish before prompting again
        time.sleep(1)
        while nav.is_navigating:
            time.sleep(0.5)


if __name__ == "__main__":
    main()
