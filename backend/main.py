import os
import cv2
import time
import sqlite3
import threading
import numpy as np

from datetime import datetime
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from ultralytics import YOLO


# ============================================================
# APPLICATION
# ============================================================

app = FastAPI(
    title="BSAIS - Border Sentinel AI Surveillance",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

DB_FILE = os.path.join(BASE_DIR, "database.db")
INPUT_DIR = os.path.join(BASE_DIR, "video", "input")

MODEL_PATH = os.path.join(BASE_DIR, "yolov8n.pt")


# ============================================================
# YOLO MODEL
# ============================================================

print("[BSAIS] Loading YOLO model...")

MODEL = YOLO(MODEL_PATH)

print("[BSAIS] YOLO model loaded.")


# Prevent simultaneous YOLO inference from multiple
# camera streaming threads.
MODEL_LOCK = threading.Lock()


# ============================================================
# CAMERA CONFIGURATION
# ============================================================

CAMERA_SOURCES = {
    "CAM_01": os.path.join(INPUT_DIR, "cam_1.mp4"),
    "CAM_02": os.path.join(INPUT_DIR, "cam_2.mp4"),
    "CAM_03": os.path.join(INPUT_DIR, "cam_3.mp4"),
    "CAM_04": os.path.join(INPUT_DIR, "cam_4.mp4"),
}


CAMERA_INFO = {
    "CAM_01": {
        "name": "CAM-01",
        "sector": "Sector A",
        "location": "Northern Perimeter",
    },
    "CAM_02": {
        "name": "CAM-02",
        "sector": "Sector B",
        "location": "Forest Corridor",
    },
    "CAM_03": {
        "name": "CAM-03",
        "sector": "Sector A",
        "location": "Western Perimeter",
    },
    "CAM_04": {
        "name": "CAM-04",
        "sector": "Sector C",
        "location": "Southern Road",
    },
}


# ============================================================
# CAMERA POWER STATE
# ============================================================

camera_power = {
    "CAM_01": True,
    "CAM_02": True,
    "CAM_03": True,
    "CAM_04": True,
}


camera_state_lock = threading.Lock()


# ============================================================
# DETECTION CLASSES
# ============================================================

TARGET_CLASSES = [
    0,                  # person
    2, 3, 5, 7,         # car, motorcycle, bus, truck
    14, 15, 16, 17, 18, 19, 20, 21, 22, 23,
    43                  # knife
]


VEHICLES = {
    "car",
    "motorcycle",
    "bus",
    "truck"
}


ANIMALS = {
    "bird",
    "cat",
    "dog",
    "horse",
    "sheep",
    "cow",
    "elephant",
    "bear",
    "zebra",
    "giraffe"
}


# ============================================================
# RESTRICTED ZONES
# ============================================================

ZONES = {
    "CAM_01": np.array(
        [[100, 150], [540, 150], [540, 340], [100, 340]],
        np.int32
    ),

    "CAM_02": np.array(
        [[150, 120], [500, 120], [500, 320], [150, 320]],
        np.int32
    ),

    "CAM_03": np.array(
        [[80, 100], [560, 100], [560, 330], [80, 330]],
        np.int32
    ),

    "CAM_04": np.array(
        [[120, 120], [520, 120], [520, 320], [120, 320]],
        np.int32
    ),
}


# ============================================================
# TRACK / ALERT MEMORY
# ============================================================

alerted_ids = {
    "CAM_01": set(),
    "CAM_02": set(),
    "CAM_03": set(),
    "CAM_04": set(),
}


# ============================================================
# STATISTICS
# ============================================================

runtime_stats = {
    "CAM_01": {
        "frames": 0,
        "detections": 0,
        "fps": 0,
        "last_detection": None,
    },

    "CAM_02": {
        "frames": 0,
        "detections": 0,
        "fps": 0,
        "last_detection": None,
    },

    "CAM_03": {
        "frames": 0,
        "detections": 0,
        "fps": 0,
        "last_detection": None,
    },

    "CAM_04": {
        "frames": 0,
        "detections": 0,
        "fps": 0,
        "last_detection": None,
    },
}


stats_lock = threading.Lock()


# ============================================================
# DATABASE
# ============================================================

def get_db():
    return sqlite3.connect(
        DB_FILE,
        timeout=10.0
    )


def init_db():

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS threats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            camera_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            track_id INTEGER,
            description TEXT,
            timestamp TEXT NOT NULL,
            status TEXT DEFAULT 'unreviewed'
        )
        """
    )

    conn.commit()
    conn.close()


init_db()


# ============================================================
# PYDANTIC MODELS
# ============================================================

class BreachEventCreate(BaseModel):

    camera_id: str

    event_type: str = "Restricted Zone Breach"

    track_id: int = 0

    description: Optional[str] = None

    status: str = "unreviewed"


# ============================================================
# HELPERS
# ============================================================

def camera_exists(camera_id: str) -> bool:

    return camera_id.upper() in CAMERA_SOURCES


def is_camera_on(camera_id: str) -> bool:

    with camera_state_lock:

        return camera_power.get(
            camera_id,
            False
        )


def set_camera_power(
    camera_id: str,
    state: bool
):

    with camera_state_lock:

        camera_power[camera_id] = state


def categorize_label(class_name: str) -> str:

    if class_name == "knife":
        return "Weapon Detected"

    if class_name == "person":
        return "Person Detected"

    if class_name in VEHICLES:
        return "Vehicle Detected"

    if class_name in ANIMALS:
        return "Wildlife Detected"

    return "Object Detected"


def get_severity(class_name: str) -> str:

    if class_name == "knife":
        return "Critical"

    if class_name == "person":
        return "High"

    if class_name in VEHICLES:
        return "Medium"

    return "Low"


# ============================================================
# DATABASE EVENT INSERT
# ============================================================

def insert_breach_event(
    camera_id: str,
    track_id: int,
    class_name: str
):

    try:

        conn = get_db()
        cursor = conn.cursor()

        current_time = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        event_type = categorize_label(
            class_name
        )

        description = (
            f"{event_type} detected on {camera_id}."
        )

        cursor.execute(
            """
            INSERT INTO threats
            (
                camera_id,
                event_type,
                track_id,
                description,
                timestamp,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                camera_id,
                event_type,
                track_id,
                description,
                current_time,
                "unreviewed"
            )
        )

        conn.commit()
        conn.close()

    except Exception as e:

        print(
            f"[DATABASE] Insert error: {e}"
        )


# ============================================================
# OFFLINE FRAME
# ============================================================

def create_offline_frame(camera_id):

    frame = np.zeros(
        (360, 640, 3),
        dtype=np.uint8
    )

    frame[:] = (7, 20, 35)

    cv2.putText(
        frame,
        camera_id,
        (30, 100),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.2,
        (255, 255, 255),
        2
    )

    cv2.putText(
        frame,
        "CAMERA OFFLINE",
        (30, 160),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 0, 255),
        2
    )

    cv2.putText(
        frame,
        "Turn camera ON from dashboard",
        (30, 215),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (180, 180, 180),
        1
    )

    return frame


# ============================================================
# CAMERA FRAME GENERATOR
# ============================================================

def generate_frames_for_cam(
    camera_id: str
):

    video_path = CAMERA_SOURCES.get(
        camera_id
    )

    zone_polygon = ZONES.get(
        camera_id,
        ZONES["CAM_01"]
    )

    cap = None

    frame_count = 0

    cached_boxes = []

    cached_tracks = []

    cached_classes = []

    last_time = time.time()

    try:

        while True:

            # ------------------------------------------------
            # CAMERA OFF
            # ------------------------------------------------

            if not is_camera_on(camera_id):

                if cap is not None:

                    cap.release()
                    cap = None

                frame = create_offline_frame(
                    camera_id
                )

                success, buffer = cv2.imencode(
                    ".jpg",
                    frame,
                    [
                        cv2.IMWRITE_JPEG_QUALITY,
                        70
                    ]
                )

                if success:

                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n"
                        + buffer.tobytes()
                        + b"\r\n"
                    )

                time.sleep(0.15)

                continue

            # ------------------------------------------------
            # OPEN CAMERA
            # ------------------------------------------------

            if cap is None:

                cap = cv2.VideoCapture(
                    video_path
                )

                if not cap.isOpened():

                    frame = create_offline_frame(
                        camera_id
                    )

                    cv2.putText(
                        frame,
                        "VIDEO SOURCE ERROR",
                        (30, 270),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 0, 255),
                        2
                    )

                    success, buffer = cv2.imencode(
                        ".jpg",
                        frame
                    )

                    if success:

                        yield (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n\r\n"
                            + buffer.tobytes()
                            + b"\r\n"
                        )

                    time.sleep(1)

                    continue

            # ------------------------------------------------
            # READ FRAME
            # ------------------------------------------------

            ret, frame = cap.read()

            if not ret:

                cap.set(
                    cv2.CAP_PROP_POS_FRAMES,
                    0
                )

                ret, frame = cap.read()

                if not ret:

                    cap.release()
                    cap = None

                    time.sleep(1)

                    continue

            frame = cv2.resize(
                frame,
                (640, 360)
            )

            frame_count += 1

            # ------------------------------------------------
            # YOLO
            # ------------------------------------------------

            if frame_count % 2 == 0:

                try:

                    with MODEL_LOCK:

                        results = MODEL.track(
                            source=frame,
                            persist=True,
                            tracker="bytetrack.yaml",
                            classes=TARGET_CLASSES,
                            verbose=False
                        )

                    result = results[0]

                    if (
                        result.boxes is not None
                        and result.boxes.id is not None
                    ):

                        cached_boxes = (
                            result.boxes.xyxy
                            .cpu()
                            .numpy()
                            .astype(int)
                        )

                        cached_tracks = (
                            result.boxes.id
                            .cpu()
                            .numpy()
                            .astype(int)
                        )

                        cached_classes = (
                            result.boxes.cls
                            .cpu()
                            .numpy()
                            .astype(int)
                        )

                    else:

                        cached_boxes = []
                        cached_tracks = []
                        cached_classes = []

                except Exception as e:

                    print(
                        f"[YOLO] {camera_id}: {e}"
                    )

            # ------------------------------------------------
            # DRAW RESTRICTED ZONE
            # ------------------------------------------------

            cv2.polylines(
                frame,
                [zone_polygon],
                isClosed=True,
                color=(0, 0, 255),
                thickness=2
            )

            # ------------------------------------------------
            # PROCESS DETECTIONS
            # ------------------------------------------------

            detection_count = 0

            for (
                box,
                track_id,
                cls_idx
            ) in zip(
                cached_boxes,
                cached_tracks,
                cached_classes
            ):

                x1, y1, x2, y2 = box

                center_x = int(
                    (x1 + x2) / 2
                )

                bottom_y = int(y2)

                class_name = MODEL.names.get(
                    int(cls_idx),
                    "target"
                )

                inside_zone = (
                    cv2.pointPolygonTest(
                        zone_polygon,
                        (
                            center_x,
                            bottom_y
                        ),
                        False
                    ) >= 0
                )

                is_critical = (
                    class_name == "knife"
                )

                detection_count += 1

                if inside_zone or is_critical:

                    box_color = (
                        0,
                        0,
                        255
                    )

                    clean_id = int(
                        track_id
                    )

                    if (
                        clean_id > 0
                        and clean_id
                        not in alerted_ids[camera_id]
                    ):

                        alerted_ids[
                            camera_id
                        ].add(clean_id)

                        insert_breach_event(
                            camera_id,
                            clean_id,
                            class_name
                        )

                else:

                    box_color = (
                        0,
                        255,
                        0
                    )

                label = (
                    f"{class_name.upper()} "
                    f"#{track_id}"
                )

                cv2.rectangle(
                    frame,
                    (x1, y1),
                    (x2, y2),
                    box_color,
                    2
                )

                cv2.putText(
                    frame,
                    label,
                    (
                        x1,
                        max(
                            y1 - 7,
                            15
                        )
                    ),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    box_color,
                    2
                )

            # ------------------------------------------------
            # CAMERA LABEL
            # ------------------------------------------------

            cv2.putText(
                frame,
                f"{camera_id} - LIVE",
                (15, 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2
            )

            # ------------------------------------------------
            # UPDATE STATS
            # ------------------------------------------------

            current_time = time.time()

            elapsed = (
                current_time - last_time
            )

            if elapsed >= 1:

                calculated_fps = (
                    frame_count / elapsed
                )

                with stats_lock:

                    runtime_stats[
                        camera_id
                    ]["fps"] = round(
                        min(
                            calculated_fps,
                            60
                        ),
                        1
                    )

                    runtime_stats[
                        camera_id
                    ]["frames"] = frame_count

                    runtime_stats[
                        camera_id
                    ]["detections"] = (
                        detection_count
                    )

                frame_count = 0

                last_time = current_time

            # ------------------------------------------------
            # JPEG
            # ------------------------------------------------

            success, buffer = cv2.imencode(
                ".jpg",
                frame,
                [
                    cv2.IMWRITE_JPEG_QUALITY,
                    65
                ]
            )

            if not success:
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + buffer.tobytes()
                + b"\r\n"
            )

            time.sleep(0.025)

    finally:

        if cap is not None:

            cap.release()


# ============================================================
# ROOT
# ============================================================

@app.get("/")
def root():

    return {
        "name": "Border Sentinel AI Surveillance System",
        "status": "online",
        "version": "2.0.0"
    }


# ============================================================
# SYSTEM STATUS
# ============================================================

@app.get("/api/system/status")
def system_status():

    with camera_state_lock:

        cameras = list(
            camera_power.values()
        )

    return {
        "system": "online",
        "uptime": "99.8%",
        "total_cameras": len(
            CAMERA_SOURCES
        ),
        "online_cameras": sum(
            1 for state in cameras
            if state
        ),
        "timestamp": datetime.now().isoformat()
    }


# ============================================================
# CAMERAS
# ============================================================

@app.get("/api/cameras")
def get_cameras():

    result = []

    for camera_id, source in CAMERA_SOURCES.items():

        exists = os.path.exists(source)

        result.append({
            "id": camera_id,
            "name": CAMERA_INFO[camera_id]["name"],
            "sector": CAMERA_INFO[camera_id]["sector"],
            "location": CAMERA_INFO[camera_id]["location"],
            "source_available": exists,
            "online": is_camera_on(camera_id),
            "stream_url": (
                f"/video_feed/{camera_id}"
            ),
            "fps": runtime_stats[
                camera_id
            ]["fps"],
            "detections": runtime_stats[
                camera_id
            ]["detections"],
        })

    return result


@app.get("/api/cameras/{camera_id}")
def get_camera(camera_id: str):

    camera_id = camera_id.upper()

    if not camera_exists(camera_id):

        return JSONResponse(
            status_code=404,
            content={
                "error": "Camera not found"
            }
        )

    return {
        "id": camera_id,
        "name": CAMERA_INFO[camera_id]["name"],
        "sector": CAMERA_INFO[camera_id]["sector"],
        "location": CAMERA_INFO[camera_id]["location"],
        "online": is_camera_on(camera_id),
        "source_available": os.path.exists(
            CAMERA_SOURCES[camera_id]
        ),
        "stream_url": (
            f"/video_feed/{camera_id}"
        ),
        "fps": runtime_stats[
            camera_id
        ]["fps"],
        "detections": runtime_stats[
            camera_id
        ]["detections"],
    }


# ============================================================
# CAMERA ON
# ============================================================

@app.post("/api/cameras/{camera_id}/on")
def camera_on(camera_id: str):

    camera_id = camera_id.upper()

    if not camera_exists(camera_id):

        return JSONResponse(
            status_code=404,
            content={
                "error": "Camera not found"
            }
        )

    set_camera_power(
        camera_id,
        True
    )

    return {
        "status": "success",
        "camera_id": camera_id,
        "online": True
    }


# ============================================================
# CAMERA OFF
# ============================================================

@app.post("/api/cameras/{camera_id}/off")
def camera_off(camera_id: str):

    camera_id = camera_id.upper()

    if not camera_exists(camera_id):

        return JSONResponse(
            status_code=404,
            content={
                "error": "Camera not found"
            }
        )

    set_camera_power(
        camera_id,
        False
    )

    return {
        "status": "success",
        "camera_id": camera_id,
        "online": False
    }


# ============================================================
# LIVE VIDEO
# ============================================================

@app.get("/video_feed/{camera_id}")
def video_feed(camera_id: str):

    camera_id = camera_id.upper()

    if not camera_exists(camera_id):

        camera_id = "CAM_01"

    return StreamingResponse(
        generate_frames_for_cam(
            camera_id
        ),
        media_type=(
            "multipart/x-mixed-replace; "
            "boundary=frame"
        )
    )


# ============================================================
# ALERTS
# ============================================================

@app.get("/api/alerts")
def get_alerts():

    try:

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                id,
                camera_id,
                event_type,
                track_id,
                description,
                timestamp,
                status
            FROM threats
            ORDER BY id DESC
            LIMIT 100
            """
        )

        rows = cursor.fetchall()

        conn.close()

        alerts = []

        for row in rows:

            event_type = str(
                row[2]
            )

            if "Weapon" in event_type:

                severity = "Critical"

            elif "Person" in event_type:

                severity = "High"

            elif "Vehicle" in event_type:

                severity = "Medium"

            else:

                severity = "Low"

            alerts.append({

                "id": int(row[0]),

                "camera_id": str(
                    row[1]
                ),

                "event_type": event_type,

                "track_id": (
                    int(row[3])
                    if row[3] is not None
                    else 0
                ),

                "description": str(
                    row[4]
                ),

                "timestamp": str(
                    row[5]
                ),

                "status": str(
                    row[6]
                ),

                "severity": severity,

                "reviewed": (
                    row[6] == "reviewed"
                ),
            })

        return alerts

    except Exception as e:

        print(
            f"[ALERTS] Read error: {e}"
        )

        return []


# ============================================================
# UNREVIEWED ALERTS
# ============================================================

@app.get("/api/alerts/unreviewed")
def get_unreviewed_alerts():

    alerts = get_alerts()

    return [
        alert
        for alert in alerts
        if not alert["reviewed"]
    ]


# ============================================================
# ACKNOWLEDGE ALERT
# ============================================================

@app.patch(
    "/api/alerts/{alert_id}/acknowledge"
)
def acknowledge_alert(
    alert_id: int
):

    try:

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE threats
            SET status = 'reviewed'
            WHERE id = ?
            """,
            (int(alert_id),)
        )

        conn.commit()

        updated = cursor.rowcount

        conn.close()

        return {
            "status": "success",
            "alert_id": alert_id,
            "updated": updated > 0
        }

    except Exception as e:

        return JSONResponse(
            status_code=500,
            content={
                "error": str(e)
            }
        )


# ============================================================
# CREATE EVENT
# ============================================================

@app.post("/api/events")
def create_event(
    event: BreachEventCreate
):

    try:

        camera_id = event.camera_id.upper()

        conn = get_db()
        cursor = conn.cursor()

        current_time = (
            datetime.now()
            .strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )

        description = (
            event.description
            or
            f"Target detected on {camera_id}."
        )

        cursor.execute(
            """
            INSERT INTO threats
            (
                camera_id,
                event_type,
                track_id,
                description,
                timestamp,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                camera_id,
                event.event_type,
                int(event.track_id),
                description,
                current_time,
                event.status
            )
        )

        conn.commit()

        new_id = cursor.lastrowid

        conn.close()

        return {
            "status": "success",
            "event_id": new_id,
            "timestamp": current_time
        }

    except Exception as e:

        return JSONResponse(
            status_code=500,
            content={
                "error": str(e)
            }
        )


# ============================================================
# DETECTIONS
# ============================================================

@app.get("/api/detections")
def get_detections():

    try:

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                id,
                camera_id,
                event_type,
                track_id,
                description,
                timestamp,
                status
            FROM threats
            ORDER BY id DESC
            LIMIT 200
            """
        )

        rows = cursor.fetchall()

        conn.close()

        detections = []

        for row in rows:

            event_type = str(
                row[2]
            )

            if "Person" in event_type:

                detection_type = "Person"

            elif "Vehicle" in event_type:

                detection_type = "Vehicle"

            elif "Wildlife" in event_type:

                detection_type = "Animal"

            elif "Weapon" in event_type:

                detection_type = "Weapon"

            else:

                detection_type = "Other"

            detections.append({

                "id": int(row[0]),

                "camera_id": str(
                    row[1]
                ),

                "type": detection_type,

                "event_type": event_type,

                "track_id": (
                    int(row[3])
                    if row[3] is not None
                    else 0
                ),

                "description": str(
                    row[4]
                ),

                "timestamp": str(
                    row[5]
                ),

                "status": str(
                    row[6]
                ),

            })

        return detections

    except Exception as e:

        print(
            f"[DETECTIONS] Error: {e}"
        )

        return []


# ============================================================
# HISTORY
# ============================================================

@app.get("/api/history")
def get_history():

    return get_detections()


# ============================================================
# STATISTICS
# ============================================================

@app.get("/api/statistics")
def get_statistics():

    try:

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT event_type, COUNT(*)
            FROM threats
            GROUP BY event_type
            """
        )

        rows = cursor.fetchall()

        conn.close()

        person = 0
        vehicle = 0
        animal = 0
        weapon = 0
        other = 0

        for event_type, count in rows:

            event_type = str(
                event_type
            )

            if "Person" in event_type:

                person += count

            elif "Vehicle" in event_type:

                vehicle += count

            elif "Wildlife" in event_type:

                animal += count

            elif "Weapon" in event_type:

                weapon += count

            else:

                other += count

        total = (
            person
            + vehicle
            + animal
            + weapon
            + other
        )

        per_camera = {}

        for camera_id in CAMERA_SOURCES:

            cursor = None

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT camera_id, COUNT(*)
            FROM threats
            GROUP BY camera_id
            """
        )

        camera_rows = cursor.fetchall()

        conn.close()

        for camera_id in CAMERA_SOURCES:

            per_camera[camera_id] = 0

        for camera_id, count in camera_rows:

            if camera_id in per_camera:

                per_camera[
                    camera_id
                ] = count

        return {

            "total": total,

            "person": person,

            "vehicle": vehicle,

            "animal": animal,

            "weapon": weapon,

            "other": other,

            "per_camera": per_camera,

        }

    except Exception as e:

        print(
            f"[STATISTICS] Error: {e}"
        )

        return {
            "total": 0,
            "person": 0,
            "vehicle": 0,
            "animal": 0,
            "weapon": 0,
            "other": 0,
            "per_camera": {
                "CAM_01": 0,
                "CAM_02": 0,
                "CAM_03": 0,
                "CAM_04": 0,
            }
        }


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/api/health")
def health():

    return {
        "status": "healthy",
        "backend": "online",
        "database": os.path.exists(
            DB_FILE
        ),
        "model": MODEL is not None,
        "time": datetime.now().isoformat()
    }


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":

    import uvicorn

    print()
    print(
        "=========================================="
    )
    print(
        " BORDER SENTINEL AI SURVEILLANCE SYSTEM"
    )
    print(
        "=========================================="
    )
    print(
        "Backend: http://127.0.0.1:8001"
    )
    print(
        "API Docs: http://127.0.0.1:8001/docs"
    )
    print(
        "=========================================="
    )
    print()

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8001,
        reload=False
    )