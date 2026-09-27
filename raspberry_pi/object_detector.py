"""
object_detector.py - Neuro Vision Assist
YOLOv8n running in a dedicated inference thread.

Architecture (producer-consumer):
  Camera thread  →  [latest_frame slot]  →  YOLO thread  →  [latest_result slot]
  Display thread reads latest_result and overlays it on latest_frame

YOLO never blocks the camera. Camera never waits for YOLO.
If YOLO is slow, it simply skips frames — always processes the newest one.
"""

import cv2
import threading
import time
from collections import defaultdict
from ultralytics import YOLO
from config import CONFIDENCE_THRESHOLD, PROXIMITY_STOP, PROXIMITY_SLOW, TARGET_CLASSES

# ── Model (loaded once at import) ─────────────────────────────────────────────
_model = YOLO("yolov8n.pt")
_model.overrides["verbose"] = False

# ── Temporal smoothing state ───────────────────────────────────────────────────
_CONFIRM_FRAMES = 2
_DECAY_FRAMES   = 4
_tracker        = defaultdict(int)
_absent         = defaultdict(int)
_stable         = set()

# ── Inference thread shared state ─────────────────────────────────────────────
_infer_lock          = threading.Lock()
_pending_frame       = None    # latest frame waiting for inference
_pending_event       = threading.Event()
_latest_detections   = []      # last stable detections (read by display thread)
_latest_annotated    = None    # last annotated frame (read by display thread)
_result_lock         = threading.Lock()
_infer_running       = False
_infer_thread        = None

# Process every Nth frame to save CPU — display still runs at full speed
INFER_EVERY_N_FRAMES = 3
_frame_counter       = 0


def _zone(x_center: float) -> str:
    if x_center < 0.33:  return "left"
    if x_center <= 0.66: return "center"
    return "right"


def get_proximity(box_h: float, frame_h: int) -> str:
    ratio = box_h / frame_h
    if ratio >= PROXIMITY_STOP:  return "close"
    if ratio >= PROXIMITY_SLOW:  return "medium"
    return "far"


def _run_yolo(frame):
    """Run YOLO on a single frame. Returns (annotated_frame, detections)."""
    global _tracker, _absent, _stable

    frame_h, frame_w = frame.shape[:2]

    # Resize to 320 for inference only — faster on Pi, display still uses 640x480
    infer_frame = cv2.resize(frame, (320, 320))
    results = _model(infer_frame, conf=CONFIDENCE_THRESHOLD, imgsz=320, verbose=False)[0]

    # Scale boxes back to original frame size
    sx = frame_w / 320
    sy = frame_h / 320

    raw = []
    for box in results.boxes:
        conf      = float(box.conf[0])
        cls_id    = int(box.cls[0])
        raw_label = _model.names[cls_id].lower()
        label     = raw_label if raw_label in TARGET_CLASSES else "obstacle"

        x1, y1, x2, y2 = box.xyxy[0].tolist()
        x1, y1, x2, y2 = int(x1*sx), int(y1*sy), int(x2*sx), int(y2*sy)
        bh       = y2 - y1
        x_center = (x1 + (x2 - x1) / 2) / frame_w
        zone     = _zone(x_center)
        proximity = get_proximity(bh, frame_h)
        raw.append({"label": label, "x_center": x_center, "zone": zone,
                    "proximity": proximity, "confidence": conf,
                    "box": (x1, y1, x2, y2)})

    # ── Temporal smoothing ────────────────────────────────────────────────────
    seen_keys    = set()
    best_for_key = {}
    for d in raw:
        key = (d["label"], d["zone"])
        seen_keys.add(key)
        if key not in best_for_key or d["confidence"] > best_for_key[key]["confidence"]:
            best_for_key[key] = d

    for key in seen_keys:
        _tracker[key] += 1
        _absent[key]   = 0
        if _tracker[key] >= _CONFIRM_FRAMES:
            _stable.add(key)

    for key in list(_stable | set(_tracker.keys())):
        if key not in seen_keys:
            _absent[key] += 1
            if _absent[key] >= _DECAY_FRAMES:
                _stable.discard(key)
                _tracker.pop(key, None)
                _absent.pop(key, None)

    # ── Build detections + annotate ───────────────────────────────────────────
    detections    = []
    annotated     = frame.copy()
    for key in _stable:
        if key in best_for_key:
            d = best_for_key[key]
            detections.append({
                "label":      d["label"],
                "x_center":   d["x_center"],
                "proximity":  d["proximity"],
                "confidence": d["confidence"],
            })
            x1, y1, x2, y2 = d["box"]
            color = (0, 0, 255) if d["proximity"] == "close" else \
                    (0, 165, 255) if d["proximity"] == "medium" else (0, 255, 0)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            cv2.putText(annotated,
                        f"{d['label']} [{d['proximity']}] {d['confidence']:.0%}",
                        (x1, max(y1 - 8, 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

    return annotated, detections


def _inference_loop():
    """
    Dedicated YOLO thread.
    Waits for a new frame, runs inference, stores result.
    Always picks the LATEST pending frame — skips any that arrived while busy.
    """
    global _infer_running
    while _infer_running:
        triggered = _pending_event.wait(timeout=0.5)
        if not triggered:
            continue
        _pending_event.clear()

        with _infer_lock:
            frame = _pending_frame
        if frame is None:
            continue

        try:
            annotated, detections = _run_yolo(frame)
            with _result_lock:
                global _latest_detections, _latest_annotated
                _latest_detections = detections
                _latest_annotated  = annotated
            # Push into shared scene
            try:
                import scene_manager
                scene_manager.update(detections, "")
            except Exception:
                pass
            # Push frame + current gz to visual motion estimator (non-blocking, < 5 ms)
            try:
                import visual_motion as _vm_mod
                if _vm_mod._nav_monitor is not None:
                    gz = getattr(_vm_mod._nav_monitor, "_current_gz", 0.0)
                    _vm_mod._nav_monitor.submit_camera_frame(frame, gz)
            except Exception:
                pass
        except Exception as e:
            print(f"[YOLO ERROR] {e}")


def start_inference_thread():
    """Call once at startup to launch the YOLO inference thread."""
    global _infer_running, _infer_thread
    _infer_running = True
    _infer_thread  = threading.Thread(target=_inference_loop, daemon=True)
    _infer_thread.start()
    print("[YOLO] Inference thread started.")


def stop_inference_thread():
    global _infer_running
    _infer_running = False


def submit_frame(frame):
    """
    Called by camera/display thread to submit a frame for YOLO inference.
    Non-blocking — if YOLO is busy, the old pending frame is simply replaced.
    Only every Nth frame is submitted to save CPU.
    """
    global _pending_frame, _frame_counter
    _frame_counter += 1
    if _frame_counter % INFER_EVERY_N_FRAMES != 0:
        return
    with _infer_lock:
        _pending_frame = frame.copy()
    _pending_event.set()


def get_latest_result():
    """
    Returns (annotated_frame, detections) from the most recent YOLO inference.
    Returns (None, []) if no inference has completed yet.
    """
    with _result_lock:
        return _latest_annotated, list(_latest_detections)


# ── Legacy synchronous API (kept for standalone testing) ──────────────────────
def detect_objects(frame):
    """Synchronous detection — only used in standalone __main__ test."""
    return _run_yolo(frame)


if __name__ == "__main__":
    from camera import open_camera, read_frame, close_camera
    open_camera()
    start_inference_thread()
    print("[OK] YOLOv8n async detection. Press Ctrl+C to quit.")
    try:
        while True:
            ret, frame = read_frame()
            if not ret:
                continue
            submit_frame(frame)
            annotated, detections = get_latest_result()
            display = annotated if annotated is not None else frame
            for d in detections:
                print(f"  {d['label']:15s} | {d['proximity']:6s} | {d['confidence']:.0%} | x:{d['x_center']:.2f}")
            cv2.imshow("Object Detector", display)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    except KeyboardInterrupt:
        pass
    stop_inference_thread()
    close_camera()
    cv2.destroyAllWindows()
