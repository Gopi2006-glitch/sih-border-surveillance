import cv2
import requests
from ultralytics import YOLO
import numpy as np

# 1. Load YOLO model
model = YOLO("yolov8n.pt")

# 2. Target video path (change to 0 if testing via webcam)
VIDEO_PATH = "video/input/sample_cctv.mp4"
cap = cv2.VideoCapture(VIDEO_PATH)

# FastAPI endpoint
API_URL = "http://127.0.0.1:8001/events"

# 3. Expanded Restricted Polygon Zone covering most of the active walking area
# Format: [ [x1, y1], [x2, y2], [x3, y3], [x4, y4] ]
ZONE_POLYGON = np.array([
    [592, 382],   # Top-left
    [861, 369],   # Top-right
    [838, 639],   # Bottom-right
    [564, 615]    # Bottom-left
], np.int32)

# Set to prevent duplicate alerts for the same tracked person
alerted_ids = set()

def send_alert(track_id):
    payload = {
        "mode": "Restricted Zone Breach",
        "description": f"Person (Track ID: {track_id}) crossed into restricted zone.",
        "status": "unreviewed"
    }
    try:
        requests.post(API_URL, json=payload, timeout=0.5)
    except Exception as e:
        print(f"[Warning] Backend unreachable: {e}")

# Helper: Left-click anywhere on the video window to print exact pixel coordinates
def print_coords(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        print(f"Clicked coordinate: [{x}, {y}]")

cv2.namedWindow("BSAIS CCTV Tracking")
cv2.setMouseCallback("BSAIS CCTV Tracking", print_coords)

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    # Run YOLO tracking (filtered to class 0: Person)
    results = model.track(
        source=frame,
        persist=True,
        tracker="bytetrack.yaml",
        classes=[0],
        verbose=False
    )

    # Draw the Restricted Zone boundary on the frame
    cv2.polylines(frame, [ZONE_POLYGON], isClosed=True, color=(0, 0, 255), thickness=2)
    cv2.putText(frame, "RESTRICTED ZONE", (ZONE_POLYGON[0][0], max(ZONE_POLYGON[0][1] - 10, 20)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    # Check detections and tracked IDs
    if results[0].boxes is not None and results[0].boxes.id is not None:
        boxes = results[0].boxes.xyxy.cpu().numpy().astype(int)
        track_ids = results[0].boxes.id.cpu().numpy().astype(int)

        for box, track_id in zip(boxes, track_ids):
            x1, y1, x2, y2 = box

            # Track using the bottom-center point (person's feet)
            center_x = int((x1 + x2) / 2)
            bottom_y = int(y2)

            # Check if this point falls inside the polygon
            is_inside = cv2.pointPolygonTest(ZONE_POLYGON, (center_x, bottom_y), False) >= 0

            if is_inside:
                box_color = (0, 0, 255)  # Red for breach
                if track_id not in alerted_ids:
                    alerted_ids.add(track_id)
                    send_alert(track_id)
            else:
                box_color = (0, 255, 0)  # Green for safe

            # Draw bounding box and track ID
            cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
            cv2.circle(frame, (center_x, bottom_y), 4, (255, 255, 0), -1)
            cv2.putText(
                frame,
                f"ID: {track_id}",
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                box_color,
                2
            )

    cv2.imshow("BSAIS CCTV Tracking", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()