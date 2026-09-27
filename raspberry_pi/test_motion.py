"""
test_motion.py - Neuro Vision Assist
======================================
Diagnostic mode for validating the motion-estimation pipeline.

Tests (run one at a time, observe console output):
  A. Stand still          → Distance ≈ 0 m
  B. Shake camera         → Distance ≈ 0 m
  C. Rotate camera        → Distance ≈ 0 m
  D. Move camera up/down  → Distance ≈ 0 m
  E. Walk forward         → Distance increases continuously

Usage:
    cd raspberry_pi
    python3 test_motion.py

Output (rate-limited to ~1 Hz):
  [IMU]   motion=still   gyro=2.1°/s   steps=0
  [OF]    visual=STILL   features=87
  [FUSION] v=0.000 m/s   gate=IMU-STILL
  [DIST]  increment=0.000m   travelled=0.000m

Press Ctrl+C to stop.
"""

import sys
import time
import threading
import cv2

sys.path.insert(0, ".")

from imu_reader    import init_mpu, read_raw_imu
from camera        import open_camera, read_frame, close_camera
from step_detector import StepDetector
from visual_motion import VisualMotion
from sensor_fusion import SensorFusion
from distance_tracker import DistanceTracker
from config import FRAME_WIDTH, FRAME_HEIGHT, NAV_POLL_S

# ── Shared state ───────────────────────────────────────────────────────────────
_running   = True
_gz_shared = 0.0
_gz_lock   = threading.Lock()

# ── Diagnostic print (rate-limited) ───────────────────────────────────────────
_last_print_t  = 0.0
_last_motion   = ""
_PRINT_INTERVAL = 0.75   # seconds between summary prints


def _print_diag(motion, gyro, steps, visual_still, n_features,
                velocity, gate_reason, increment, travelled):
    global _last_print_t, _last_motion

    now = time.monotonic()
    motion_changed = (motion != _last_motion)

    if not motion_changed and (now - _last_print_t) < _PRINT_INTERVAL:
        return

    _last_print_t = now
    _last_motion  = motion

    visual_str = "STILL" if visual_still else "MOVING"
    print(
        f"\n[IMU]    motion={motion:<8s}  gyro={gyro:5.1f}°/s  steps={steps}"
        f"\n[OF]     visual={visual_str}  features={n_features}"
        f"\n[FUSION] v={velocity:.3f} m/s   gate={gate_reason}"
        f"\n[DIST]   increment={increment:.3f}m   travelled={travelled:.3f}m"
    )


# ── IMU loop (50 Hz) ───────────────────────────────────────────────────────────

def imu_loop(detector: StepDetector, fusion: SensorFusion,
             tracker: DistanceTracker, visual: VisualMotion):
    global _running, _gz_shared

    last_t = time.monotonic()

    while _running:
        t0 = time.monotonic()
        dt = max(t0 - last_t, 1e-4)
        last_t = t0

        try:
            ax, ay, az, gz = read_raw_imu()
        except Exception as e:
            print(f"[IMU ERROR] {e}")
            time.sleep(NAV_POLL_S)
            continue

        with _gz_lock:
            _gz_shared = gz

        detector.update(ax, ay, az, gz)
        fusion.tick(dt)

        pose      = fusion.current_pose
        increment = tracker.update(pose)
        travelled = tracker.travelled_distance

        # Determine what gate fired
        motion = detector.motion_state
        if motion not in ("walking", "running"):
            gate = f"IMU-{motion.upper()}"
        elif detector.step_count < 2:
            gate = "IMU-INSUFFICIENT-STEPS"
        elif visual.is_visually_still and detector.is_still:
            gate = "BOTH-STILL"
        else:
            gate = "WALKING"

        _print_diag(
            motion      = motion,
            gyro        = abs(gz),
            steps       = detector.step_count,
            visual_still= visual.is_visually_still,
            n_features  = 0,   # updated by camera thread
            velocity    = fusion.fused_velocity_m_s,
            gate_reason = gate,
            increment   = increment,
            travelled   = travelled,
        )

        elapsed = time.monotonic() - t0
        time.sleep(max(0.0, NAV_POLL_S - elapsed))


# ── Camera loop ────────────────────────────────────────────────────────────────

def camera_loop(visual: VisualMotion):
    global _running

    while _running:
        ret, frame = read_frame()
        if not ret:
            time.sleep(0.01)
            continue

        with _gz_lock:
            gz = _gz_shared

        visual.submit_frame(frame, gz)

        # Show live preview with motion state overlay
        try:
            state_str = "STILL" if visual.is_visually_still else "MOVING"
            cv2.putText(frame, f"Visual: {state_str}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                        (0, 255, 0) if not visual.is_visually_still else (0, 0, 255), 2)
            cv2.imshow("Motion Test", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                _running = False
        except Exception:
            pass


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    global _running

    print("\n[TEST] Initialising IMU...")
    init_mpu()
    print("[TEST] IMU ready.\n")

    if not open_camera():
        print("[ERROR] Cannot open camera.")
        return

    detector = StepDetector()
    visual   = VisualMotion()
    fusion   = SensorFusion(detector, visual)
    tracker  = DistanceTracker()

    print("=" * 55)
    print("  Motion Estimation Diagnostic")
    print("=" * 55)
    print("  A. Stand still          → Distance ≈ 0 m")
    print("  B. Shake camera         → Distance ≈ 0 m")
    print("  C. Rotate camera        → Distance ≈ 0 m")
    print("  D. Move camera up/down  → Distance ≈ 0 m")
    print("  E. Walk forward         → Distance increases")
    print("  Press Ctrl+C or 'q' in preview to stop.")
    print("=" * 55 + "\n")

    cam_t = threading.Thread(target=camera_loop, args=(visual,), daemon=True)
    cam_t.start()

    imu_t = threading.Thread(
        target=imu_loop, args=(detector, fusion, tracker, visual), daemon=True
    )
    imu_t.start()

    try:
        while _running:
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass

    _running = False
    imu_t.join(timeout=1.0)
    cam_t.join(timeout=1.0)
    close_camera()
    cv2.destroyAllWindows()

    print(f"\n[TEST] Final travelled distance: {tracker.travelled_distance:.3f} m")
    print(f"[TEST] Total steps confirmed:    {detector.step_count}")
    print("[TEST] Done.")


if __name__ == "__main__":
    main()
