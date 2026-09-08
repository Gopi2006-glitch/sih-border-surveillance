import sqlite3
from datetime import datetime
import cv2
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from ultralytics import YOLO

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

model = YOLO("yolov8n.pt")

# --- Initialize SQLite Database ---
def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS threats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mode TEXT,
            description TEXT,
            timestamp TEXT,
            status TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

@app.get("/api/telemetry")
def get_telemetry():
    return {
        "ai_model": "YOLOv8n (Optimized)",
        "tracker_engine": "ByteTrack Active",
        "primary_feed": "CAM-01 (1920x1080)",
        "database_protocol": "SQLite / BaaSAPI",
        "zone_security": "RESTRICTED BOUNDARY ARMED",
        "cameras": [
            {"name": "CAM-01 (Sector Alpha)", "status": "ONLINE"},
            {"name": "CAM-02 (Sector Beta)", "status": "ONLINE"}
        ]
    }

@app.get("/api/threats")
def get_threats():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM threats ORDER BY id DESC LIMIT 10")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def generate_frames():
    video_path = "video/input/sample_cctv.mp4"
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        print(f"Error: Could not open video file at {video_path}")
        return

    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue

        results = model(frame, stream=True)
        annotated_frame = frame
        
        for r in results:
            annotated_frame = r.plot()
            # Check if any person (class 0) is detected to log a threat example
            for box in r.boxes:
                cls_id = int(box.cls[0])
                if cls_id == 0:  # 'person' class in YOLO COCO dataset
                    # Optional: Log to DB here with debouncing logic if needed
                    pass

        ret, buffer = cv2.imencode('.jpg', annotated_frame)
        if not ret:
            continue
        
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

    cap.release()

@app.get("/video_feed")
def video_feed():
    return StreamingResponse(generate_frames(), media_type="multipart/x-mixed-replace; boundary=frame")