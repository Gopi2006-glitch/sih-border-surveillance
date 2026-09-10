import sqlite3
import os
import hashlib
from datetime import datetime

# Guarantee absolute path to BSAIS/backend/database/alerts.db
MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.abspath(os.path.join(MODULE_DIR, "alerts.db"))
ALERTS_DIR = os.path.abspath(os.path.join(MODULE_DIR, "..", "..", "data", "alerts"))
os.makedirs(ALERTS_DIR, exist_ok=True)

def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=20.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")  # Enable concurrent read/write between streamer and app
    return conn

def init_db():
    """Ensure tables exist."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cam_id TEXT NOT NULL,
                sector TEXT NOT NULL,
                label TEXT NOT NULL,
                confidence REAL NOT NULL,
                severity TEXT NOT NULL,
                thumbnail_path TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                status TEXT DEFAULT 'Pending',
                track_id INTEGER DEFAULT -1,
                created_at TEXT
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS access_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operator_id TEXT NOT NULL,
                passcode_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                attempt_timestamp TEXT NOT NULL,
                terminal_source TEXT NOT NULL
            );
        """)
        conn.commit()

init_db()

# ----------------- ALERT WRITERS & READERS -----------------
def insert_alert(cam_id: str, sector: str, label: str, confidence: float, severity: str, thumbnail_path: str, track_id: int = -1):
    now = datetime.now()
    ts_display = now.strftime("%H:%M:%S")
    iso_str = now.isoformat()
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO alerts (cam_id, sector, label, confidence, severity, thumbnail_path, timestamp, status, track_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'Pending', ?, ?)
            """, (cam_id, sector, label, float(confidence), severity, thumbnail_path, ts_display, int(track_id), iso_str))
            conn.commit()
            return cursor.lastrowid
    except Exception as e:
        print(f"[DB INSERT ERROR] {e}")
        return None

def get_latest_alerts(limit: int = 5):
    try:
        with get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        print(f"[DB GET ERROR] {e}")
        return []

def get_alert_by_id(alert_id: int):
    try:
        with get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception:
        return None

def update_alert_status(alert_id: int, new_status: str):
    try:
        with get_connection() as conn:
            conn.execute("UPDATE alerts SET status = ? WHERE id = ?", (new_status, alert_id))
            conn.commit()
    except Exception as e:
        print(f"[DB UPDATE ERROR] {e}")

def get_stats_summary():
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM alerts")
            total = cursor.fetchone()[0] or 0

            cursor.execute("SELECT label, COUNT(*) FROM alerts GROUP BY label")
            rows = cursor.fetchall()
            counts = {}
            for l, c in rows:
                clean = "Person" if "Person" in str(l) else ("Vehicle" if "Vehicle" in str(l) else str(l))
                counts[clean] = counts.get(clean, 0) + c
            return total, counts
    except Exception:
        return 0, {}

# ----------------- ACCESS LOGS -----------------
def log_access_attempt(operator_id: str, passcode: str, status: str, terminal_source: str = "MAIN_COMMAND_CONSOLE"):
    pass_hash = hashlib.sha256(passcode.encode()).hexdigest()[:16]
    now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with get_connection() as conn:
            conn.execute("""
                INSERT INTO access_logs (operator_id, passcode_hash, status, attempt_timestamp, terminal_source)
                VALUES (?, ?, ?, ?, ?)
            """, (operator_id.strip(), pass_hash, status, now_ts, terminal_source))
            conn.commit()
    except Exception as e:
        print(f"[ACCESS LOG ERROR] {e}")

def get_recent_access_logs(limit: int = 50):
    try:
        with get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM access_logs ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(r) for r in cursor.fetchall()]
    except Exception:
        return []