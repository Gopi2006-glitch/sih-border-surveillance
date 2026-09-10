import cv2
import numpy as np
from shapely.geometry import Point, Polygon
from ultralytics import YOLO

# 1. Load model (YOLOv8n is lightweight and fast for CPU/GPU prototyping)
model = YOLO("yolov8n.pt")

# Target classes from COCO: 0: person, 1: bicycle, 2: car, 3: motorcycle, 5: bus, 7: truck
TARGET_CLASSES = [0, 1, 2, 3, 5, 7]

# 2. Define a Virtual Fence / Restricted Polygon [(x1, y1), (x2, y2), ...]
# (Adjust coordinates based on your video/camera resolution)
FENCE_COORDS = [(200, 200), (500, 200), (500, 450), (200, 450)]
fence_polygon = Polygon(FENCE_COORDS)

# 3. Input source (0 for default webcam, or replace with "rtsp://..." or "test.mp4")
cap = cv2.VideoCapture(0)

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    # Run YOLO tracking (persists track IDs frame-to-frame)
    results = model.track(
        source=frame,
        persist=True,
        classes=TARGET_CLASSES,
        verbose=False
    )

    # Draw the Virtual Fence boundary (Yellow)
    pts = np.array(FENCE_COORDS, np.int32).reshape((-1, 1, 2))
    cv2.polylines(frame, [pts], isClosed=True, color=(0, 255, 255), thickness=2)

    # Process detections
    if results[0].boxes.id is not None:
        boxes = results[0].boxes.xyxy.cpu().numpy()
        track_ids = results[0].boxes.id.int().cpu().numpy()
        cls_ids = results[0].boxes.cls.int().cpu().numpy()

        for box, track_id, cls_id in zip(boxes, track_ids, cls_ids):
            x1, y1, x2, y2 = map(int, box)
            label = model.names[cls_id]

            # Calculate footpoint/bottom-center for accurate ground contact
            foot_x = int((x1 + x2) / 2)
            foot_y = int(y2)
            foot_point = Point(foot_x, foot_y)

            # Virtual fence collision check
            is_inside = fence_polygon.contains(foot_point)
            box_color = (0, 0, 255) if is_inside else (0, 255, 0)  # Red if breach, Green if normal

            if is_inside:
                cv2.putText(
                    frame,
                    f"BREACH! ID:{track_id} ({label})",
                    (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 0, 255),
                    2
                )
            else:
                cv2.putText(
                    frame,
                    f"ID:{track_id} {label}",
                    (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 0),
                    1
                )

            # Draw bounding box and foot point
            cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
            cv2.circle(frame, (foot_x, foot_y), 4, box_color, -1)

    cv2.imshow("Smart CCTV Stream", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()