"""
main.py - Neuro Vision Assist
Integrates: Camera + YOLOv8 Detection + Navigation Logic + IMU + Socket Sender

Run on Raspberry Pi:
    python3 main.py

Make sure voice_receiver.py is running on the laptop first.
Set LAPTOP_IP in sender.py before running.
"""

import cv2
import time
import threading

from object_detector  import detect_objects
from navigation_logic import generate_instruction
from sender           import send_message
from imu_reader       import init_mpu, get_orientation

# --- Config ---
SEND_INTERVAL   = 2.0   # Seconds between sending messages (avoid spam)
SHOW_PREVIEW    = True  # Set False on headless Pi to save resources

last_sent_time  = 0
last_message    = ""

def imu_thread():
    """Background thread: continuously reads and prints IMU data."""
    init_mpu()
    while True:
        try:
            pitch, roll, yaw = get_orientation()
            print(f"[IMU] Pitch:{pitch}° Roll:{roll}° Yaw:{yaw}°/s")
        except Exception as e:
            print(f"[IMU ERROR] {e}")
        time.sleep(1)

def main():
    global last_sent_time, last_message

    # Start IMU in background thread
    t = threading.Thread(target=imu_thread, daemon=True)
    t.start()

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] Camera not found.")
        return

    # Lower resolution for better performance on Pi
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    print("[OK] System running. Press 'q' to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[ERROR] Frame read failed.")
            break

        annotated_frame, detections = detect_objects(frame)
        instruction = generate_instruction(detections)

        now = time.time()

        # Send only if new message and enough time has passed
        if instruction and instruction != last_message and (now - last_sent_time) >= SEND_INTERVAL:
            print(f"[NAV] {instruction}")
            send_message(instruction)
            last_message    = instruction
            last_sent_time  = now

        if SHOW_PREVIEW:
            if instruction:
                cv2.putText(annotated_frame, instruction, (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            cv2.imshow("Neuro Vision Assist", annotated_frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
