"""
Module 1: Camera Test
Run this first to verify the camera is working.
"""

import cv2

def test_camera():
    cap = cv2.VideoCapture(0)  # 0 = default Pi camera

    if not cap.isOpened():
        print("[ERROR] Camera not found. Check ribbon cable connection.")
        return

    print("[OK] Camera opened. Press 'q' to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[ERROR] Failed to read frame.")
            break

        cv2.imshow("Camera Test", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    test_camera()
