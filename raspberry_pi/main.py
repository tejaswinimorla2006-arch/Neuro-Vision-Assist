"""
main.py - Neuro Vision Assist
AI Navigation Assistant for Visually Impaired Users

Input flow (navigation INACTIVE):
    Wake word → listen → intent → handler

Input flow (navigation ACTIVE):
    Any input → navigation controller FIRST
    Only if nav cannot handle it → vision / safety / chat
    Wake word NEVER resets navigation state.
"""

import os

HEADLESS = False
if not HEADLESS:
    os.environ["DISPLAY"]         = ":0"
    os.environ["XAUTHORITY"]      = "/home/raspberrypi/.Xauthority"
    os.environ["QT_QPA_PLATFORM"] = "xcb"

import cv2
import time
import threading

from config           import FRAME_WIDTH, FRAME_HEIGHT, SEND_INTERVAL, NAV_REPEAT_INTERVAL
from object_detector  import submit_frame, get_latest_result, start_inference_thread, stop_inference_thread
from camera           import open_camera, read_frame, close_camera
from navigation_logic import generate_instruction
from sender           import start_sender, enqueue_message
from imu_reader       import init_mpu, get_orientation
import scene_manager
import vision_reasoner
import chatbot
import intent
import guidance as guidance_module
from campus_nav.navigation_controller import NavigationController
from campus_nav.gps_manager           import GPSManager
from indoor_nav.navigation_controller import IndoorNavController

# ── Indoor nav controller (module-level so IMU thread can reach it) ────────────
_indoor_nav: IndoorNavController | None = None

# ── Shared state ───────────────────────────────────────────────────────────────
_lock  = threading.Lock()
_state = {
    "tilt_alert":       False,
    "pitch":            0.0,
    "roll":             0.0,
    "gps_lat":          None,
    "gps_lon":          None,
    "last_detections":  [],
    "last_instruction": "",
}

def _get(key):
    with _lock:
        return _state[key]


# ── TTS ────────────────────────────────────────────────────────────────────────
_tts_lock        = threading.Lock()
_tts_engine      = None
_tts_error_count = 0
_TTS_ERROR_MAX   = 3   # stop logging after this many consecutive failures

def _init_tts():
    global _tts_engine
    try:
        import pyttsx3
        _tts_engine = pyttsx3.init()
        _tts_engine.setProperty("rate", 150)
        _tts_engine.setProperty("volume", 1.0)
        print("[OK] TTS engine initialised.")
    except Exception as e:
        print(f"[WARN] TTS unavailable: {e}. Terminal output only.")
        _tts_engine = None

def speak(text: str):
    """Print + enqueue for laptop. TTS in background thread, errors suppressed after limit."""
    global _tts_error_count
    print(f"\nAssistant: {text}\n")
    enqueue_message(text)
    if _tts_engine is None:
        return
    def _run():
        global _tts_error_count
        with _tts_lock:
            try:
                _tts_engine.say(text)
                _tts_engine.runAndWait()
                _tts_error_count = 0   # reset on success
            except Exception as e:
                _tts_error_count += 1
                if _tts_error_count <= _TTS_ERROR_MAX:
                    print(f"[TTS] Audio error (sending to laptop instead): {e}")
    threading.Thread(target=_run, daemon=True).start()


# ── Intent handlers ────────────────────────────────────────────────────────────

def get_guidance() -> str:
    return guidance_module.generate_guidance(scene_manager.get())

def describe_scene() -> str:
    scene = scene_manager.get()
    base  = vision_reasoner.answer("what do you see", scene)
    # If navigating, append nav context
    if _indoor_nav and _indoor_nav.is_navigating:
        instr = _indoor_nav._state.current_instruction
        if instr:
            return f"{base} Your current navigation instruction is: {instr}"
    return base

def obstacle_guidance() -> str:
    scene = scene_manager.get()
    base  = vision_reasoner.answer("is it safe to walk", scene)
    if _indoor_nav and _indoor_nav.is_navigating:
        remaining = _indoor_nav._state.remaining_in_segment
        if remaining > 0:
            return f"{base} You have approximately {remaining:.1f} metres remaining to the next waypoint."
    return base

def ask_gemini(query: str) -> str:
    scene     = scene_manager.get()
    objects   = scene.get("objects", [])
    labels    = list(dict.fromkeys(o["label"] for o in objects))
    scene_ctx = ("I can see: " + ", ".join(labels) + ".") if labels else "Path looks clear."

    result         = {"text": None}
    original_speak = chatbot.speak_local

    def _capture(text):
        result["text"] = text

    chatbot.speak_local           = _capture
    chatbot.get_scene_description = lambda: scene_ctx
    chatbot.handle_text_input(query)

    for _ in range(80):
        if result["text"] is not None:
            break
        time.sleep(0.1)

    chatbot.speak_local = original_speak
    return result["text"] or vision_reasoner.answer(query, scene)


# ── Input loop ─────────────────────────────────────────────────────────────────

def _read_input(prompt: str = "") -> str:
    """Read one line from stdin. Returns '' on error."""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return "__EXIT__"


def _route_command(command: str) -> bool:
    """
    Route a command to the correct handler.
    Returns False if the caller should exit.

    Priority when navigation is ACTIVE:
        1. Hard nav commands (next/continue/repeat/cancel/pause/resume/where)
           → ALWAYS handled by nav, NEVER by chat
        2. Vision / Safety / Guidance questions
        3. Navigation controller (location answers, destination changes)
        4. Chat fallback

    Priority when navigation is INACTIVE:
        1. Intent classification → handler
    """
    if not command or command == "__EXIT__":
        return command != "__EXIT__"

    if command.lower() in ("quit", "exit"):
        return False

    nav_session_active = _indoor_nav and (
        _indoor_nav.is_navigating or
        _indoor_nav._state.state.name in ("AWAITING_START", "AWAITING_DEST")
    )

    # ── Navigation session is ACTIVE ──────────────────────────────────────────
    if nav_session_active:
        from indoor_nav.navigation_controller import _NAV_COMMANDS
        t = command.strip().lower()

        # Hard nav commands — intercepted BEFORE intent classification
        if _NAV_COMMANDS.match(t):
            _indoor_nav.handle_input(command)
            return True

        # Vision / Safety / Guidance always allowed during navigation
        user_intent = intent.detect(command)
        if user_intent == "VISION":
            speak(describe_scene())
            return True
        if user_intent == "SAFETY":
            speak(obstacle_guidance())
            return True
        if user_intent == "GUIDANCE":
            speak(get_guidance())
            return True

        # Everything else → nav controller first, then chat
        handled = _indoor_nav.handle_input(command)
        if not handled:
            threading.Thread(
                target=lambda q=command: speak(ask_gemini(q)),
                daemon=True
            ).start()
        return True

    # ── Navigation INACTIVE: normal intent routing ─────────────────────────────
    user_intent = intent.detect(command)
    print(f"[INTENT] {user_intent} -> \"{command}\"")

    if user_intent == "GUIDANCE":
        speak(get_guidance())

    elif user_intent == "VISION":
        speak(describe_scene())

    elif user_intent == "SAFETY":
        speak(obstacle_guidance())

    elif user_intent == "NAVIGATION":
        handled = _indoor_nav.handle_input(command)
        if not handled:
            threading.Thread(
                target=lambda q=command: speak(ask_gemini(q)),
                daemon=True
            ).start()

    elif user_intent == "SYSTEM":
        if command.lower() in ("where", "where am i"):
            node = _indoor_nav._state.current_node if _indoor_nav else None
            if node:
                from indoor_nav.floor_map import NODES as FNODES
                label = FNODES.get(node, {}).get("label", node)
                speak(f"You are currently near {label}.")
            else:
                speak("I don't know your current location yet.")
        elif command.lower() == "help":
            speak(
                "Say: what do you see, is it safe to walk, "
                "take me to LH-202, or ask me anything."
            )
        else:
            speak("Okay.")

    else:
        threading.Thread(
            target=lambda q=command: speak(ask_gemini(q)),
            daemon=True
        ).start()

    return True


def main_loop():
    """
    Main input loop.

    When navigation is ACTIVE the loop reads input directly without
    requiring the wake word — the session stays alive.

    When navigation is INACTIVE the loop waits for the wake word first.
    """
    print(f'\n[Waiting] Type "{intent.WAKE_WORD}" to activate  (or "quit" to exit)...')

    while True:
        nav_active = _indoor_nav and (
            _indoor_nav.is_navigating or
            _indoor_nav._state.state.name in ("AWAITING_START", "AWAITING_DEST")
        )

        if nav_active:
            # ── Navigation session: read input directly, no wake word needed ──
            raw = _read_input("You: ")
            if raw == "__EXIT__":
                break

            if not raw:
                continue

            # Strip wake word if user happens to say it — don't reset nav
            if intent.detect(raw) == "WAKE":
                remainder = intent.remainder_after_wake(raw)
                if remainder:
                    raw = remainder
                else:
                    speak("I'm still navigating. What do you need?")
                    continue

            if not _route_command(raw):
                break

        else:
            # ── Idle: wait for wake word ───────────────────────────────────────
            raw = _read_input()
            if raw == "__EXIT__":
                break
            if not raw:
                continue
            if raw.lower() in ("quit", "exit"):
                break

            if intent.detect(raw) != "WAKE":
                continue   # ignore non-wake input while idle

            command = intent.remainder_after_wake(raw)
            if not command:
                speak("Yes, I'm listening.")
                command = _read_input("You: ")

            if command == "__EXIT__":
                break

            if not _route_command(command):
                break

            # After routing, if nav just became active, print nav prompt
            if _indoor_nav and (
                _indoor_nav.is_navigating or
                _indoor_nav._state.state.name in ("AWAITING_START", "AWAITING_DEST")
            ):
                print("[NAV] Navigation session active. No wake word needed until destination reached.")
            else:
                print(f'\n[Waiting] Type "{intent.WAKE_WORD}" to activate  (or "quit" to exit)...')


# ── Background threads ─────────────────────────────────────────────────────────

def imu_thread():
    init_mpu()
    print("[OK] IMU thread started.")
    while True:
        try:
            pitch, roll, yaw, tilt_alert = get_orientation()
            with _lock:
                _state["pitch"]      = pitch
                _state["roll"]       = roll
                _state["tilt_alert"] = tilt_alert
        except Exception as e:
            print(f"[IMU ERROR] {e}")
        time.sleep(0.2)


def camera_thread(running):
    last_sent_time = 0
    last_message   = ""
    fps_counter    = 0
    fps_timer      = time.time()
    fps            = 0.0

    _show = not HEADLESS
    if _show:
        try:
            cv2.namedWindow("Neuro Vision Assist", cv2.WINDOW_AUTOSIZE)
            cv2.moveWindow("Neuro Vision Assist", 0, 0)
        except Exception:
            _show = False
            print("[WARN] Cannot open display window. Running headless.")

    while running.is_set():
        ret, frame = read_frame()
        if not ret:
            continue

        fps_counter += 1
        if time.time() - fps_timer >= 1.0:
            fps         = fps_counter / (time.time() - fps_timer)
            fps_counter = 0
            fps_timer   = time.time()

        submit_frame(frame)

        annotated_frame, detections = get_latest_result()
        if annotated_frame is None:
            annotated_frame = frame

        tilt_alert  = _get("tilt_alert")
        instruction = generate_instruction(detections, tilt_alert)

        with _lock:
            _state["last_detections"]  = detections
            _state["last_instruction"] = instruction or ""

        # Only real YOLO detections trigger obstacle nav pause
        if _indoor_nav is not None and _indoor_nav.is_navigating:
            has_obs = bool(
                detections
                and instruction
                and "clear"  not in instruction.lower()
                and "adjust" not in instruction.lower()
            )
            _indoor_nav.obstacle_update(has_obs, instruction or "")

        # Passive obstacle alerts — skip tilt-only messages
        now = time.time()
        is_real_obstacle = (
            instruction
            and "clear"  not in instruction.lower()
            and "adjust" not in instruction.lower()
            and detections
        )
        if is_real_obstacle:
            elapsed         = now - last_sent_time
            message_changed = instruction != last_message
            if (elapsed >= SEND_INTERVAL and message_changed) or elapsed >= NAV_REPEAT_INTERVAL:
                print(f"\n[OBSTACLE ALERT] {instruction}")
                enqueue_message(instruction)
                last_message   = instruction
                last_sent_time = now

        if instruction:
            cv2.putText(annotated_frame, instruction[:60], (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2)
        cv2.putText(annotated_frame, f"FPS:{fps:.1f}",
                    (FRAME_WIDTH - 80, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        lat      = _get("gps_lat")
        lon      = _get("gps_lon")
        gps_text = f"GPS:{lat},{lon}" if lat else "GPS:no fix"
        cv2.putText(annotated_frame, gps_text,
                    (10, FRAME_HEIGHT - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 0), 1)

        if _show:
            try:
                cv2.imshow("Neuro Vision Assist", annotated_frame)
                cv2.waitKey(1)
            except Exception:
                _show = False

    # Signal YOLO to stop — camera/window cleanup done in main thread
    stop_inference_thread()
    if _show:
        cv2.destroyAllWindows()


def _imu_reader_for_nav():
    """Read calibrated IMU values for NavigationMonitor. Called at 50 Hz."""
    from imu_reader import read_raw_imu
    return read_raw_imu()


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    global _indoor_nav
    _init_tts()
    start_sender()

    threading.Thread(target=imu_thread, daemon=True).start()

    _indoor_nav = IndoorNavController(speak_fn=speak, imu_read_fn=_imu_reader_for_nav)

    # Wire the navigation monitor's visual motion into the camera pipeline.
    # object_detector.py reads visual_motion._nav_monitor after each YOLO frame.
    import visual_motion as _vm
    _vm._nav_monitor = _indoor_nav._monitor

    nav = NavigationController(start_location="main_gate", enqueue_fn=enqueue_message)
    def on_gps_update(fix):
        with _lock:
            _state["gps_lat"] = fix.latitude
            _state["gps_lon"] = fix.longitude
        nav.set_latest_gps_fix(fix)
        nav.update_gps_position(fix)

    gps_manager = GPSManager(
        on_campus_entered=lambda: nav.set_current_location("main_gate"),
        on_position_update=on_gps_update
    )
    nav.set_gps_provider(gps_manager.get_latest_fix)
    gps_manager.start()

    chatbot.send_to_laptop = enqueue_message

    if not open_camera():
        print("[ERROR] Camera not found. Check CSI cable and raspi-config.")
        return

    print(f"[OK] Camera: {FRAME_WIDTH}x{FRAME_HEIGHT}")
    start_inference_thread()

    running    = threading.Event()
    running.set()
    cam_thread = threading.Thread(target=camera_thread, args=(running,), daemon=True)
    cam_thread.start()

    print("\n" + "=" * 52)
    print("  Neuro Vision Assist — AI Navigation Assistant")
    print("=" * 52)
    print(f'  Wake word : "{intent.WAKE_WORD}"')
    print("  Intents   : VISION | SAFETY | GUIDANCE | NAVIGATION | CHAT")
    print("  Examples  :")
    print('    "hey assist take me to LH-202"')
    print('    "hey assist what do you see"')
    print('    "hey assist is it safe to walk"')
    print('    During navigation: just type your location or "next"')
    print("=" * 52)

    try:
        main_loop()
    except KeyboardInterrupt:
        pass

    running.clear()
    cam_thread.join(timeout=3.0)
    close_camera()
    print("\n[OK] System stopped.")


if __name__ == "__main__":
    main()
