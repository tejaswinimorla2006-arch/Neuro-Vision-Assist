"""
Module 3: Object Detector
Uses YOLOv8n to detect objects from a camera frame.
Returns list of detections: (label, x_center, confidence)
"""

from ultralytics import YOLO
import cv2

# Only detect these relevant objects
TARGET_CLASSES = {"person", "chair", "bottle", "cell phone"}

model = YOLO("yolov8n.pt")  # Downloads automatically on first run

def detect_objects(frame):
    """
    Args:
        frame: BGR image from OpenCV
    Returns:
        annotated_frame: frame with bounding boxes drawn
        detections: list of (label, x_center_normalized, confidence)
    """
    results = model(frame, verbose=False)[0]
    detections = []

    for box in results.boxes:
        label = model.names[int(box.cls)]
        if label not in TARGET_CLASSES:
            continue

        conf = float(box.conf)
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        x_center = (x1 + x2) / 2 / frame.shape[1]  # Normalize 0.0 to 1.0

        detections.append((label, x_center, conf))

        # Draw bounding box and label
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(frame, f"{label} {conf:.2f}", (x1, y1 - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

    return frame, detections


if __name__ == "__main__":
    cap = cv2.VideoCapture(0)
    print("[OK] Running object detection. Press 'q' to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        annotated, detections = detect_objects(frame)
        print(detections)
        cv2.imshow("Detection", annotated)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
