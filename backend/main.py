import os
import cv2
import sqlite3
import numpy as np
from datetime import datetime
from typing import Optional
from ultralytics import YOLO

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="BSAIS Security Backend - Multi-Camera")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load YOLO model once globally to optimize CPU/RAM usage
MODEL = YOLO("yolov8n.pt")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(BASE_DIR, "database.db")
INPUT_DIR = os.path.join(BASE_DIR, "video", "input")

def get_video_file(name: str):
    target = os.path.join(INPUT_DIR, name)
    if os.path.exists(target):
        return target
    return os.path.join(INPUT_DIR, "sample_cctv.mp4")

CAMERA_SOURCES = {
    "CAM_01": get_video_file("cam_1.mp4"),
    "CAM_02": get_video_file("cam_2.mp4"),
    "CAM_03": get_video_file("cam_3.mp4"),
    "CAM_04": get_video_file("cam_4.mp4")
}

# Coordinate definitions calibrated for 640px frame width
ZONES = {
    "CAM_01": np.array([[592, 382], [861, 369], [838, 639], [564, 615]], np.int32),
    "CAM_02": np.array([[200, 200], [600, 200], [600, 500], [200, 500]], np.int32),
    "CAM_03": np.array([[300, 300], [700, 300], [700, 600], [300, 600]], np.int32),
    "CAM_04": np.array([[150, 150], [550, 150], [550, 550], [150, 550]], np.int32)
}

alerted_ids = {
    "CAM_01": set(),
    "CAM_02": set(),
    "CAM_03": set(),
    "CAM_04": set()
}

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS threats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            camera_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            track_id INTEGER,
            description TEXT,
            timestamp TEXT NOT NULL,
            status TEXT DEFAULT 'unreviewed'
        )
    """)
    conn.commit()
    conn.close()

init_db()

class BreachEventCreate(BaseModel):
    camera_id: str
    event_type: str = "Restricted Zone Breach"
    track_id: int
    description: Optional[str] = None
    status: str = "unreviewed"

def insert_breach_event(camera_id: str, track_id: int, event_type: str = "Restricted Zone Breach"):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    description = f"Target detected entering monitored boundary on {camera_id}."
    
    cursor.execute("""
        INSERT INTO threats (camera_id, event_type, track_id, description, timestamp, status)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (camera_id, event_type, track_id, description, current_time, "unreviewed"))
    
    conn.commit()
    conn.close()

def generate_frames_for_cam(camera_id: str):
    video_path = CAMERA_SOURCES.get(camera_id)
    zone_polygon = ZONES.get(camera_id, ZONES["CAM_01"])
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[{camera_id}] Error: Unable to open {video_path}")
        return

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = cap.read()
            if not ret:
                break

        h, w = frame.shape[:2]
        target_w = 640
        target_h = int(h * (target_w / w))
        frame = cv2.resize(frame, (target_w, target_h))

        results = MODEL.track(
            source=frame,
            persist=True,
            tracker="bytetrack.yaml",
            classes=[0],
            verbose=False
        )

        cv2.polylines(frame, [zone_polygon], isClosed=True, color=(0, 0, 255), thickness=2)
        cv2.putText(frame, f"{camera_id} RESTRICTED", (zone_polygon[0][0], max(zone_polygon[0][1] - 8, 20)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 2)

        if results[0].boxes is not None and results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy().astype(int)
            track_ids = results[0].boxes.id.cpu().numpy().astype(int)

            for box, track_id in zip(boxes, track_ids):
                x1, y1, x2, y2 = box
                center_x = int((x1 + x2) / 2)
                bottom_y = int(y2)

                is_inside = cv2.pointPolygonTest(zone_polygon, (center_x, bottom_y), False) >= 0

                if is_inside:
                    box_color = (0, 0, 255)
                    clean_id = int(track_id)
                    if clean_id not in alerted_ids[camera_id] and clean_id > 0:
                        alerted_ids[camera_id].add(clean_id)
                        insert_breach_event(camera_id, clean_id)
                else:
                    box_color = (0, 255, 0)

                cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
                cv2.putText(frame, f"ID:{track_id}", (x1, y1 - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, box_color, 2)

        cv2.putText(frame, f"{camera_id} - LIVE", (15, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")

    cap.release()

@app.get("/video_feed/{camera_id}")
def video_feed(camera_id: str):
    valid_cam = camera_id.upper()
    if valid_cam not in CAMERA_SOURCES:
        valid_cam = "CAM_01"
    return StreamingResponse(
        generate_frames_for_cam(valid_cam),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.get("/api/alerts/unreviewed")
def get_unreviewed_alerts():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, camera_id, event_type, track_id, description, timestamp, status 
        FROM threats 
        WHERE status = 'unreviewed'
        ORDER BY id DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    alerts = []
    for row in rows:
        alerts.append({
            "id": int(row[0]),
            "camera_id": str(row[1]),
            "event_type": str(row[2]),
            "track_id": int(row[3]) if row[3] is not None and str(row[3]).isdigit() else 0,
            "description": str(row[4]),
            "timestamp": str(row[5]),
            "status": str(row[6])
        })
    return alerts

@app.post("/api/events")
def create_event(event: BreachEventCreate):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    desc = event.description or f"Target entering monitored boundary on {event.camera_id}."

    cursor.execute("""
        INSERT INTO threats (camera_id, event_type, track_id, description, timestamp, status)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (event.camera_id, event.event_type, int(event.track_id), desc, current_time, event.status))
    
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()

    return {"status": "success", "event_id": new_id, "timestamp": current_time}

@app.patch("/api/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE threats SET status = 'reviewed' WHERE id = ?", (int(alert_id),))
    conn.commit()
    conn.close()
    return {"status": "success", "alert_id": alert_id}
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)