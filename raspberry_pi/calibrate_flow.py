"""
calibrate_flow.py - Neuro Vision Assist
========================================
Optical flow calibration utility.

Usage
-----
1. Place the device in its normal chest-mounted position.
2. Stand at a marked start point.
3. Run:  python3 calibrate_flow.py
4. Walk exactly KNOWN_DISTANCE metres in a straight line.
5. Press Enter when you reach the end point.
6. The script prints the measured distance and the correction factor.
7. Copy the printed OF_CALIBRATION_FACTOR value into config.py.

What it measures
----------------
The script accumulates raw optical flow displacement (before calibration
factor) while you walk.  It then computes:

    factor = KNOWN_DISTANCE / measured_raw_distance

This factor corrects for:
  - Incorrect OF_M_PER_PX (camera mounting height, FOV)
  - Systematic underestimation from radial expansion geometry
  - Any other constant scale error

After calibration, the system will report distances within ~5-10% of
actual for straight-line walking.

Requirements
------------
- Camera must be running (uses existing camera pipeline)
- IMU must be running (for gyro gate)
- Run from the raspberry_pi/ directory
"""

import sys
import time
import threading
import cv2

KNOWN_DISTANCE = 10.0   # metres — change if you walk a different distance

# ── Minimal camera + flow setup (no YOLO, no nav) ─────────────────────────────

sys.path.insert(0, ".")

from config import OF_SCALE, OF_MOTION_THRESH, OF_M_PER_PX, OF_MAX_DISP_M
from config import OF_GYRO_GATE_DEG_S, OF_MIN_CORNERS, NAV_POLL_S
import numpy as np

_CORNER_PARAMS = dict(maxCorners=150, qualityLevel=0.01, minDistance=5, blockSize=7)
_LK_PARAMS     = dict(
    winSize=(21, 21), maxLevel=3,
    criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 15, 0.03),
)
_FOCAL_PX = 133.0

_accum_raw = 0.0   # raw displacement (before calibration factor)
_lock      = threading.Lock()
_running   = True
_gz        = 0.0


def _flow_thread(cap):
    global _accum_raw, _running, _gz
    prev_gray = None
    prev_pts  = None
    last_t    = time.monotonic()

    while _running:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.01)
            continue

        now = time.monotonic()
        dt  = max(now - last_t, 1e-4)
        last_t = now

        small = cv2.resize(frame, (0, 0), fx=OF_SCALE, fy=OF_SCALE)
        gray  = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

        if abs(_gz) > OF_GYRO_GATE_DEG_S:
            prev_gray = gray
            prev_pts  = cv2.goodFeaturesToTrack(gray, mask=None, **_CORNER_PARAMS)
            continue

        if prev_gray is None or prev_pts is None or len(prev_pts) < OF_MIN_CORNERS:
            prev_gray = gray
            prev_pts  = cv2.goodFeaturesToTrack(gray, mask=None, **_CORNER_PARAMS)
            continue

        next_pts, status, _ = cv2.calcOpticalFlowPyrLK(
            prev_gray, gray, prev_pts, None, **_LK_PARAMS
        )
        if next_pts is None or status is None:
            prev_gray = gray
            prev_pts  = cv2.goodFeaturesToTrack(gray, mask=None, **_CORNER_PARAMS)
            continue

        good_prev = prev_pts[status.ravel() == 1]
        good_next = next_pts[status.ravel() == 1]

        if len(good_next) < OF_MIN_CORNERS:
            prev_gray = gray
            prev_pts  = cv2.goodFeaturesToTrack(gray, mask=None, **_CORNER_PARAMS)
            continue

        dx = good_next[:, 0, 0] - good_prev[:, 0, 0]
        dy = good_next[:, 0, 1] - good_prev[:, 0, 1]
        mean_flow = float(np.mean(np.sqrt(dx*dx + dy*dy)))

        gz_rad = abs(_gz) * (3.14159 / 180.0)
        rot    = gz_rad * _FOCAL_PX * dt
        corr   = max(0.0, mean_flow - rot)

        if corr >= OF_MOTION_THRESH:
            raw_disp = min(corr * OF_M_PER_PX, OF_MAX_DISP_M)
            with _lock:
                _accum_raw += raw_disp

        if len(good_next) < int(0.4 * _CORNER_PARAMS["maxCorners"]):
            prev_pts = cv2.goodFeaturesToTrack(gray, mask=None, **_CORNER_PARAMS)
        else:
            prev_pts = good_next.reshape(-1, 1, 2)
        prev_gray = gray


def main():
    global _running, _gz

    # Try to read IMU gz
    imu_available = False
    try:
        from imu_reader import init_mpu, read_raw_imu
        init_mpu()
        imu_available = True
        print("[CAL] IMU available — gyro gate active.")
    except Exception as e:
        print(f"[CAL] IMU unavailable ({e}) — gyro gate disabled.")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[CAL] ERROR: Cannot open camera.")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)

    print(f"\n[CAL] Calibration walk: {KNOWN_DISTANCE} metres")
    print("[CAL] Stand still at start point.")
    input("[CAL] Press Enter when ready to start walking...")

    t = threading.Thread(target=_flow_thread, args=(cap,), daemon=True)
    t.start()

    print(f"[CAL] Walk exactly {KNOWN_DISTANCE} metres in a straight line.")
    print("[CAL] Press Enter when you reach the end point.")

    # Poll IMU gz while waiting
    if imu_available:
        def _imu_poll():
            global _gz
            while _running:
                try:
                    _, _, _, gz = read_raw_imu()
                    _gz = gz
                except Exception:
                    pass
                time.sleep(0.02)
        threading.Thread(target=_imu_poll, daemon=True).start()

    input()
    _running = False
    cap.release()

    with _lock:
        raw = _accum_raw

    if raw < 0.1:
        print("[CAL] ERROR: No optical flow detected. Check camera and lighting.")
        return

    factor = KNOWN_DISTANCE / raw
    corrected = raw * factor

    print(f"\n[CAL] ─────────────────────────────────────────")
    print(f"[CAL] Known distance    : {KNOWN_DISTANCE:.2f} m")
    print(f"[CAL] Raw OF estimate   : {raw:.3f} m  (using OF_M_PER_PX={OF_M_PER_PX})")
    print(f"[CAL] Scale error       : {(raw/KNOWN_DISTANCE - 1)*100:+.1f}%")
    print(f"[CAL] Correction factor : {factor:.4f}")
    print(f"[CAL] ─────────────────────────────────────────")
    print(f"\n[CAL] Add this line to config.py:")
    print(f"      OF_CALIBRATION_FACTOR = {factor:.4f}")
    print(f"\n[CAL] After applying, estimated distance for {KNOWN_DISTANCE}m walk: {corrected:.3f}m")


if __name__ == "__main__":
    main()
