"""
camera_test.py - Neuro Vision Assist
Tests camera feed with FPS counter.

Usage:
    python3 camera_test.py
"""
import os
os.environ['QT_QPA_PLATFORM']  = 'xcb'
os.environ['DISPLAY']          = ':0'
os.environ['XAUTHORITY']       = '/home/raspberrypi/.Xauthority'
import cv2
import time
from camera import open_camera, read_frame, close_camera

def test_camera():
    if not open_camera():
        print("[ERROR] Failed to start camera.")
        return

    print("[OK] Camera started. Press 'q' to quit.")
    frame_count = 0
    start_time  = time.time()
    fps         = 0.0

    cv2.namedWindow("Camera Test", cv2.WINDOW_AUTOSIZE)
    cv2.moveWindow("Camera Test", 0, 0)

    while True:
        ret, frame = read_frame()
        if not ret:
            continue

        frame_count += 1
        elapsed = time.time() - start_time
        if elapsed >= 1.0:
            fps        = frame_count / elapsed
            frame_count = 0
            start_time  = time.time()
            print(f"[FPS] {fps:.1f}")

        cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imshow("Camera Test", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:
            break

    close_camera()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    test_camera()
