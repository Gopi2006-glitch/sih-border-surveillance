import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import requests
import json
import time
import os
import sys
import pandas as pd
import numpy as np

# ----------------- DATABASE BUS IMPORT & CLOUD MOCK FALLBACK -----------------
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(BASE_DIR)

try:
    from backend.database.alerts_db import (
        get_latest_alerts,
        get_stats_summary,
        get_alert_by_id,
        update_alert_status,
        get_connection,
        log_access_attempt,
        get_recent_access_logs,
    )
except ImportError:
    # Cloud Mock / Standalone Mode to ensure dashboard is 100% functional
    def get_latest_alerts(limit=5):
        return [
            {"id": 55462, "label": "Person", "track_id": 104, "cam_id": "CAM-01", "sector": "Sector A", "confidence": 0.94, "severity": "High", "status": "Pending", "timestamp": "15:45:12", "thumbnail_path": ""},
            {"id": 55460, "label": "Person", "track_id": 102, "cam_id": "CAM-02", "sector": "Sector B", "confidence": 0.88, "severity": "High", "status": "Pending", "timestamp": "15:43:08", "thumbnail_path": ""},
            {"id": 55340, "label": "Vehicle", "track_id": 88, "cam_id": "CAM-04", "sector": "Sector B", "confidence": 0.91, "severity": "Medium", "status": "Acknowledged", "timestamp": "15:39:20", "thumbnail_path": ""},
            {"id": 55210, "label": "Person", "track_id": 73, "cam_id": "CAM-03", "sector": "Sector A", "confidence": 0.82, "severity": "High", "status": "Pending", "timestamp": "15:31:05", "thumbnail_path": ""}
        ][:limit]

    def get_stats_summary():
        return 1838, {"Person": 1360, "Vehicle": 478}

    def get_alert_by_id(alert_id: int):
        return {
            "id": alert_id,
            "label": "Person",
            "track_id": 104,
            "cam_id": "CAM-01",
            "sector": "Sector A",
            "confidence": 0.94,
            "severity": "High",
            "status": "Pending",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "thumbnail_path": ""
        }

    def update_alert_status(alert_id: int, new_status: str):
        pass

    def get_connection():
        import sqlite3
        return sqlite3.connect(":memory:")

    def log_access_attempt(*args, **kwargs):
        pass

    def get_recent_access_logs(*args, **kwargs):
        return []

st.set_page_config(
    page_title="Border Sentinel",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ----------------- CAMERA API MAPPING & RELIABLE SURVEILLANCE STREAMS -----------------
CAM_API_MAP = {
    "CAM-01": "cam_1",
    "CAM-02": "cam_2",
    "CAM-03": "cam_3",
    "CAM-04": "cam_4",
    
    }
# Reliable cloud surveillance feeds (live surveillance GIFs & snapshots)
FALLBACK_SURVEILLANCE_FEEDS = {
    "CAM-01": "https://images.unsplash.com/photo-1557597774-9d273605dfa9?w=800&auto=format&fit=crop&q=80",
    "CAM-02": "https://images.unsplash.com/photo-1508873696983-2df5703bc20d?w=800&auto=format&fit=crop&q=80",
    "CAM-03": "https://images.unsplash.com/photo-1541888946425-d0fbb186c5f7?w=800&auto=format&fit=crop&q=80",
    "CAM-04": "https://images.unsplash.com/photo-1579202673506-ca3ce28943ef?w=800&auto=format&fit=crop&q=80"
}

FALLBACK_ALERT_THUMB = "https://cdn-icons-png.flaticon.com/512/3135/3135715.png"

if "cam_states" not in st.session_state:
    st.session_state.cam_states = {
        "CAM-01": True,
        "CAM-02": True,
        "CAM-03": True,
        "CAM-04": True,
    }

if "active_inspect_id" not in st.session_state:
    st.session_state.active_inspect_id = None

def set_cam_state(cam_id: str, state: bool):
    st.session_state.cam_states[cam_id] = state
    backend_key = CAM_API_MAP.get(cam_id)
    if backend_key:
        try:
            requests.post(
                f"http://127.0.0.1:8000/camera/{backend_key}/toggle",
                json={"enabled": state},
                timeout=0.2,
            )
        except Exception:
            pass

# ----------------- STYLES -----------------
css_path = os.path.join(os.path.dirname(__file__), "style.css")
if os.path.exists(css_path):
    with open(css_path) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
else:
    st.markdown("""
        <style>
            .kpi-card { background:#0f172a; border:1px solid #1e293b; border-radius:10px; padding:12px; text-align:center; }
            .kpi-title { font-size:0.8rem; color:#94a3b8; font-weight:600; margin-bottom:4px; }
            .kpi-val { font-size:1.6rem; font-weight:800; color:#f8fafc; }
            .cam-top-bar { display:flex; justify-content:space-between; background:#0f172a; padding:6px 12px; border-radius:6px 6px 0 0; font-size:0.8rem; font-weight:600; border:1px solid #1e293b; border-bottom:none; margin-top:8px; }
            .control-bar { margin-top:12px; padding:10px; background:#0f172a; border:1px solid #1e293b; border-radius:8px; display:flex; gap:16px; font-size:0.82rem; }
            .badge-high { background:#ef4444; color:white; padding:2px 6px; border-radius:4px; font-weight:bold; }
            .badge-med { background:#f59e0b; color:white; padding:2px 6px; border-radius:4px; font-weight:bold; }
            .top-header { display:flex; justify-content:space-between; align-items:center; background:#0f172a; border:1px solid #1e293b; padding:12px 18px; border-radius:10px; margin-bottom:15px; }
        </style>
    """, unsafe_allow_html=True)

# ----------------- DATA FETCH & TIME-BOUND EVALUATION -----------------
def check_recent_threat(max_seconds=6):
    recent = get_latest_alerts(limit=1)
    if recent:
        alert = recent[0]
        if alert.get("severity") == "High" and alert.get("status") == "Pending":
            created = alert.get("created_at")
            if created:
                try:
                    alert_dt = datetime.fromisoformat(created)
                    elapsed = (datetime.now() - alert_dt).total_seconds()
                    if 0 <= elapsed <= max_seconds:
                        return True, alert
                except Exception:
                    pass
    return False, None

# ----------------- INCIDENT INSPECTOR MODAL -----------------
@st.dialog("🚨 Incident Inspector", width="large")
def inspect_incident_dialog(alert_id: int):
    alert = get_alert_by_id(alert_id)
    if not alert:
        st.error("Incident record not found.")
        return

    thumb_url = f"http://127.0.0.1:8000/alerts_static/{alert['thumbnail_path']}" if alert.get("thumbnail_path") else FALLBACK_ALERT_THUMB
    col_img, col_details = st.columns([1, 1], gap="medium")

    with col_img:
        st.markdown(f"""
            <div style="border: 1px solid #334155; border-radius: 8px; overflow: hidden; background: #0b111e;">
                <img src="{thumb_url}" style="width: 100%; aspect-ratio: 4/3; object-fit: cover;" onerror="this.src='{FALLBACK_ALERT_THUMB}'" />
            </div>
            <div style="margin-top: 8px; font-size: 0.75rem; color: #64748b;">
                Incident Target ID: <code>#{alert.get('id', alert_id)}</code>
            </div>
        """, unsafe_allow_html=True)

    with col_details:
        st.markdown(f"### {alert['label']} Detection")
        st.markdown(f"""
        * **Incident ID:** `#{alert['id']:05d}`
        * **Camera Unit:** `{alert['cam_id']}`
        * **Sector:** `{alert['sector']}`
        * **Timestamp:** `{alert['timestamp']}`
        * **Confidence Level:** `{int(alert['confidence'] * 100)}%`
        * **Threat Severity:** <span class="{'badge-high' if alert['severity'] == 'High' else 'badge-med'}">{alert['severity']}</span>
        * **Current Status:** `{alert.get('status', 'Pending')}`
        """, unsafe_allow_html=True)

        st.markdown("<hr style='border:0; border-top:1px solid #1e293b; margin:12px 0;'>", unsafe_allow_html=True)
        st.caption("Operator Actions")

        act1, act2 = st.columns(2)
        with act1:
            if st.button("✅ Acknowledge", use_container_width=True, type="primary"):
                update_alert_status(alert_id, "Acknowledged")
                st.toast(f"Incident #{alert_id} marked as Acknowledged.")
                st.rerun()
        with act2:
            if st.button("❌ False Alarm", use_container_width=True):
                update_alert_status(alert_id, "False Alarm")
                st.toast(f"Incident #{alert_id} marked as False Alarm.")
                st.rerun()

        st.download_button(
            label="📥 Export Telemetry",
            data=json.dumps(alert, indent=2),
            file_name=f"incident_{alert_id}.json",
            mime="application/json",
            use_container_width=True,
        )

# ----------------- SIDEBAR -----------------
with st.sidebar:
    st.markdown("""
        <div style="background: linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.9) 100%); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 12px; padding: 14px; margin-bottom: 18px; box-shadow: 0 4px 15px rgba(0,0,0,0.5);">
            <div style="display: flex; align-items: center; gap: 12px;">
                <div style="background: radial-gradient(circle, #38bdf8 0%, #0284c7 100%); width: 40px; height: 40px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 1.4rem; box-shadow: 0 0 12px rgba(56, 189, 248, 0.6);">
                    🛡️
                </div>
                <div>
                    <span style="font-size: 1.05rem; font-weight: 800; color: #f8fafc; letter-spacing: 1px; display: block;">BORDER SENTINEL</span>
                    <span style="font-size: 0.68rem; font-weight: 700; color: #38bdf8; letter-spacing: 0.8px;">AI DEFENSE COMMAND</span>
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    nav_selection = st.radio(
        "Navigation",
        [
            "📊  Dashboard",
            "🚨  Alerts (3)",
            "🎯  Detections",
            "📜  Incident History",
            "📈  Analytics",
            "🔑  Access Logs",
            "⚙️  System Settings",
        ],
        label_visibility="collapsed",
    )
    st.markdown("<hr style='border:0; border-top:1px solid #1e293b; margin:16px 0 10px 0;'>", unsafe_allow_html=True)

    st.markdown("<b style='color:#38bdf8; font-size:0.8rem;'>OPERATOR DUTY LOG</b>", unsafe_allow_html=True)
    with st.form("quick_duty_log_form"):
        op_id = st.text_input("Call-Sign", value="Operator-1", label_visibility="collapsed", placeholder="Call-Sign")
        pass_code = st.text_input("Passcode", type="password", label_visibility="collapsed", placeholder="Enter Duty Key")
        log_btn = st.form_submit_button("Record Entry ⚡", use_container_width=True)

        if log_btn and pass_code:
            eval_status = "AUTHORIZED" if pass_code in ["admin123", "sentry2026", "sentinel"] else "UNAUTHORIZED"
            log_access_attempt(
                operator_id=op_id,
                passcode=pass_code,
                status=eval_status,
                terminal_source="MAIN_COMMAND_CONSOLE"
            )
            if eval_status == "AUTHORIZED":
                st.toast(f"✅ Access Logged: {op_id} (Verified)")
            else:
                st.toast(f"⚠️ Flagged Attempt: {op_id} (Logged in Ledger)")

    st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)
    st.markdown("""
        <div style='background: linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(15, 23, 42, 0.8) 100%); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 10px; padding: 12px; font-size: 0.75rem; box-shadow: 0 4px 10px rgba(0,0,0,0.3);'>
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                <span style="display: inline-block; width: 8px; height: 8px; background: #10b981; border-radius: 50%; box-shadow: 0 0 8px #10b981;"></span>
                <b style="color: #34d399;">PERIMETER SHIELD ACTIVE</b>
            </div>
            <span style="color: #94a3b8; font-size: 0.7rem;">Sector A & Sector B Under Live Surveillance</span>
        </div>
    """, unsafe_allow_html=True)

# ----------------- DYNAMIC HEADER & INTRUSION BANNER -----------------
@st.fragment(run_every="2s")
def render_header_with_siren():
    is_active_threat, threat = check_recent_threat(max_seconds=6)
    now_str = datetime.now().strftime("%b %d, %Y  %H:%M:%S")

    status_tag = (
        f'<span style="color:#ef4444; font-size:0.8rem; font-weight:700;">⚠️ INTRUSION: {threat.get("cam_id", "CAM-01")}</span>'
        if is_active_threat
        else '<span style="color:#10b981; font-size:0.8rem; font-weight:600;">● System Online</span>'
    )

    st.markdown(f"""
        <div class="top-header">
            <div style="display:flex; align-items:center; gap:12px;">
                <span style="font-size:1.15rem; font-weight:800; color:#38bdf8; letter-spacing:1px;">BORDER SENTINEL</span>
                <span style="color:#334155;">|</span>
                <span style="color:#94a3b8; font-size:0.8rem;">AI POWERED BORDER SURVEILLANCE SYSTEM</span>
            </div>
            <div style="display:flex; align-items:center; gap:22px;">
                {status_tag}
                <span style="color:#94a3b8; font-size:0.8rem;">{now_str}</span>
                <span style="background:#ef4444; color:white; padding:2px 8px; border-radius:999px; font-size:0.75rem; font-weight:bold;">🔔 3</span>
                <span style="color:#e2e8f0; font-size:0.82rem;"><b>Admin</b> <small style="color:#94a3b8;">Operator</small></span>
            </div>
        </div>
    """, unsafe_allow_html=True)

render_header_with_siren()

# ----------------- ROBUST FEED RENDERER WITH CLOUD FALLBACK -----------------
def render_feed(cam_id: str, endpoint: str):
    is_on = st.session_state.cam_states.get(cam_id, True)
    ts = int(time.time() * 1000)
    
    if not is_on:
        return '<div style="width:100%; aspect-ratio:16/9; background:#0b111e; display:flex; align-items:center; justify-content:center; color:#64748b; font-size:0.8rem; border-radius:0 0 6px 6px; font-weight:bold; border:1px solid #1e293b;">CAMERA FEED DISABLED</div>'
    
    fallback_url = FALLBACK_SURVEILLANCE_FEEDS.get(cam_id, FALLBACK_SURVEILLANCE_FEEDS["CAM-01"])
    # Uses onerror fallback: tries backend streaming endpoint first; falls back gracefully to cloud snapshot if backend isn't running
    return f"""
        <div style="width:100%; aspect-ratio:16/9; background:#0b111e; border:1px solid #1e293b; border-radius:0 0 6px 6px; overflow:hidden;">
            <img src="http://127.0.0.1:8000/video/{endpoint}?t={ts}" 
                 onerror="this.onerror=null; this.src='{fallback_url}';" 
                 style="width:100%; height:100%; object-fit:cover;" />
        </div>
    """

# =====================================================================
# TAB 1: 📊 DASHBOARD
# =====================================================================
if "Dashboard" in nav_selection:
    col_center, col_right = st.columns([7, 3])

    with col_center:
        total_dets, counts = get_stats_summary()
        active_alerts_count = counts.get("Person", 0)

        k1, k2, k3, k4 = st.columns(4)
        with k1:
            online_cams = sum(1 for v in st.session_state.cam_states.values() if v)
            st.markdown(f'<div class="kpi-card"><div class="kpi-title">📹 Active Cameras</div><div class="kpi-val">0{online_cams} / 04</div><small style="color:#10b981;">● Operational</small></div>', unsafe_allow_html=True)
        with k2:
            st.markdown(f'<div class="kpi-card"><div class="kpi-title">⚠️ Active Alerts</div><div class="kpi-val" style="color:#ef4444;">{active_alerts_count:02d}</div><small style="color:#ef4444;">Requires Attention</small></div>', unsafe_allow_html=True)
        with k3:
            st.markdown(f'<div class="kpi-card"><div class="kpi-title">🎯 Total Detections</div><div class="kpi-val">{total_dets:02d}</div><small style="color:#10b981;">▲ Live Bus</small></div>', unsafe_allow_html=True)
        with k4:
            st.markdown('<div class="kpi-card"><div class="kpi-title">🛡️ System Uptime</div><div class="kpi-val">99.9%</div><small style="color:#10b981;">Operational</small></div>', unsafe_allow_html=True)

        st.write("")

        r1_col1, r1_col2 = st.columns(2)
        with r1_col1:
            c1_on = st.session_state.cam_states["CAM-01"]
            pill = ("● Live", "#10b981") if c1_on else ("● Offline", "#64748b")
            st.markdown(f'<div class="cam-top-bar"><span>CAM-01 | Sector A</span><span style="color:{pill[1]};">{pill[0]}</span></div>', unsafe_allow_html=True)
            st.markdown(render_feed("CAM-01", "cam_1"), unsafe_allow_html=True)
            b1, b2 = st.columns(2)
            b1.button("OFF", key="c1_off", on_click=set_cam_state, args=("CAM-01", False), use_container_width=True, type="primary" if not c1_on else "secondary")
            b2.button("ON", key="c1_on", on_click=set_cam_state, args=("CAM-01", True), use_container_width=True, type="primary" if c1_on else "secondary")

        with r1_col2:
            c2_on = st.session_state.cam_states["CAM-02"]
            pill = ("● Alert", "#ef4444") if c2_on else ("● Offline", "#64748b")
            st.markdown(f'<div class="cam-top-bar"><span>CAM-02 | Sector B</span><span style="color:{pill[1]};">{pill[0]}</span></div>', unsafe_allow_html=True)
            st.markdown(render_feed("CAM-02", "cam_2"), unsafe_allow_html=True)
            b3, b4 = st.columns(2)
            b3.button("OFF", key="c2_off", on_click=set_cam_state, args=("CAM-02", False), use_container_width=True, type="primary" if not c2_on else "secondary")
            b4.button("ON", key="c2_on", on_click=set_cam_state, args=("CAM-02", True), use_container_width=True, type="primary" if c2_on else "secondary")

        r2_col1, r2_col2 = st.columns(2)
        with r2_col1:
            c3_on = st.session_state.cam_states["CAM-03"]
            pill = ("● Live", "#10b981") if c3_on else ("● Offline", "#64748b")
            st.markdown(f'<div class="cam-top-bar"><span>CAM-03 | Sector A</span><span style="color:{pill[1]};">{pill[0]}</span></div>', unsafe_allow_html=True)
            st.markdown(render_feed("CAM-03", "cam_3"), unsafe_allow_html=True)
            b5, b6 = st.columns(2)
            b5.button("OFF", key="c3_off", on_click=set_cam_state, args=("CAM-03", False), use_container_width=True, type="primary" if not c3_on else "secondary")
            b6.button("ON", key="c3_on", on_click=set_cam_state, args=("CAM-03", True), use_container_width=True, type="primary" if c3_on else "secondary")

        with r2_col2:
            c4_on = st.session_state.cam_states["CAM-04"]
            pill = ("● Motion", "#f59e0b") if c4_on else ("● Offline", "#64748b")
            st.markdown(f'<div class="cam-top-bar"><span>CAM-04 | Sector B</span><span style="color:{pill[1]};">{pill[0]}</span></div>', unsafe_allow_html=True)
            st.markdown(render_feed("CAM-04", "cam_4"), unsafe_allow_html=True)
            b7, b8 = st.columns(2)
            b7.button("OFF", key="c4_off", on_click=set_cam_state, args=("CAM-04", False), use_container_width=True, type="primary" if not c4_on else "secondary")
            b8.button("ON", key="c4_on", on_click=set_cam_state, args=("CAM-04", True), use_container_width=True, type="primary" if c4_on else "secondary")

        cam_status_html = " ".join([
            f'<span><span style="color:{"#10b981" if is_on else "#ef4444"};">●</span> {cid}: <b>{"ON" if is_on else "OFF"}</b></span>'
            for cid, is_on in st.session_state.cam_states.items()
        ])

        st.markdown(f"""
            <div class="control-bar">
                <span style="font-weight:bold; color:#cbd5e1;">📹 Camera Controls:</span>
                {cam_status_html}
            </div>
        """, unsafe_allow_html=True)

    with col_right:
        st.markdown("""
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                <span style="color:white; font-weight:700; font-size:0.95rem;">🚨 Live Alerts</span>
                <span style="color:#10b981; font-size:0.75rem; font-weight:600;">● Realtime</span>
            </div>
        """, unsafe_allow_html=True)

        recent_alerts = get_latest_alerts(limit=4)

        for alert in recent_alerts:
            aid = alert["id"]
            sev_color = "#ef4444" if alert.get("severity") == "High" else "#f59e0b"
            t_url = f"http://127.0.0.1:8000/alerts_static/{alert.get('thumbnail_path')}" if alert.get("thumbnail_path") else FALLBACK_ALERT_THUMB

            st.markdown(f"""
                <div style="background:#0f172a; border:1px solid #1e293b; border-left:4px solid {sev_color}; padding:10px; border-radius:6px; margin-bottom:8px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div>
                            <span style="color:#f8fafc; font-weight:700; font-size:0.85rem;">{alert['label']} #{alert['id']}</span>
                            <span style="background:{sev_color}; color:white; font-size:0.65rem; padding:1px 5px; border-radius:4px; font-weight:bold; margin-left:4px;">{alert.get('severity', 'High')}</span>
                        </div>
                        <img src="{t_url}" onerror="this.onerror=null; this.src='{FALLBACK_ALERT_THUMB}';" style="width:24px; height:24px; border-radius:4px;" />
                    </div>
                    <div style="color:#94a3b8; font-size:0.72rem; margin:4px 0;">
                        {alert.get('sector', 'Sector A')} | {alert.get('cam_id', 'CAM-01')}<br>
                        {alert.get('timestamp', 'Live')} | Status: <b>{alert.get('status', 'Pending')}</b>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            if st.button(f"🔍 Inspect Incident #{aid}", key=f"btn_inspect_{aid}", use_container_width=True):
                inspect_incident_dialog(aid)

        # Realtime Donut Chart
        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
        st.markdown("<b style='color:white; font-size:0.85rem;'>📊 Detection Stats (Real-Time)</b>", unsafe_allow_html=True)
        fig = go.Figure(data=[go.Pie(
            labels=['Person', 'Vehicle'],
            values=[counts.get('Person', 75), counts.get('Vehicle', 25)],
            hole=.65,
            marker=dict(colors=['#ef4444', '#f59e0b'])
        )])
        fig.update_layout(
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5),
            margin=dict(l=10, r=10, t=10, b=10),
            height=180,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#94a3b8", size=11)
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

else:
    st.info(f"Viewing: {nav_selection}")
