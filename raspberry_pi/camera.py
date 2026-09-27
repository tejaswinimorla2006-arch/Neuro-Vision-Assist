"""
camera.py - Neuro Vision Assist
Low-latency camera capture using Picamera2 directly (no TCP/rpicam-vid pipe).

Architecture:
  - Picamera2 captures directly into numpy arrays — zero copy, zero TCP buffer
  - A background thread continuously grabs the latest frame
  - read_frame() always returns the NEWEST frame, never a buffered old one
  - If YOLO is slow, frames are dropped (latest wins) — no queue buildup
"""

import threading
import time
import numpy as np

_picam        = None
_latest_frame = None   # always holds the single most recent frame
_frame_lock   = threading.Lock()
_frame_event  = threading.Event()   # signals a new frame is available
_running      = False
_capture_thread = None


def open_camera():
    global _picam, _running, _capture_thread

    try:
        from picamera2 import Picamera2
    except ImportError:
        print("[CAMERA] picamera2 not found. Install: sudo apt install python3-picamera2")
        return False

    try:
        _picam = Picamera2()

        # Low-latency config: small buffer, BGR format (OpenCV native), no extra processing
        config = _picam.create_video_configuration(
            main={"size": (640, 480), "format": "BGR888"},
            buffer_count=2,          # minimum buffers = minimum latency
            controls={
                "FrameRate": 30,
                "NoiseReductionMode": 0,   # disable noise reduction (saves CPU)
                "Sharpness": 1.0,
            }
        )
        _picam.configure(config)
        _picam.start()
        time.sleep(0.5)   # let sensor settle (much shorter than TCP 3s wait)

        _running = True
        _capture_thread = threading.Thread(target=_capture_loop, daemon=True)
        _capture_thread.start()

        print("[CAMERA] Picamera2 started. Low-latency mode active.")
        return True

    except Exception as e:
        print(f"[CAMERA ERROR] {e}")
        return False


def _capture_loop():
    """
    Runs in background thread.
    Grabs frames as fast as the sensor produces them.
    Always overwrites _latest_frame — no queue, no buildup.
    """
    global _latest_frame
    while _running:
        try:
            frame = _picam.capture_array("main")   # direct numpy array, BGR
            with _frame_lock:
                _latest_frame = frame
            _frame_event.set()   # signal that a new frame is ready
        except Exception as e:
            print(f"[CAMERA CAPTURE ERROR] {e}")
            time.sleep(0.01)


def read_frame():
    """
    Returns (True, frame) with the LATEST captured frame.
    Waits up to 100ms for a new frame if none available yet.
    Never returns a stale buffered frame.
    """
    _frame_event.wait(timeout=0.1)
    _frame_event.clear()
    with _frame_lock:
        if _latest_frame is None:
            return False, None
        return True, _latest_frame.copy()


def read_frame_nowait():
    """
    Non-blocking version. Returns whatever is available right now.
    Returns (False, None) if no frame captured yet.
    """
    with _frame_lock:
        if _latest_frame is None:
            return False, None
        return True, _latest_frame.copy()


def close_camera():
    global _picam, _running, _latest_frame
    _running = False
    if _picam:
        try:
            _picam.stop()
            _picam.close()
        except Exception:
            pass
        _picam = None
    _latest_frame = None
    print("[CAMERA] Closed.")
