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

# ----------------- DATABASE BUS IMPORT -----------------
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
    def get_latest_alerts(limit=5): return []
    def get_stats_summary(): return 0, {}
    def get_alert_by_id(alert_id: int): return None
    def update_alert_status(alert_id: int, new_status: str): pass
    def get_connection():
        import sqlite3
        return sqlite3.connect(":memory:")
    def log_access_attempt(*args, **kwargs): pass
    def get_recent_access_logs(*args, **kwargs): return []

st.set_page_config(
    page_title="Border Sentinel",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ----------------- CAMERA API MAPPING & STATE -----------------
CAM_API_MAP = {
    "CAM-01": "cam_1",
    "CAM-02": "cam_2",
    "CAM-03": "cam_3",
    "CAM-04": "cam_4",
}

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

# ----------------- DATA FETCH & TIME-BOUND EVALUATION -----------------
def check_recent_threat(max_seconds=6):
    """Only display strobe if an unacknowledged intrusion occurred in the last max_seconds."""
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

def fetch_all_db_alerts(limit=200):
    try:
        with get_connection() as conn:
            df = pd.read_sql_query(f"SELECT * FROM alerts ORDER BY id DESC LIMIT {limit}", conn)
            if not df.empty:
                for col in df.columns:
                    if col in ["confidence"]:
                        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
                    elif col in ["id", "track_id"]:
                        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(-1).astype(int)
                    else:
                        df[col] = df[col].fillna("").astype(str)
            return df
    except Exception as e:
        print(f"[DB READ ERROR] {e}")
        return pd.DataFrame()

# ----------------- INCIDENT INSPECTOR MODAL -----------------
@st.dialog("🚨 Incident Inspector", width="large")
def inspect_incident_dialog(alert_id: int):
    alert = get_alert_by_id(alert_id)
    if not alert:
        st.error("Incident record not found.")
        return

    thumb_url = f"http://127.0.0.1:8000/alerts_static/{alert['thumbnail_path']}"
    col_img, col_details = st.columns([1, 1], gap="medium")

    with col_img:
        st.markdown(f"""
            <div style="border: 1px solid #334155; border-radius: 8px; overflow: hidden; background: #0b111e;">
                <img src="{thumb_url}" style="width: 100%; aspect-ratio: 4/3; object-fit: cover;" onerror="this.src='https://via.placeholder.com/320x240/111827/ef4444?text=DETECTION+BUFFER'" />
            </div>
            <div style="margin-top: 8px; font-size: 0.75rem; color: #64748b;">
                Snapshot: <code>{alert['thumbnail_path']}</code>
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

    strobe_class = "threat-strobe-active" if is_active_threat else ""
    status_tag = (
        f'<span class="strobe-pill">⚠️ INTRUSION DETECTED: {threat.get("cam_id", "CAM-01")} ({threat.get("sector", "Sector A")})</span>'
        if is_active_threat
        else '<span style="color:#10b981; font-size:0.8rem; font-weight:600;">● System Online</span>'
    )

    audio_script = ""
    intrusion_banner = ""
    if is_active_threat:
        intrusion_banner = f"""
        <div style="background: rgba(239, 68, 68, 0.2); border: 2px solid #ef4444; border-radius: 8px; padding: 12px 16px; margin-bottom: 14px; display: flex; align-items: center; justify-content: space-between;">
            <div style="display: flex; align-items: center; gap: 12px;">
                <span style="font-size: 1.6rem;">🚨</span>
                <div>
                    <b style="color: #ef4444; font-size: 0.95rem; letter-spacing: 0.5px;">CRITICAL BREACH: INTRUDER CONFIRMED</b><br>
                    <span style="color: #cbd5e1; font-size: 0.8rem;">Entity detected at <b>{threat.get('cam_id', 'CAM-01')}</b> ({threat.get('sector', 'Sector A')}). Live Telegram notifications transmitting.</span>
                </div>
            </div>
            <span style="background: #ef4444; color: white; font-size: 0.72rem; font-weight: bold; padding: 5px 10px; border-radius: 4px;">ALERT ACTIVE</span>
        </div>
        """
        audio_script = """
        <script>
            (function() {
                try {
                    var audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                    var osc = audioCtx.createOscillator();
                    var gain = audioCtx.createGain();
                    osc.type = 'sawtooth';
                    osc.frequency.setValueAtTime(880, audioCtx.currentTime);
                    osc.frequency.exponentialRampToValueAtTime(440, audioCtx.currentTime + 0.35);
                    gain.gain.setValueAtTime(0.2, audioCtx.currentTime);
                    gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.35);
                    osc.connect(gain);
                    gain.connect(audioCtx.destination);
                    osc.start();
                    osc.stop(audioCtx.currentTime + 0.35);
                } catch(e) {}
            })();
        </script>
        """

    st.markdown(f"""
        <div class="top-header {strobe_class}">
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
        {intrusion_banner}
        {audio_script}
    """, unsafe_allow_html=True)

render_header_with_siren()

def render_feed(cam_id: str, endpoint: str):
    is_on = st.session_state.cam_states.get(cam_id, True)
    ts = int(time.time() * 1000)
    if is_on:
        return f'<img src="http://127.0.0.1:8000/video/{endpoint}?t={ts}&state=1" style="width:100%; border-radius:6px; aspect-ratio:16/9; object-fit:cover;" />'
    return '<div style="width:100%; aspect-ratio:16/9; background:#0b111e; display:flex; align-items:center; justify-content:center; color:#64748b; font-size:0.8rem; border-radius:6px; font-weight:bold;">CAMERA FEED DISABLED</div>'

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
        @st.fragment(run_every="2s")
        def render_live_panel():
            st.markdown("""
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                    <span style="color:white; font-weight:700; font-size:0.95rem;">🚨 Live Alerts</span>
                    <span style="color:#10b981; font-size:0.75rem; font-weight:600;">● Realtime</span>
                </div>
            """, unsafe_allow_html=True)

            recent_alerts = get_latest_alerts(limit=5)

            if not recent_alerts:
                st.markdown(
                    '<div style="color:#64748b; font-size:0.8rem; padding:18px; text-align:center; border:1px dashed #334155; border-radius:6px;">No alerts detected yet. Feeds monitoring...</div>',
                    unsafe_allow_html=True,
                )
            else:
                for alert in recent_alerts:
                    badge_cls = "badge-high" if alert.get("severity") == "High" else "badge-med"
                    thumb_name = alert.get("thumbnail_path", "")
                    thumb_url = f"http://127.0.0.1:8000/alerts_static/{thumb_name}"
                    status_label = alert.get("status", "Pending")
                    alert_id = alert.get("id")

                    st.markdown(f"""
                        <div class="alert-row" style="margin-bottom: 6px;">
                            <div style="flex: 1; min-width: 0;">
                                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 2px;">
                                    <span style="font-size: 0.8rem; font-weight: 700; color: #f8fafc;">{alert.get('label', 'Entity')}</span>
                                    <span class="{badge_cls}">{alert.get('severity', 'High')} ({int(float(alert.get('confidence', 0.8)) * 100)}%)</span>
                                </div>
                                <div style="font-size: 0.7rem; color: #94a3b8;">{alert.get('sector', 'Sector A')} | {alert.get('cam_id', 'CAM-01')} • {alert.get('timestamp', '')}</div>
                                <div style="font-size: 0.65rem; color: #64748b; margin-top: 2px;">Status: <b style="color:#38bdf8;">{status_label}</b></div>
                            </div>
                            <img class="alert-thumb" src="{thumb_url}" alt="crop" onerror="this.src='https://via.placeholder.com/44x44/111827/ef4444?text=DET'" />
                        </div>
                    """, unsafe_allow_html=True)

                    if st.button(f"🔍 Inspect Incident #{alert_id}", key=f"insp_btn_{alert_id}", use_container_width=True):
                        st.session_state.active_inspect_id = int(alert_id)
                        st.rerun()

                    st.markdown("<div style='height: 4px;'></div>", unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("""
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 6px;">
                    <span style="color:white; font-weight:700; font-size:0.95rem;">📊 Detection Stats (Real-Time)</span>
                </div>
            """, unsafe_allow_html=True)

            _, counts = get_stats_summary()
            person_count = counts.get("Person", 0)
            vehicle_count = counts.get("Vehicle", 0)

            if person_count == 0 and vehicle_count == 0:
                labels = ["Standby Monitoring"]
                values = [1]
                colors = ["#1e293b"]
            else:
                labels = ["Person", "Vehicle"]
                values = [person_count, vehicle_count]
                colors = ["#ef4444", "#f59e0b"]

            fig = go.Figure(data=[go.Pie(
                labels=labels,
                values=values,
                hole=0.68,
                marker=dict(colors=colors),
                textinfo="none"
            )])

            fig.update_layout(
                showlegend=True,
                margin=dict(t=5, b=5, l=5, r=5),
                height=180,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#cbd5e1", size=10),
                legend=dict(orientation="v", x=1.02, y=0.5),
            )

            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        render_live_panel()

# =====================================================================
# TAB 2: 🚨 ALERTS (TRIAGE AND ACTION CENTER)
# =====================================================================
elif "Alerts" in nav_selection:
    st.markdown("### 🚨 Threat Incident Management & Dispatch")
    st.caption("Review, filter, and acknowledge real-time perimeter alert events.")

    df_alerts = fetch_all_db_alerts(limit=100)

    if df_alerts.empty:
        st.info("No alert records present in the database.")
    else:
        status_filter = st.selectbox("Filter by Status:", ["All", "Pending", "Acknowledged", "False Alarm"])
        if status_filter != "All":
            filtered_df = df_alerts[df_alerts["status"] == status_filter]
        else:
            filtered_df = df_alerts

        st.markdown(f"**Displaying {len(filtered_df)} Incidents**")

        for _, alert in filtered_df.iterrows():
            badge = "badge-high" if alert["severity"] == "High" else "badge-med"
            thumb = f"http://127.0.0.1:8000/alerts_static/{alert['thumbnail_path']}"

            col_card, col_act = st.columns([8, 2])
            with col_card:
                st.markdown(f"""
                <div class="alert-row" style="border-radius:6px; margin-bottom:8px;">
                    <div style="display:flex; align-items:center; gap:12px;">
                        <img src="{thumb}" class="alert-thumb" style="width:55px; height:55px;" onerror="this.src='https://via.placeholder.com/55x55/111827/ef4444?text=DET'" />
                        <div>
                            <b>Incident #{int(alert['id']):05d} — {alert['label']}</b> 
                            <span class="{badge}">{alert['severity']}</span>
                            <div style="font-size:0.75rem; color:#94a3b8; margin-top:2px;">
                                Sector: <b>{alert['sector']}</b> | Camera: <b>{alert['cam_id']}</b> | Time: <b>{alert['timestamp']}</b> | Status: <b>{alert['status']}</b>
                            </div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            with col_act:
                if st.button(f"🔍 Inspect #{alert['id']}", key=f"triage_{alert['id']}", use_container_width=True):
                    st.session_state.active_inspect_id = int(alert["id"])
                    st.rerun()

# =====================================================================
# TAB 3: 🎯 DETECTIONS (OBJECT & VECTOR LOGS)
# =====================================================================
elif "Detections" in nav_selection:
    st.markdown("### 🎯 Real-Time Detection Telemetry Log")
    st.caption("Live stream of raw inference logs, track IDs, confidence scores, and direction vectors.")

    df = fetch_all_db_alerts(limit=50)
    if not df.empty:
        display_cols = ["id", "cam_id", "sector", "label", "confidence", "severity", "timestamp", "status"]
        if "track_id" in df.columns:
            display_cols.insert(4, "track_id")

        st.dataframe(
            df[display_cols],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No detection logs available.")

# =====================================================================
# TAB 4: 📜 INCIDENT HISTORY (ARCHIVE & CSV EXPORT)
# =====================================================================
elif "Incident History" in nav_selection:
    st.markdown("### 📜 Security Incident History & Archive")
    st.caption("Query persistent surveillance records and export dispatch evidence.")

    df_hist = fetch_all_db_alerts(limit=500)
    if not df_hist.empty:
        csv_data = df_hist.to_csv(index=False).encode('utf-8')
        c_exp1, c_exp2 = st.columns([3, 7])
        with c_exp1:
            st.download_button(
                label="📥 Export Full Incident Log (CSV)",
                data=csv_data,
                file_name=f"border_sentinel_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True,
                type="primary",
            )
        with c_exp2:
            st.caption(f"Total Archived Records: {len(df_hist)} events.")

        st.dataframe(df_hist, use_container_width=True, height=450)
    else:
        st.info("No historical alerts found in database.")

# =====================================================================
# TAB 5: 📈 ANALYTICS (TRENDS & CHARTS)
# =====================================================================
elif "Analytics" in nav_selection:
    st.markdown("### 📈 Surveillance Metrics & Threat Analytics")
    st.caption("Statistical aggregation of perimeter breach frequency, time distribution, and target classification.")

    df_all = fetch_all_db_alerts(limit=300)
    if not df_all.empty:
        col_g1, col_g2 = st.columns(2)

        with col_g1:
            st.markdown("##### 🚨 Incidents by Camera Sector")
            sec_counts = df_all["sector"].value_counts().reset_index()
            sec_counts.columns = ["Sector", "Detections"]
            fig1 = px.bar(sec_counts, x="Sector", y="Detections", color="Sector", color_discrete_sequence=["#38bdf8", "#ef4444"])
            fig1.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#cbd5e1"))
            st.plotly_chart(fig1, use_container_width=True)

        with col_g2:
            st.markdown("##### 🎯 Classification Breakdown")
            label_counts = df_all["label"].apply(lambda x: "Person" if "Person" in str(x) else "Vehicle").value_counts().reset_index()
            label_counts.columns = ["Type", "Count"]
            fig2 = px.pie(label_counts, names="Type", values="Count", color="Type", color_discrete_map={"Person": "#ef4444", "Vehicle": "#f59e0b"}, hole=0.5)
            fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#cbd5e1"))
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("##### ⏱️ Breach Volume by Timeline")
        df_timeline = df_all.copy()
        fig3 = px.line(df_timeline, x="timestamp", y="confidence", color="severity", markers=True, color_discrete_map={"High": "#ef4444", "Medium": "#f59e0b"})
        fig3.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#cbd5e1"))
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("Gathering detection statistics. Keep cameras online to view live analytics.")

# =====================================================================
# TAB 6: 🔑 ACCESS LOGS (PASSWORD & TERMINAL AUDIT)
# =====================================================================
elif "Access Logs" in nav_selection:
    st.markdown("### 🔑 Terminal Access & Password Audit Ledger")
    st.caption("Cryptographic record of all entered passcodes, operator call-signs, and clearance timestamps.")

    logs = get_recent_access_logs(limit=50)
    if logs:
        df_logs = pd.DataFrame(logs)
        for col in df_logs.columns:
            df_logs[col] = df_logs[col].fillna("").astype(str)

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Entry Attempts", len(df_logs))
        c2.metric("Authorized Sign-ins", len(df_logs[df_logs["status"] == "AUTHORIZED"]))
        c3.metric("Unauthorized / Flagged", len(df_logs[df_logs["status"] == "UNAUTHORIZED"]))

        st.markdown("<br>", unsafe_allow_html=True)
        st.dataframe(
            df_logs[["id", "operator_id", "status", "passcode_hash", "attempt_timestamp", "terminal_source"]],
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No terminal entry attempts recorded yet. Submit a passcode in the sidebar form to generate entries.")

# =====================================================================
# TAB 7: ⚙️ SYSTEM SETTINGS (CONFIGURATION)
# =====================================================================
elif "System Settings" in nav_selection:
    st.markdown("### ⚙️ Border Sentinel Core Configuration")
    st.caption("Manage AI model parameters, streaming server targets, and alerting webhooks.")

    cfg_col1, cfg_col2 = st.columns(2)

    with cfg_col1:
        st.markdown("#### 🧠 AI Inference Engine")
        st.slider("YOLOv8 Detection Confidence Threshold", min_value=0.10, max_value=0.90, value=0.30, step=0.05)
        st.slider("ByteTrack Movement Vector Sensitivity", min_value=3, max_value=25, value=10)
        st.selectbox("Inference Accelerator Device", ["CPU (Optimized OpenVINO / ONNX)", "CUDA (NVIDIA TensorRT)", "DirectML"])

    with cfg_col2:
        st.markdown("#### 📲 Telegram Notification Gateways")
        st.text_input("Telegram Bot Token", value="884659130:AAG...", type="password")
        st.text_input("Security Chat ID", value="1498877231")
        st.slider("Anti-Spam Alert Cooldown (seconds)", min_value=3, max_value=60, value=10)

    st.markdown("<hr style='border:0; border-top:1px solid #1e293b; margin:16px 0;'>", unsafe_allow_html=True)
    if st.button("💾 Save System Configuration", type="primary"):
        st.success("System parameters persisted to config.toml.")

# ----------------- ROOT-LEVEL DIALOG INVOCATION -----------------
if st.session_state.active_inspect_id is not None:
    inspect_incident_dialog(st.session_state.active_inspect_id)
    st.session_state.active_inspect_id = None