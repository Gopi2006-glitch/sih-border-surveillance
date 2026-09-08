from datetime import datetime
import time
import cv2
import numpy as np
from ultralytics import YOLO
import requests

# 1. Load the YOLO model
model = YOLO('yolov8n.pt')

# 2. Open the CCTV video file
video_path = 'video/input/sample_cctv.mp4'
cap = cv2.VideoCapture(video_path)

if not cap.isOpened():
    print(f"❌ Could not open video at {video_path}.")
    exit()

print("✅ CCTV video opened successfully. Running Live Backend Integration...")

# Define a restricted zone polygon
restricted_zone = np.array([
    [100, 100], 
    [500, 100], 
    [500, 400], 
    [100, 400]
], np.int32)

# Cooldown dictionary to prevent spamming duplicate alerts for the same tracking ID
last_alert_time = {}
ALERT_COOLDOWN = 5  # Seconds between alerts for the same object

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        print("Video ended.")
        break

    # 3. Perform tracking
    results = model.track(frame, persist=True, tracker="bytetrack.yaml", verbose=False)
    annotated_frame = results[0].plot()

    # Draw the restricted zone on the frame
    cv2.polylines(annotated_frame, [restricted_zone], isClosed=True, color=(0, 165, 255), thickness=3)

    # 4. Check if objects enter the restricted zone
    if results[0].boxes.xyxy is not None and results[0].boxes.id is not None:
        boxes = results[0].boxes.xyxy.cpu().numpy()
        track_ids = results[0].boxes.id.int().cpu().tolist()
        classes = results[0].boxes.cls.int().cpu().tolist()

        for box, track_id, cls_id in zip(boxes, track_ids, classes):
            class_name = model.names[cls_id]
            
            if class_name in ["person", "car", "truck", "bus"]:
                x1, y1, x2, y2 = box
                center_x = int((x1 + x2) / 2)
                center_y = int(y2)
                
                is_inside = cv2.pointPolygonTest(restricted_zone, (center_x, center_y), False)
                
                if is_inside >= 0:
                    current_time = time.time()
                    
                    # Send alert only if the cooldown has passed for this specific tracking ID
                    if track_id not in last_alert_time or (current_time - last_alert_time[track_id]) > ALERT_COOLDOWN:
                        last_alert_time[track_id] = current_time
                        
                        alert_msg = f"🚨 ALERT: {class_name.upper()} (ID: {track_id}) entered the restricted zone!"
                        print(alert_msg)
                        
                        # 5. Send HTTP POST request to FastAPI backend
                        try:
                            payload = {
                                "camera_id": "CAM-01",
                                "event_type": f"{class_name.capitalize()} entered restricted zone",
                                "confidence": 0.92
                            }
                            response = requests.post("http://127.0.0.1:8000/alerts/", json=payload)
                            if response.status_code == 200:
                                print("✅ Alert successfully saved to database via API!")
                        except Exception as e:
                            print(f"❌ Failed to connect to backend: {e}")

                    cv2.putText(annotated_frame, f"WARNING: {class_name} ID {track_id}!", (10, 50),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

    cv2.imshow("Border Surveillance - Integrated System", annotated_frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
print("✅ Video processing stopped.")