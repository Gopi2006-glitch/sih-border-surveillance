import cv2
import time
import os
import uuid
import numpy as np
from collections import defaultdict, deque
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from ultralytics import YOLO
import sys

# ----------------- PATH & BUS IMPORTS -----------------
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(BASE_DIR)

from backend.database.alerts_db import insert_alert, ALERTS_DIR
try:
    from backend.services.notifier import send_telegram_alert_async
except ImportError:
    def send_telegram_alert_async(*args, **kwargs):
        pass

app = FastAPI(title="Border Sentinel Streaming Server with High-Vis Overlays")

os.makedirs(ALERTS_DIR, exist_ok=True)
app.mount("/alerts_static", StaticFiles(directory=ALERTS_DIR), name="alerts_static")

# ----------------- MODEL & CONFIGURATION -----------------
model = YOLO("yolov8n.pt")
TARGET_CLASSES = [0, 2, 3, 5, 7]  # 0: Person, 2: Car, 3: Motorcycle, 5: Bus, 7: Truck

cams_config = {
    "cam_1": {"path": os.path.join(BASE_DIR, "video", "input", "cam_1.mp4"), "name": "CAM-01", "sector": "Sector A"},
    "cam_2": {"path": os.path.join(BASE_DIR, "video", "input", "cam_2.mp4"), "name": "CAM-02", "sector": "Sector B"},
    "cam_3": {"path": os.path.join(BASE_DIR, "video", "input", "cam_3.mp4"), "name": "CAM-03", "sector": "Sector A"},
    "cam_4": {"path": os.path.join(BASE_DIR, "video", "input", "cam_4.mp4"), "name": "CAM-04", "sector": "Sector B"},
}

cam_enabled = {k: True for k in cams_config}

# ----------------- FALLBACK BUFFERS -----------------
standby_img = np.full((270, 480, 3), 16, dtype=np.uint8)
cv2.putText(standby_img, "CAMERA FEED DISABLED", (110, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (100, 116, 139), 2)
_, standby_buf = cv2.imencode('.jpg', standby_img, [cv2.IMWRITE_JPEG_QUALITY, 45])
STANDBY_BYTES = standby_buf.tobytes()

no_signal_img = np.full((270, 480, 3), 20, dtype=np.uint8)
cv2.putText(no_signal_img, "NO SIGNAL / SOURCE NOT FOUND", (60, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (68, 68, 239), 2)
_, err_buf = cv2.imencode('.jpg', no_signal_img, [cv2.IMWRITE_JPEG_QUALITY, 45])
NO_SIGNAL_BYTES = err_buf.tobytes()


class ToggleRequest(BaseModel):
    enabled: bool


@app.post("/camera/{cam_id}/toggle")
def toggle_camera(cam_id: str, req: ToggleRequest):
    if cam_id in cam_enabled:
        cam_enabled[cam_id] = req.enabled
        return {"cam_id": cam_id, "status": "active" if req.enabled else "paused"}
    return {"error": "Camera not found"}, 404


def calculate_direction(history: deque):
    """Calculate movement vector from recent coordinate history."""
    if len(history) < 6:
        return "Stationary", (148, 163, 184)

    start_pt = history[0]
    end_pt = history[-1]
    dy = end_pt[1] - start_pt[1]
    dx = end_pt[0] - start_pt[0]

    if abs(dy) < 8 and abs(dx) < 8:
        return "Stationary", (148, 163, 184)
    elif dy > 10:
        return "INBOUND [Approaching]", (0, 0, 255)       # Red in BGR
    elif dy < -10:
        return "OUTBOUND [Retreating]", (0, 220, 100)     # Green in BGR
    elif dx > 10:
        return "LATERAL [Eastbound]", (0, 190, 255)       # Amber in BGR
    else:
        return "LATERAL [Westbound]", (0, 190, 255)       # Amber in BGR


def generate_frames(cam_id: str):
    config = cams_config.get(cam_id)
    if not config:
        while True:
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + NO_SIGNAL_BYTES + b'\r\n')
            time.sleep(1.0)

    video_path = config["path"]
    if not os.path.exists(video_path):
        while True:
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + NO_SIGNAL_BYTES + b'\r\n')
            time.sleep(1.0)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        while True:
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + NO_SIGNAL_BYTES + b'\r\n')
            time.sleep(1.0)

    track_history = defaultdict(lambda: deque(maxlen=25))
    alerted_track_ids = {}
    cached_boxes = []
    frame_idx = 0

    while True:
        if not cam_enabled.get(cam_id, True):
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + STANDBY_BYTES + b'\r\n')
            time.sleep(0.15)
            continue

        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.02)
                continue

        frame_idx += 1
        resized = cv2.resize(frame, (480, 270), interpolation=cv2.INTER_LINEAR)
        now = time.time()

        # Run ByteTrack tracking every 2 frames
        if frame_idx % 2 == 0:
            results = model.track(
                resized,
                persist=True,
                classes=TARGET_CLASSES,
                conf=0.30,
                imgsz=320,
                tracker="bytetrack.yaml",
                verbose=False
            )

            if results[0].boxes is not None and len(results[0].boxes) > 0:
                current_boxes = []
                boxes_xyxy = results[0].boxes.xyxy.cpu().numpy().astype(int)
                confs = results[0].boxes.conf.cpu().numpy()
                clss = results[0].boxes.cls.cpu().numpy().astype(int)

                if results[0].boxes.id is not None:
                    track_ids = results[0].boxes.id.cpu().numpy().astype(int)
                else:
                    track_ids = [i + 1 for i in range(len(boxes_xyxy))]

                for box, track_id, conf, cls_id in zip(boxes_xyxy, track_ids, confs, clss):
                    x1, y1, x2, y2 = box
                    cx = int((x1 + x2) / 2)
                    cy = int((y1 + y2) / 2)

                    history = track_history[track_id]
                    history.append((cx, cy))

                    label = "Person" if cls_id == 0 else "Vehicle"
                    direction_str, dir_color = calculate_direction(history)

                    # Only escalate to database and Telegram if INBOUND approaching with 30s cooldown
                    is_approaching = "INBOUND" in direction_str
                    last_time = alerted_track_ids.get(track_id, 0)

                    if label == "Person" and is_approaching and (now - last_time > 30.0):
                        crop_h, crop_w = resized.shape[:2]
                        crop = resized[max(0, y1):min(crop_h, y2), max(0, x1):min(crop_w, x2)]
                        if crop.size > 0:
                            filename = f"{cam_id}_id{track_id}_{uuid.uuid4().hex[:4]}.jpg"
                            filepath = os.path.join(ALERTS_DIR, filename)
                            cv2.imwrite(filepath, crop)

                            insert_alert(
                                cam_id=config["name"],
                                sector=config["sector"],
                                label=f"Person #{track_id} (INBOUND)",
                                confidence=float(conf),
                                severity="High",
                                thumbnail_path=filename,
                                track_id=track_id
                            )
                            alerted_track_ids[track_id] = now

                            send_telegram_alert_async(
                                cam_id=config["name"],
                                sector=config["sector"],
                                label=f"Perimeter Breach: Person #{track_id} Approaching",
                                confidence=float(conf),
                                image_path=filepath
                            )

                    current_boxes.append((box, track_id, conf, label, direction_str, dir_color, list(history)))

                if current_boxes:
                    cached_boxes = current_boxes

        # ----------------- RENDER NEON OVERLAYS & TRAILS -----------------
        for (box, track_id, conf, label, direction_str, dir_color, history_pts) in cached_boxes:
            x1, y1, x2, y2 = box

            # 1. Trajectory trail (Bright Cyan in BGR)
            if len(history_pts) > 1:
                pts = np.array(history_pts, dtype=np.int32).reshape((-1, 1, 2))
                cv2.polylines(resized, [pts], isClosed=False, color=(255, 255, 0), thickness=2)
                for p in history_pts[-3:]:
                    cv2.circle(resized, p, 3, (255, 255, 0), -1)

            # 2. Bounding Box - Vivid Neon Green for Person: (0, 255, 0) in BGR
            box_color = (0, 255, 0) if label == "Person" else (0, 180, 255)
            cv2.rectangle(resized, (x1, y1), (x2, y2), box_color, 2)

            # Corner brackets for tactical HUD design
            c_len = min(12, int((x2 - x1) / 4))
            cv2.line(resized, (x1, y1), (x1 + c_len, y1), (255, 255, 255), 2)
            cv2.line(resized, (x1, y1), (x1, y1 + c_len), (255, 255, 255), 2)
            cv2.line(resized, (x2, y1), (x2 - c_len, y1), (255, 255, 255), 2)
            cv2.line(resized, (x2, y1), (x2, y1 + c_len), (255, 255, 255), 2)

            # 3. Label tag badge (Neon Green background with dark text)
            header_tag = f"#{track_id} {label} {int(conf * 100)}%"
            label_bg_y = max(18, y1)
            text_size = cv2.getTextSize(header_tag, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)[0]
            cv2.rectangle(resized, (x1, label_bg_y - 18), (x1 + text_size[0] + 8, label_bg_y), box_color, -1)
            cv2.putText(resized, header_tag, (x1 + 4, label_bg_y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 1, cv2.LINE_AA)

            # 4. Movement vector direction tag
            cv2.putText(resized, direction_str, (x1, min(265, y2 + 14)), cv2.FONT_HERSHEY_SIMPLEX, 0.38, dir_color, 1, cv2.LINE_AA)

        _, buffer = cv2.imencode('.jpg', resized, [cv2.IMWRITE_JPEG_QUALITY, 55])
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

        time.sleep(0.01)


@app.get("/video/{cam_id}")
def video_feed(cam_id: str):
    return StreamingResponse(
        generate_frames(cam_id),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)