# BSAIS — Team Project Documentation

## AI-Powered Multi-Camera Border & Area Security System

**BSAIS — Border & Area Security AI System** is an AI-based video surveillance platform designed to monitor multiple CCTV camera feeds in real time.

The system uses **YOLOv8 + ByteTrack** to detect and track people, checks whether tracked people enter predefined restricted zones, records security incidents in **SQLite**, and displays everything through a web-based security dashboard.

---

# 1. 🎯 Project Objective

### Problem

Traditional CCTV systems mainly allow security personnel to **watch video manually**.

If an operator is monitoring multiple cameras simultaneously, it becomes difficult to:

* Continuously watch every camera
* Identify people entering restricted areas
* Track the same person across frames
* Detect incidents quickly
* Maintain an incident history
* Review and acknowledge alerts

### Our Solution

BSAIS converts ordinary CCTV feeds into an **AI-assisted surveillance system**.

Instead of requiring an operator to watch every frame:

```text
CCTV Camera
     ↓
Video Stream
     ↓
YOLOv8 Object Detection
     ↓
ByteTrack Object Tracking
     ↓
Restricted-Zone Detection
     ↓
Threat/Intrusion Detected
     ↓
SQLite Database
     ↓
Security Dashboard
     ↓
Operator Acknowledges Alert
```

The operator therefore focuses primarily on **security incidents rather than continuously watching every video feed**.

---

# 2. 🧠 What We Are Building

The first version of BSAIS has four major components:

| Component        | Technology  | Purpose                               |
| ---------------- | ----------- | ------------------------------------- |
| Video Processing | OpenCV      | Read and process CCTV frames          |
| AI Detection     | YOLOv8      | Detect people/objects                 |
| Tracking         | ByteTrack   | Maintain identity of detected targets |
| Backend          | FastAPI     | API + video streaming                 |
| Database         | SQLite      | Store security incidents              |
| Frontend         | HTML/CSS/JS | Security operator dashboard           |
| Streaming        | MJPEG       | Display processed video in browser    |

---

# 3. 🏗️ Overall Architecture

```text
                    CCTV / Video Sources
                    ┌──────┬──────┬──────┐
                    │      │      │      │
                  CAM01  CAM02  CAM03  CAM04
                    │      │      │      │
                    └──────┴──────┴──────┘
                              │
                              ▼
                        OpenCV
                    Frame Extraction
                              │
                              ▼
                     ┌────────────────┐
                     │    YOLOv8      │
                     │ Object Detect  │
                     └───────┬────────┘
                             │
                             ▼
                     ┌────────────────┐
                     │   ByteTrack    │
                     │ Object Tracking│
                     └───────┬────────┘
                             │
                             ▼
                    Person Track IDs
                             │
                             ▼
                  Restricted Zone Check
                             │
                    ┌────────┴────────┐
                    │                 │
                 Outside           Inside
                    │                 │
                    ▼                 ▼
                 Continue       Threat Detected
                                      │
                          ┌───────────┴───────────┐
                          │                       │
                          ▼                       ▼
                    SQLite Database         Dashboard Alert
                                                  │
                                                  ▼
                                           Operator Review
                                                  │
                                                  ▼
                                             Acknowledge
```

---

# 4. 🔑 Core Concept

The most important concept for every team member to understand is:

> **Detection ≠ Tracking ≠ Intrusion Detection**

These are three different operations.

### Detection

YOLO answers:

> "What objects are present in this frame?"

Example:

```text
Person
Person
Car
```

### Tracking

ByteTrack answers:

> "Is this the same person I saw in the previous frame?"

Example:

```text
Frame 1 → Person ID 7
Frame 2 → Person ID 7
Frame 3 → Person ID 7
```

So we don't treat the same person as a completely new person every frame.

### Intrusion Detection

The system then asks:

> "Is tracked person ID 7 inside our restricted polygon?"

Example:

```text
             RESTRICTED AREA
        ┌──────────────────────┐
        │                      │
        │       Person #7      │
        │          ●           │
        │                      │
        └──────────────────────┘
                  ↓
              INTRUSION
```

This distinction is fundamental to the project.

---

# 5. 📁 Project Folder Structure

Our project should follow this structure:

```text
BSAIS/
│
├── backend/
│   └── main.py
│
├── frontend/
│   ├── index.html
│   │
│   ├── css/
│   │   └── style.css
│   │
│   └── js/
│       └── app.js
│
├── scripts/
│   └── calibrate_camera.py
│
├── video/
│   ├── input/
│   │   ├── cam_1.mp4
│   │   ├── cam_2.mp4
│   │   ├── cam_3.mp4
│   │   └── cam_4.mp4
│   │
│   └── output/
│
├── database.db
├── yolov8n.pt
├── requirements.txt
├── .gitignore
└── README.md
```

---

# 6. 👨‍💻 Responsibility of Each File

## `backend/main.py`

This is the **brain of the system**.

It handles:

* FastAPI server
* Loading YOLO
* Reading video
* Object detection
* Object tracking
* Zone detection
* Threat creation
* SQLite operations
* MJPEG streaming
* REST API endpoints

Think of it as:

```text
main.py
   │
   ├── Video Processing
   ├── AI
   ├── Tracking
   ├── Security Logic
   ├── Database
   └── API
```

---

## `frontend/index.html`

Responsible for the dashboard structure.

Example:

```text
┌─────────────────────────────────────┐
│       BSAIS SECURITY CENTER          │
├─────────────────┬───────────────────┤
│     CAM 01      │       CAM 02      │
│                 │                   │
├─────────────────┼───────────────────┤
│     CAM 03      │       CAM 04      │
│                 │                   │
└─────────────────┴───────────────────┘

        SECURITY INCIDENTS

   Camera 2
   Person entered restricted zone

   [ACKNOWLEDGE]
```

---

## `frontend/css/style.css`

Controls:

* Dashboard appearance
* Dark theme
* CCTV cards
* Alert colors
* Buttons
* Responsive layout

---

## `frontend/js/app.js`

Responsible for communication between frontend and backend.

For example:

```text
Frontend
   │
   │ GET /api/alerts
   ▼
FastAPI
   │
   ▼
SQLite
```

It also:

* Polls alerts
* Displays new threats
* Sends acknowledgement requests
* Updates the dashboard

---

# 7. 🤖 AI Pipeline

Our AI pipeline works like this:

```text
Video Frame
     ↓
Resize / Preprocess
     ↓
YOLOv8
     ↓
Bounding Boxes
     ↓
ByteTrack
     ↓
Track IDs
     ↓
Person Foot Point
     ↓
Polygon Test
     ↓
Threat Decision
```

---

# 8. YOLOv8 Detection

YOLOv8 receives a frame:

```text
        CAMERA FRAME
             ↓
       ┌────────────┐
       │   YOLOv8   │
       └─────┬──────┘
             ↓
       Detected Objects
             ↓
       ┌─────────────┐
       │ Person      │
       │ Person      │
       │ Car         │
       └─────────────┘
```

For the current security use case, we primarily care about:

```text
Class 0 = Person
```

---

# 9. 🎯 Why We Use ByteTrack

Without tracking:

```text
Frame 1 → Person
Frame 2 → Person
Frame 3 → Person
Frame 4 → Person
```

The system might treat these as four separate detections.

With ByteTrack:

```text
Frame 1 → Person #12
Frame 2 → Person #12
Frame 3 → Person #12
Frame 4 → Person #12
```

This allows us to maintain a unique `track_id`.

That is important for preventing duplicate alerts.

---

# 10. 🚨 Restricted Zone Detection

Each camera can have its own restricted polygon.

Conceptually:

```python
ZONES = {
    "CAM_01": [...],
    "CAM_02": [...],
    "CAM_03": [...],
    "CAM_04": [...]
}
```

Example:

```text
Camera Frame

┌─────────────────────────────────┐
│                                 │
│             Person              │
│                ●                │
│                                 │
│       ┌──────────────────┐      │
│       │ RESTRICTED ZONE  │      │
│       │                  │      │
│       └──────────────────┘      │
│                                 │
└─────────────────────────────────┘
```

The system checks whether the person's reference point is inside the polygon.

We use:

```python
cv2.pointPolygonTest()
```

---

# 11. 📍 Why Use the Foot/Centroid Point?

A bounding box looks like:

```text
       ┌─────────┐
       │ PERSON  │
       │         │
       │         │
       └────●────┘
            ↑
        reference
          point
```

For ground-based restricted zones, the **bottom-center/foot point** is usually more useful than the box center because it better represents where the person is standing on the ground.

---

# 12. 🚨 Threat Generation

The basic logic is:

```text
Person detected?
       ↓
     YES
       ↓
Track ID assigned?
       ↓
     YES
       ↓
Is person inside restricted zone?
       ↓
     YES
       ↓
Has this track already generated an alert?
       ↓
    NO
       ↓
Create threat
       ↓
Save to SQLite
       ↓
Show on dashboard
```

This prevents the system from generating hundreds of alerts for the same person.

---

# 13. 🗄️ Database

We use SQLite because the prototype does not require a separate database server.

Main table:

```text
threats
```

Expected fields:

| Field         | Purpose                       |
| ------------- | ----------------------------- |
| `id`          | Unique incident ID            |
| `camera_id`   | Camera that detected incident |
| `event_type`  | Type of security event        |
| `track_id`    | AI tracking ID                |
| `description` | Human-readable description    |
| `timestamp`   | Incident time                 |
| `status`      | Review state                  |

Example:

```text
ID:          21
Camera:      CAM_02
Event:       Restricted Zone Intrusion
Track ID:    7
Description: Person entered restricted area
Time:        2026-09-09 09:30:15
Status:      unreviewed
```

---

# 14. 🔄 Alert Lifecycle

An alert has two basic states:

```text
UNREVIEWED
     │
     │ Operator clicks Acknowledge
     ▼
REVIEWED
```

The frontend sends:

```text
PATCH
/api/alerts/{id}/acknowledge
```

The backend updates SQLite.

---

# 15. 📡 API Structure

The backend exposes endpoints similar to:

### Camera Stream

```text
GET /video_feed/CAM_01
GET /video_feed/CAM_02
GET /video_feed/CAM_03
GET /video_feed/CAM_04
```

These provide MJPEG video streams.

---

### Alerts

```text
GET /api/alerts
```

Used by the dashboard to retrieve incidents.

---

### Acknowledge Alert

```text
PATCH /api/alerts/{id}/acknowledge
```

Used when the operator reviews an incident.

---

# 16. 🌐 Frontend ↔ Backend Communication

This is important for frontend team members.

The browser doesn't directly access SQLite.

Instead:

```text
                 FRONTEND
                    │
              JavaScript Fetch
                    │
                    ▼
                 FASTAPI
                    │
             ┌──────┴──────┐
             │             │
             ▼             ▼
          SQLite       Video Engine
```

Example:

```javascript
fetch("http://127.0.0.1:8001/api/alerts")
```

The backend responds with alert information.

---

# 17. 🎥 MJPEG Streaming

Instead of sending a normal video file to the browser, the backend continuously sends JPEG frames.

Conceptually:

```text
Frame 1 → JPEG
Frame 2 → JPEG
Frame 3 → JPEG
Frame 4 → JPEG
       ↓
     Browser
```

The browser displays this as a continuous video stream.

Endpoint:

```text
/video_feed/{camera_id}
```

---

# 18. 🛠️ Camera Calibration

Different cameras have different perspectives.

Therefore, a single polygon cannot necessarily be used for every camera.

The calibration tool allows us to click points on the camera image.

Example:

```text
Click 1 ●────────────● Click 2
       │              │
       │   RESTRICTED │
       │     ZONE     │
       │              │
Click 4 ●────────────● Click 3
```

The tool generates coordinates such as:

```python
np.array([
    [120, 150],
    [600, 140],
    [650, 400],
    [100, 420]
])
```

These coordinates are then placed inside the corresponding camera's `ZONES` configuration.

---

# 19. 🚀 Installation

## Step 1 — Clone

```bash
git clone https://github.com/<your-username>/BSAIS.git
cd BSAIS
```

## Step 2 — Virtual Environment

### Windows

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### macOS/Linux

```bash
python3 -m venv venv
source venv/bin/activate
```

## Step 3 — Install Dependencies

```bash
pip install -r requirements.txt
```

If `requirements.txt` is not yet available:

```bash
pip install fastapi uvicorn opencv-python ultralytics numpy pydantic
```

---

# 20. 🎬 Add Camera Videos

Place videos here:

```text
video/input/
```

Required:

```text
cam_1.mp4
cam_2.mp4
cam_3.mp4
cam_4.mp4
```

---

# 21. ▶️ Start Backend

From the project root:

```powershell
python backend/main.py
```

Backend:

```text
http://127.0.0.1:8001
```

---

# 22. 🌐 Start Frontend

Open the project in VS Code.

Use **Live Server** to open:

```text
frontend/index.html
```

The dashboard will normally be available at:

```text
http://127.0.0.1:5500/frontend/index.html
```

---

# 23. 🧪 Testing Procedure

Every team member should test the system in this order.

### Test 1 — Backend

Check that FastAPI starts successfully.

```text
Backend → Running
```

### Test 2 — Camera

Check:

```text
CAM_01 → Video
CAM_02 → Video
CAM_03 → Video
CAM_04 → Video
```

### Test 3 — AI

Put a person inside a camera video.

Verify:

```text
Person → Detected
```

### Test 4 — Tracking

Verify that the person keeps the same ID:

```text
Person #1
Person #1
Person #1
```

### Test 5 — Zone

Move the person into the restricted polygon.

Expected:

```text
INTRUSION DETECTED
```

### Test 6 — Database

Check that a record appears in:

```text
database.db
```

### Test 7 — Dashboard

Verify the incident appears on the frontend.

### Test 8 — Acknowledgement

Click:

```text
ACKNOWLEDGE
```

Expected:

```text
unreviewed → reviewed
```

---

# 24. 👥 Recommended Team Division

For a **6-member team**, divide development into modules rather than everyone modifying `main.py`.

### Member 1 — AI/CV Engineer

Responsible for:

```text
YOLOv8
ByteTrack
Detection
Tracking
Confidence filtering
```

---

### Member 2 — Security Logic Engineer

Responsible for:

```text
Restricted zones
Polygon detection
Intrusion rules
Duplicate-alert prevention
Threat classification
```

---

### Member 3 — Backend Engineer

Responsible for:

```text
FastAPI
REST APIs
MJPEG streaming
Backend architecture
Error handling
```

---

### Member 4 — Database Engineer

Responsible for:

```text
SQLite
Database schema
Threat storage
Alert status
Database queries
```

---

### Member 5 — Frontend Engineer

Responsible for:

```text
Dashboard
CCTV grid
Alert panel
Acknowledgement UI
Responsive design
```

---

### Member 6 — Integration & Testing Engineer

Responsible for:

```text
Connecting all modules
Testing
Bug tracking
Performance testing
Demo preparation
Documentation
```

This person should **not just wait until the end**. Integration should happen continuously.

---

# 25. 🔀 Git Workflow

Everyone should **not directly push to `main`**.

Recommended:

```text
main
 │
 ├── feature/ai-tracking
 ├── feature/security-zones
 ├── feature/backend-api
 ├── feature/database
 ├── feature/dashboard
 └── feature/testing
```

Workflow:

```text
Create branch
      ↓
Write code
      ↓
Test locally
      ↓
git add .
      ↓
git commit
      ↓
git push
      ↓
Pull Request
      ↓
Team Review
      ↓
Merge into main
```

---

# 26. 📝 Commit Convention

Use meaningful commit messages.

### Good

```text
feat: add ByteTrack person tracking
```

```text
feat: add restricted zone detection
```

```text
fix: prevent duplicate intrusion alerts
```

```text
feat: add alert acknowledgement API
```

```text
ui: improve CCTV dashboard
```

### Avoid

```text
update
```

```text
changes
```

```text
final
```

```text
new code
```

---

# 27. ⚠️ Important Team Rules

### Rule 1

**Never commit `venv/`.**

### Rule 2

**Never commit unnecessary generated files.**

### Rule 3

Don't modify another member's module without informing them.

### Rule 4

Before pushing:

```bash
git pull
```

Resolve conflicts before creating your PR.

### Rule 5

Every feature must be tested before merging.

### Rule 6

Don't hard-code machine-specific paths such as:

```text
C:\Users\Gopi\Desktop\BSAIS\...
```

Use relative paths.

---

# 28. 🔒 `.gitignore`

Use:

```gitignore
venv/
__pycache__/
*.pyc
.vscode/

database.db
yolov8n.pt

video/output/

.env
```

**Important:** if the model weights are required for a fresh installation, document how teammates obtain them rather than silently depending on a local file.

---

# 29. 🧩 Development Roadmap

The project should be developed in stages.

### Phase 1 — Basic Video

```text
Video
 ↓
OpenCV
 ↓
Browser
```

### Phase 2 — AI Detection

```text
Video
 ↓
YOLOv8
 ↓
Person Detection
```

### Phase 3 — Tracking

```text
YOLOv8
 ↓
ByteTrack
 ↓
Track IDs
```

### Phase 4 — Security Zones

```text
Tracking
 ↓
Polygon Detection
 ↓
Intrusion
```

### Phase 5 — Database

```text
Intrusion
 ↓
SQLite
 ↓
Threat Record
```

### Phase 6 — Dashboard

```text
SQLite/API
 ↓
Frontend
 ↓
Operator
```

### Phase 7 — Integration

```text
4 Cameras
+
AI
+
Tracking
+
Zones
+
Database
+
Dashboard
```

### Phase 8 — Advanced Features

After the basic system is stable, we can add:

```text
├── Evidence snapshots
├── Incident video recording
├── Multiple threat types
├── Email/SMS alerts
├── Real CCTV/RTSP cameras
├── User authentication
├── Role-based access
├── Analytics
├── Heatmaps
├── Camera health monitoring
├── GPU acceleration
└── Deployment
```

---

# 30. 🧪 Definition of Done

A feature is considered complete only when:

```text
☐ Code implemented
☐ Runs without errors
☐ Tested locally
☐ Doesn't break existing features
☐ Git commit created
☐ Branch pushed
☐ Team member reviewed
☐ Merged into main
```

---

# 31. 🎤 How to Explain BSAIS in the Hackathon

Every teammate should be able to explain this in simple terms:

> **"BSAIS is an AI-powered security monitoring system that converts existing CCTV feeds into an intelligent surveillance platform. We use YOLOv8 to detect people, ByteTrack to maintain their identities across frames, and polygon-based geofencing to determine whether a person enters a restricted area. When an intrusion occurs, the system creates an incident in SQLite and immediately exposes it through our FastAPI backend to a security dashboard where the operator can review and acknowledge the alert."**

---

# 32. 🧠 One-Line Explanation of Each Technology

Your teammates should remember these:

```text
OpenCV
→ Handles video frames

YOLOv8
→ Detects objects

ByteTrack
→ Tracks objects

Polygon
→ Defines restricted areas

pointPolygonTest
→ Determines whether a target is inside the area

FastAPI
→ Backend/API

MJPEG
→ Sends processed video to browser

SQLite
→ Stores incidents

JavaScript
→ Communicates with backend

HTML/CSS
→ Builds the operator dashboard
```

---

# 33. 🔥 Final System

The final system should look conceptually like:

```text
                   BSAIS
                     │
        ┌────────────┴────────────┐
        │                         │
     CAMERA SYSTEM             OPERATOR
        │                         │
  ┌─────┼─────┐                   │
  │     │     │                   │
CAM01 CAM02 CAM03 CAM04           │
  │     │     │     │             │
  └─────┴─────┴─────┘             │
              │                   │
           OpenCV                 │
              │                   │
           YOLOv8                 │
              │                   │
          ByteTrack               │
              │                   │
       Restricted Zone            │
              │                   │
        ┌─────┴─────┐             │
        │           │             │
      Safe       Intrusion        │
                    │             │
                 SQLite           │
                    │             │
                 FastAPI          │
                    │             │
                    └─────────────┤
                                  ▼
                         SECURITY DASHBOARD
                                  │
                            Review Alert
                                  │
                             Acknowledge
```

## 🚀 Most Important Point for the Team

Don't think of BSAIS as **"one Python file that runs YOLO."**

Think of it as **six connected systems**:

```text
1. VIDEO SYSTEM
        ↓
2. AI DETECTION SYSTEM
        ↓
3. TRACKING SYSTEM
        ↓
4. SECURITY DECISION SYSTEM
        ↓
5. INCIDENT/DATABASE SYSTEM
        ↓
6. OPERATOR DASHBOARD
```

If every teammate understands those six layers, they'll understand the entire project architecture and can work independently without constantly asking *"where does this code go?"*.

This documentation is also a good foundation for your **SIH presentation/demo**, because the same architecture can later be expanded from sample MP4 videos to **real CCTV/RTSP streams, evidence capture, real-time notifications, analytics, and deployment**.
