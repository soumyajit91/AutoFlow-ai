"""
app.py
======
Premium Streamlit UI for AutoFlow AI — supports two workflows:
  1. Meeting to Action  (existing)
  2. Employee Onboarding  (new)

With Supabase Authentication (email + password login/signup).

Run with:  streamlit run app.py
"""

import json
import os
import sys
import time

from dotenv import load_dotenv
load_dotenv()

import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))
from main import run_workflow, run_onboarding_workflow
from tools import LOGS_FILE
from db import get_supabase_client, sign_in, sign_up, sign_out


# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Autonomous Workflow AI",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] { font-family:'Inter',sans-serif; background:#0a0d1a; color:#e2e8f0; }
.stApp { background:linear-gradient(135deg,#0a0d1a 0%,#0f172a 50%,#0a0d1a 100%); }
#MainMenu,footer,header { visibility:hidden; }

.hero {
    background:linear-gradient(135deg,#1e3a5f 0%,#0f172a 50%,#1a1040 100%);
    border:1px solid rgba(99,179,237,.15); border-radius:16px;
    padding:2rem 2.5rem; margin-bottom:1.5rem; position:relative; overflow:hidden;
}
.hero::before {
    content:''; position:absolute; top:-60px; right:-60px;
    width:200px; height:200px;
    background:radial-gradient(circle,rgba(99,179,237,.12) 0%,transparent 70%); border-radius:50%;
}
.hero h1 {
    font-size:2.2rem; font-weight:700;
    background:linear-gradient(90deg,#63b3ed,#a78bfa,#f472b6);
    -webkit-background-clip:text; -webkit-text-fill-color:transparent; margin:0 0 .4rem;
}
.hero p { color:#94a3b8; font-size:1rem; margin:0; }

.glass-card {
    background:rgba(255,255,255,.04); backdrop-filter:blur(12px);
    border:1px solid rgba(255,255,255,.08); border-radius:12px;
    padding:1.4rem 1.6rem; margin-bottom:1rem; transition:border-color .25s;
}
.glass-card:hover { border-color:rgba(99,179,237,.3); }

.badge { display:inline-block; padding:.22rem .75rem; border-radius:999px;
         font-size:.75rem; font-weight:600; letter-spacing:.04em; text-transform:uppercase; }
.badge-success  { background:#064e3b; color:#34d399; border:1px solid #065f46; }
.badge-warning  { background:#451a03; color:#fb923c; border:1px solid #7c2d12; }
.badge-error    { background:#450a0a; color:#f87171; border:1px solid #7f1d1d; }
.badge-info     { background:#0c1a4a; color:#60a5fa; border:1px solid #1e3a8a; }
.badge-escalate { background:#2d1754; color:#c084fc; border:1px solid #581c87; }

.agent-step {
    border-left:3px solid #3b82f6; padding:.9rem 1.2rem; margin:.6rem 0;
    background:rgba(59,130,246,.06); border-radius:0 10px 10px 0;
}
.agent-name { font-weight:600; font-size:.88rem; color:#93c5fd; }
.agent-role { font-size:.78rem; color:#64748b; margin-bottom:.4rem; }
.agent-reasoning { font-size:.83rem; color:#cbd5e1; line-height:1.55; white-space:pre-wrap; }

.task-row {
    display:grid; grid-template-columns:2fr 1fr 90px 1fr 170px;
    gap:.8rem; align-items:center; padding:.75rem 1rem;
    border-bottom:1px solid rgba(255,255,255,.05); font-size:.85rem;
}
.task-row.header {
    font-weight:600; font-size:.78rem; text-transform:uppercase;
    letter-spacing:.06em; color:#64748b;
    background:rgba(255,255,255,.03); border-radius:8px 8px 0 0;
}
.task-desc  { color:#e2e8f0; font-weight:500; }
.task-owner { color:#93c5fd; }
.task-source{ color:#94a3b8; font-size:.75rem; }

.conf-bar-wrap { background:rgba(255,255,255,.07); border-radius:99px; height:6px; width:100%; }
.conf-bar { height:6px; border-radius:99px; }

.section-title {
    font-size:.78rem; font-weight:700; text-transform:uppercase;
    letter-spacing:.12em; color:#475569; margin:1.5rem 0 .7rem;
    padding-bottom:.4rem; border-bottom:1px solid rgba(255,255,255,.05);
}

.db-status-ok  { background:#064e3b; color:#34d399; border:1px solid #065f46;
                  padding:.25rem .8rem; border-radius:8px; font-size:.75rem; font-weight:600; }
.db-status-off { background:#1e1e1e; color:#64748b; border:1px solid #334155;
                  padding:.25rem .8rem; border-radius:8px; font-size:.75rem; font-weight:600; }

[data-testid="stSidebar"] { background:#0d1627 !important; border-right:1px solid rgba(255,255,255,.06) !important; }
[data-testid="stSidebar"] p, [data-testid="stSidebar"] label { color:#94a3b8 !important; }

.stTextArea textarea, .stTextInput input {
    background:rgba(255,255,255,.04) !important; border:1px solid rgba(255,255,255,.10) !important;
    border-radius:8px !important; color:#e2e8f0 !important;
}
.stTextArea textarea:focus, .stTextInput input:focus {
    border-color:#3b82f6 !important; box-shadow:0 0 0 2px rgba(59,130,246,.25) !important;
}
.stButton > button[kind="primary"] {
    background:linear-gradient(135deg,#1d4ed8,#7c3aed) !important;
    border:none !important; font-weight:600 !important; font-size:.95rem !important;
    padding:.65rem 2rem !important; border-radius:8px !important; color:white !important;
    transition:all .2s !important; box-shadow:0 4px 20px rgba(99,102,241,.3) !important;
}
.stButton > button[kind="primary"]:hover {
    transform:translateY(-1px) !important; box-shadow:0 6px 24px rgba(99,102,241,.5) !important;
}
.prog-step { display:flex; align-items:center; gap:.75rem; padding:.5rem 0; font-size:.85rem; color:#94a3b8; }
.prog-dot  { width:10px; height:10px; border-radius:50%; background:#1e40af; flex-shrink:0; box-shadow:0 0 8px #3b82f6; }
.prog-dot.done   { background:#059669; box-shadow:0 0 8px #10b981; }
.prog-dot.active { background:#d97706; box-shadow:0 0 12px #f59e0b; animation:pulse 1s infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }

.login-card {
    max-width:420px; margin:4rem auto;
    background:rgba(255,255,255,.04); backdrop-filter:blur(16px);
    border:1px solid rgba(255,255,255,.08); border-radius:16px; padding:2.5rem;
}
.login-card h2 { font-size:1.5rem; font-weight:700; color:#e2e8f0; text-align:center; margin:0 0 .3rem; }
.login-card .subtitle { text-align:center; color:#64748b; font-size:.85rem; margin-bottom:1.5rem; }
.login-logo { text-align:center; font-size:3rem; margin-bottom:.8rem; }

.user-badge {
    background:rgba(99,179,237,.08); border:1px solid rgba(99,179,237,.2);
    border-radius:10px; padding:.6rem .9rem; margin:.5rem 0;
}
.user-badge .email { color:#93c5fd; font-size:.82rem; font-weight:600; }
.user-badge .label { color:#475569; font-size:.7rem; }

/* Onboarding info card */
.ob-info {
    display:grid; grid-template-columns:repeat(auto-fill, minmax(200px,1fr));
    gap:1rem; margin:1rem 0;
}
.ob-info-item {
    background:rgba(255,255,255,.04); border:1px solid rgba(255,255,255,.08);
    border-radius:10px; padding:1rem; text-align:center;
}
.ob-info-item .label { font-size:.7rem; color:#64748b; text-transform:uppercase; letter-spacing:.08em; }
.ob-info-item .value { font-size:1.1rem; font-weight:600; color:#e2e8f0; margin-top:.3rem; }
.ob-info-item .value.accent { color:#63b3ed; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def status_badge(status):
    badges = {
        "success":            '<span class="badge badge-success">✓ Success</span>',
        "recovered":          '<span class="badge badge-success">♻ Recovered</span>',
        "completed":          '<span class="badge badge-success">✓ Completed</span>',
        "partial_failure":    '<span class="badge badge-warning">⚠ Partial</span>',
        "partial_escalation": '<span class="badge badge-warning">⚠ Partial</span>',
        "warning":            '<span class="badge badge-warning">⚠ Warning</span>',
        "failed":             '<span class="badge badge-error">✗ Failed</span>',
        "escalated":          '<span class="badge badge-escalate">↑ Escalated</span>',
        "retrying":           '<span class="badge badge-warning">↻ Retrying</span>',
        "escalating":         '<span class="badge badge-escalate">↑ Escalating</span>',
    }
    return badges.get(status, f'<span class="badge badge-info">{status}</span>')

def confidence_bar(conf):
    pct = int(conf * 100)
    color = "#34d399" if pct >= 75 else ("#fb923c" if pct >= 45 else "#f87171")
    return (f'<div class="conf-bar-wrap"><div class="conf-bar" style="width:{pct}%;background:linear-gradient(90deg,{color},{color}aa);"></div></div>'
            f'<small style="color:{color};font-size:.72rem;">{pct}%</small>')

def agent_icon(name):
    return {"PlannerAgent":"🗺","UnderstandingAgent":"🧠","AssignmentAgent":"🎯",
            "ValidatorAgent":"✅","ExecutorAgent":"⚙️","RecoveryAgent":"🔄",
            "LoggerAgent":"📋"}.get(name, "🤖")

def _db_status_badge():
    client = get_supabase_client()
    if client:
        return '<span class="db-status-ok">🟢 Supabase Connected</span>'
    return '<span class="db-status-off">🔴 Supabase Offline</span>'

def _get_current_user_id():
    user = st.session_state.get("user")
    if user and isinstance(user, dict):
        return user.get("user_id")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# SESSION DEFAULTS
# ─────────────────────────────────────────────────────────────────────────────
for key, default in [
    ("authenticated", False), ("user", None), ("auth_mode", "login"),
    ("workflow_type", "Meeting to Action"), ("last_ctx", None), ("last_ob_ctx", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ═══════════════════════════════════════════════════════════════════════════════
# LOGIN PAGE
# ═══════════════════════════════════════════════════════════════════════════════

def login_page():
    st.markdown("""
    <div class="hero" style="text-align:center; max-width:600px; margin:2rem auto 1.5rem;">
        <h1>🤖 Autonomous Workflow AI</h1>
        <p>Agentic AI for Enterprise Workflows · 7 Agents · Full Audit Trail</p>
    </div>
    """, unsafe_allow_html=True)

    mode = st.session_state["auth_mode"]
    is_login = (mode == "login")

    col_l, col_c, col_r = st.columns([1, 2, 1])
    with col_c:
        st.markdown(f"""
        <div class="login-card">
            <div class="login-logo">{"🔐" if is_login else "✨"}</div>
            <h2>{"Welcome Back" if is_login else "Create Account"}</h2>
            <div class="subtitle">{"Sign in to access your workflows" if is_login else "Sign up with your email"}</div>
        </div>
        """, unsafe_allow_html=True)

        with st.form("auth_form", clear_on_submit=False):
            email = st.text_input("Email", placeholder="you@example.com")
            password = st.text_input("Password", type="password", placeholder="Your password" if is_login else "Min 6 characters")
            submit_label = "Sign In" if is_login else "Create Account"
            submitted = st.form_submit_button(submit_label, type="primary", use_container_width=True)

        if submitted:
            if not email or not password:
                st.error("Please enter both email and password.")
            elif is_login:
                with st.spinner("Signing in..."):
                    ok, data = sign_in(email, password)
                if ok:
                    st.session_state["authenticated"] = True
                    st.session_state["user"] = data
                    st.rerun()
                else:
                    st.error(data.get("error", "Login failed."))
            else:
                if len(password) < 6:
                    st.error("Password must be at least 6 characters.")
                else:
                    with st.spinner("Creating account..."):
                        ok, data = sign_up(email, password)
                    if ok:
                        st.success(data.get("message", "Account created! Please log in."))
                        st.session_state["auth_mode"] = "login"
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(data.get("error", "Sign-up failed."))

        st.markdown("<br>", unsafe_allow_html=True)
        tc1, tc2 = st.columns(2)
        with tc1:
            if is_login and st.button("Don't have an account? Sign Up", use_container_width=True):
                st.session_state["auth_mode"] = "signup"
                st.rerun()
        with tc2:
            if not is_login and st.button("Already have an account? Sign In", use_container_width=True):
                st.session_state["auth_mode"] = "login"
                st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# SHARED TABS: Agent Reasoning + Execution Status + Local Audit + DB Logs
# ═══════════════════════════════════════════════════════════════════════════════

def render_agent_reasoning_tab(reasoning_list):
    st.markdown('<div class="section-title">Agent-by-Agent Reasoning Trail</div>', unsafe_allow_html=True)
    for step in reasoning_list:
        st.markdown(f"""<div class="agent-step">
            <div class="agent-name">{agent_icon(step['agent'])} {step['agent']}</div>
            <div class="agent-role">{step.get('role','')} · {step.get('step','')} · {step.get('timestamp','')}</div>
            <div class="agent-reasoning">{step.get('reasoning','')}</div>
            <div style="margin-top:.4rem;">{status_badge(step.get('status',''))}</div>
        </div>""", unsafe_allow_html=True)


def render_execution_status_tab(audit_log):
    st.markdown('<div class="section-title">Per-Step Execution Status</div>', unsafe_allow_html=True)
    step_map = {}
    for entry in audit_log:
        step_map[entry.get("step", "unknown")] = entry
    for step_key, entry in step_map.items():
        status = entry.get("status", "unknown")
        err_html = f'<div style="color:#f87171;font-size:.78rem;margin-top:.3rem;">⚠ {entry["error"]}</div>' if entry.get("error") else ""
        rec_html = f'<div style="color:#a78bfa;font-size:.78rem;">↻ {entry["recovery_action"]}</div>' if entry.get("recovery_action") else ""
        res_html = f'<div style="color:#94a3b8;font-size:.78rem;margin-top:.25rem;">→ {str(entry["final_result"])[:180]}</div>' if entry.get("final_result") else ""
        retry_html = f'<span style="color:#64748b;font-size:.72rem;">retries: {entry.get("retry_count",0)}</span>' if entry.get("retry_count", 0) > 0 else ""
        st.markdown(f"""<div class="glass-card">
            <div style="display:flex;align-items:center;gap:1rem;flex-wrap:wrap;">
                <span class="agent-name">{agent_icon(entry.get('agent',''))} {entry.get('agent','—')}</span>
                <span style="color:#475569;font-size:.78rem;">{step_key}</span>
                {status_badge(status)} {retry_html}
                <span style="color:#475569;font-size:.72rem;margin-left:auto;">{entry.get('timestamp','')}</span>
            </div>
            <div style="color:#cbd5e1;font-size:.82rem;margin-top:.5rem;">{entry.get('action','')}</div>
            {err_html}{rec_html}{res_html}
        </div>""", unsafe_allow_html=True)


def render_local_logs_tab():
    st.markdown('<div class="section-title">Local JSON Audit Trail (logs.json)</div>', unsafe_allow_html=True)
    if os.path.exists(LOGS_FILE):
        with open(LOGS_FILE, "r", encoding="utf-8") as f:
            logs_data = json.load(f)
        st.caption(f"{len(logs_data)} entries")
        c1, c2 = st.columns(2)
        with c1:
            st.json(logs_data)
        with c2:
            st.download_button("⬇ Download logs.json", data=json.dumps(logs_data, indent=2),
                               file_name="autoflow_audit_logs.json", mime="application/json",
                               use_container_width=True)
    else:
        st.info("logs.json not found. Run the workflow first.")


def render_db_logs_tab(user_id, user_email):
    st.markdown('<div class="section-title">🗄 Your Audit Logs — Supabase PostgreSQL</div>', unsafe_allow_html=True)
    client = get_supabase_client()
    if not client:
        st.warning("Supabase is not configured or unreachable.")
        return

    cL, cR = st.columns([3, 1])
    with cR:
        limit = st.number_input("Rows", min_value=10, max_value=500, value=50, step=10)
        st.button("🔄 Refresh", use_container_width=True)
    with cL:
        st.markdown(_db_status_badge(), unsafe_allow_html=True)
        if user_id:
            st.caption(f"Filtering logs for user: {user_email}")

    try:
        query = client.table("logs").select("*").order("created_at", desc=True).limit(limit)
        if user_id:
            query = query.eq("user_id", user_id)
        resp = query.execute()
        rows = resp.data or []
        if not rows:
            st.info("No logs found. Run the workflow to populate them.")
        else:
            st.caption(f"Showing {len(rows)} row(s)")
            import pandas as pd
            df = pd.DataFrame(rows)
            preferred = ["created_at","agent","step","status","retry_count",
                         "action","input","error","recovery_action","final_result","user_id","id"]
            cols_present = [c for c in preferred if c in df.columns]
            extra = [c for c in df.columns if c not in cols_present]
            df = df[cols_present + extra]

            def _cs(val):
                return {"success":"background-color:#064e3b;color:#34d399",
                        "completed":"background-color:#064e3b;color:#34d399",
                        "failed":"background-color:#450a0a;color:#f87171",
                        "escalated":"background-color:#2d1754;color:#c084fc",
                        "retrying":"background-color:#451a03;color:#fb923c"}.get(str(val).lower(),"")

            styled = df.style.map(_cs, subset=["status"]).set_properties(**{
                "background-color":"#0d1627","color":"#e2e8f0","font-size":"12px"})
            st.dataframe(styled, use_container_width=True, height=450)
            st.download_button("⬇ Download CSV", data=df.to_csv(index=False),
                               file_name="supabase_audit_logs.csv", mime="text/csv",
                               use_container_width=True)
    except Exception as exc:
        st.error(f"Failed to fetch from Supabase: {exc}")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN APP
# ═══════════════════════════════════════════════════════════════════════════════

def main_app():
    user = st.session_state.get("user", {}) or {}
    user_email = user.get("email", "user")
    user_id = user.get("user_id")

    # ── SIDEBAR ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("""
        <div style="text-align:center;padding:1.2rem 0 .5rem;">
            <div style="font-size:2.5rem;">🤖</div>
            <h2 style="font-size:1.1rem;font-weight:700;color:#e2e8f0;margin:.3rem 0 .1rem;">Autonomous Workflow AI</h2>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"""
        <div class="user-badge">
            <div class="label">Signed in as</div>
            <div class="email">📧 {user_email}</div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("🚪 Logout", use_container_width=True):
            sign_out()
            for k in ["authenticated","user","last_ctx","last_ob_ctx"]:
                st.session_state[k] = None
            st.session_state["authenticated"] = False
            st.rerun()

        st.markdown(_db_status_badge(), unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        # Workflow type selector
        st.markdown('<div class="section-title">🔀 Workflow Type</div>', unsafe_allow_html=True)
        workflow_type = st.selectbox(
            "Choose Workflow",
            ["Meeting to Action", "Employee Onboarding", "SLA Monitoring Dashboard"],
            label_visibility="collapsed",
        )
        st.session_state["workflow_type"] = workflow_type

        if workflow_type == "Meeting to Action":
            st.markdown('<div class="section-title">🧠 LLM Provider</div>', unsafe_allow_html=True)
            provider_label = st.selectbox(
                "Provider",
                ["Pure Rule-Based (No API)", "Groq (Free Cloud API)", "Ollama (Local)"],
                label_visibility="collapsed",
            )
            provider_map = {"Pure Rule-Based (No API)":"rule_based","Groq (Free Cloud API)":"groq","Ollama (Local)":"ollama"}
            provider = provider_map[provider_label]

            api_key = ""
            if provider == "groq":
                api_key = st.text_input("Groq API Key", type="password", placeholder="gsk_...")
            elif provider == "ollama":
                st.info("Ensure `ollama run llama3` is running.")
        else:
            provider = "rule_based"
            api_key = ""

        # Email config — shared across both workflows
        st.markdown('<div class="section-title">📧 Email Backend</div>', unsafe_allow_html=True)
        email_provider = st.selectbox("Provider", ["Gmail SMTP", "Resend API"], label_visibility="collapsed")
        
        real_email = st.checkbox("Enable Real Emails", value=False)
        sender_email = email_password = resend_key = ""
        
        if real_email:
            if email_provider == "Gmail SMTP":
                sender_email = st.text_input("Gmail Address")
                email_password = st.text_input("App Password", type="password")
            else:
                resend_key = st.text_input("Resend API Key", type="password", placeholder="re_...")

        # Set env vars so tools.py send_email / send_welcome_email can pick them up
        if real_email and email_provider == "Gmail SMTP" and sender_email and email_password:
            os.environ["SENDER_EMAIL"] = sender_email
            os.environ["EMAIL_PASSWORD"] = email_password
            os.environ.pop("RESEND_API_KEY", None)
        elif real_email and email_provider == "Resend API" and resend_key:
            os.environ["RESEND_API_KEY"] = resend_key
            os.environ.pop("SENDER_EMAIL", None)
            os.environ.pop("EMAIL_PASSWORD", None)
        else:
            os.environ.pop("SENDER_EMAIL", None)
            os.environ.pop("EMAIL_PASSWORD", None)
            os.environ.pop("RESEND_API_KEY", None)

        st.markdown('<div class="section-title">⚙️ System</div>', unsafe_allow_html=True)
        st.markdown(f"""
        <div style="font-size:.78rem;color:#475569;line-height:1.8;">
            <b style="color:#64748b;">Mode:</b> {workflow_type}<br>
            <b style="color:#64748b;">Agents:</b> 5-7 autonomous<br>
            <b style="color:#64748b;">Retry:</b> Up to 2x per failure<br>
            <b style="color:#64748b;">DB:</b> Supabase PostgreSQL
        </div>
        """, unsafe_allow_html=True)

    # ── HERO ─────────────────────────────────────────────────────────────────
    if workflow_type == "Meeting to Action":
        wf_label = "Meeting → Action"
    elif workflow_type == "Employee Onboarding":
        wf_label = "Employee Onboarding"
    else:
        wf_label = "SLA Monitoring"

    st.markdown(f"""
    <div class="hero">
        <h1>🤖 Autonomous Workflow AI</h1>
        <p>Welcome, <b style="color:#63b3ed;">{user_email}</b> &nbsp;·&nbsp;
           <b style="color:#a78bfa;">{wf_label}</b> &nbsp;·&nbsp;
           Supabase Audit Trail</p>
    </div>
    """, unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # WORKFLOW: Meeting to Action
    # ══════════════════════════════════════════════════════════════════════════
    if workflow_type == "Meeting to Action":
        _render_meeting_workflow(user_id, user_email, provider, api_key, sender_email, email_password)

    # ══════════════════════════════════════════════════════════════════════════
    # WORKFLOW: Employee Onboarding
    # ══════════════════════════════════════════════════════════════════════════
    elif workflow_type == "Employee Onboarding":
        _render_onboarding_workflow(user_id, user_email)

    # ══════════════════════════════════════════════════════════════════════════
    # DASHBOARD: SLA Monitoring
    # ══════════════════════════════════════════════════════════════════════════
    else:
        _render_sla_dashboard(user_id, user_email)

    # ── FOOTER ───────────────────────────────────────────────────────────────
    st.markdown("""
    <div style="text-align:center;padding:2rem 0 1rem;color:#1e293b;font-size:.75rem;">
        Autonomous Workflow AI · Multi-Agent Pipeline · Supabase Auth + Audit
    </div>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# MEETING TO ACTION UI
# ═══════════════════════════════════════════════════════════════════════════════

def _render_meeting_workflow(user_id, user_email, provider, api_key, sender_email, email_password):
    # Agent pipeline overview
    st.markdown('<div class="section-title">Agent Pipeline</div>', unsafe_allow_html=True)
    agents_overview = [
        ("PlannerAgent","Builds plan"),("UnderstandingAgent","Extracts items"),
        ("AssignmentAgent","Assigns owners"),("ValidatorAgent","Validates"),
        ("ExecutorAgent","Executes"),("RecoveryAgent","Recovers"),("LoggerAgent","Writes audit"),
    ]
    cols = st.columns(7)
    for col, (name, desc) in zip(cols, agents_overview):
        with col:
            st.markdown(f"""<div class="glass-card" style="text-align:center;padding:.9rem .5rem;min-height:100px;">
                <div style="font-size:1.3rem;">{agent_icon(name)}</div>
                <div style="font-size:.68rem;font-weight:600;color:#93c5fd;margin:.2rem 0;">{name.replace('Agent','')}</div>
                <div style="font-size:.62rem;color:#64748b;">{desc}</div>
            </div>""", unsafe_allow_html=True)

    DEFAULT_TRANSCRIPT = """Alice: Good morning everyone. Let's get started with the sprint planning.

Bob: I will take care of the database schema migration by end of week.

Alice: Great. We also need someone to write unit tests for the new login module.
Charlie: I'm still wrapping up my current task, maybe someone else can handle it?
Alice: Let's leave the unit tests unassigned for now.

Bob: Should we also update the deployment pipeline? I think the CI config needs fixing.
DevOps Lead: I'll look into the CI/CD infrastructure improvements.

Alice: Can someone send a summary of this meeting to the stakeholders?
Charlie: I can do the stakeholder email summary.

Alice: Let's also schedule a follow-up demo with the client next Thursday.
"""
    st.markdown('<div class="section-title">📝 Meeting Transcript Input</div>', unsafe_allow_html=True)
    col_in, col_run = st.columns([4, 1])
    with col_in:
        transcript = st.text_area("Transcript", value=DEFAULT_TRANSCRIPT, height=200, label_visibility="collapsed")
    with col_run:
        st.markdown("<br>", unsafe_allow_html=True)
        run_btn = st.button("▶ Run Workflow", type="primary", use_container_width=True, key="run_meeting")

    if run_btn and transcript.strip():
        try:
            with st.spinner(""):
                ctx = run_workflow(transcript=transcript, provider=provider, api_key=api_key,
                                   sender_email=sender_email, email_password=email_password,
                                   user_id=user_id)
            st.success("✅ Workflow completed!")
        except Exception as exc:
            st.error(f"Workflow error: {exc}")
            st.stop()
        st.session_state["last_ctx"] = ctx

    ctx = st.session_state.get("last_ctx")
    if ctx is not None:
        st.markdown("---")
        t1, t2, t3, t4, t5 = st.tabs(["📋 Extracted Tasks","🤖 Agent Reasoning",
                                        "📊 Execution Status","🗂 Local Audit","🗄 Live DB Logs"])
        with t1:
            st.markdown('<div class="section-title">Action Items</div>', unsafe_allow_html=True)
            if ctx.action_items:
                st.markdown("""<div class="task-row header"><div>Action Item</div><div>Owner</div>
                    <div>Confidence</div><div>Source</div><div>Status</div></div>""", unsafe_allow_html=True)
                for item in ctx.action_items:
                    src = {"llm":"🧠 LLM","rule_based":"📐 Rules","human_clarification":"👤 Human"}.get(item.owner_source, item.owner_source)
                    st.markdown(f"""<div class="task-row">
                        <div class="task-desc">{item.description[:80]}</div>
                        <div class="task-owner">👤 {item.owner}</div>
                        <div>{confidence_bar(item.confidence)}</div>
                        <div class="task-source">{src}</div>
                        <div>{status_badge(item.exec_status)}</div>
                    </div>""", unsafe_allow_html=True)
                m1,m2,m3,m4 = st.columns(4)
                m1.metric("Total",len(ctx.action_items))
                m2.metric("✅ OK",sum(1 for a in ctx.action_items if a.exec_status=="success"))
                m3.metric("↑ Esc",sum(1 for a in ctx.action_items if a.exec_status=="escalated"))
                m4.metric("📧",ctx.email_status)
        with t2:
            render_agent_reasoning_tab(ctx.agent_reasoning)
        with t3:
            render_execution_status_tab(ctx.audit_log)
        with t4:
            render_local_logs_tab()
        with t5:
            render_db_logs_tab(user_id, user_email)


# ═══════════════════════════════════════════════════════════════════════════════
# EMPLOYEE ONBOARDING UI
# ═══════════════════════════════════════════════════════════════════════════════

def _render_onboarding_workflow(user_id, user_email):
    # Agent pipeline overview (5 agents for onboarding)
    st.markdown('<div class="section-title">Onboarding Agent Pipeline</div>', unsafe_allow_html=True)
    ob_agents = [
        ("PlannerAgent","Creates plan"),("ExecutorAgent","Runs 5 steps"),
        ("ValidatorAgent","Checks data"),("RecoveryAgent","Retries failures"),("LoggerAgent","Writes audit"),
    ]
    cols = st.columns(5)
    for col, (name, desc) in zip(cols, ob_agents):
        with col:
            st.markdown(f"""<div class="glass-card" style="text-align:center;padding:.9rem .5rem;min-height:100px;">
                <div style="font-size:1.3rem;">{agent_icon(name)}</div>
                <div style="font-size:.68rem;font-weight:600;color:#93c5fd;margin:.2rem 0;">{name.replace('Agent','')}</div>
                <div style="font-size:.62rem;color:#64748b;">{desc}</div>
            </div>""", unsafe_allow_html=True)

    DEPARTMENTS = {
        "Engineering": ["Software Engineer", "Backend Developer", "Frontend Developer", "DevOps Engineer"],
        "Marketing": ["Content Strategist", "SEO Specialist", "Social Media Manager", "Brand Manager"],
        "Sales": ["Sales Executive", "Account Manager", "Business Development Associate", "Sales Analyst"],
        "HR": ["HR Executive", "Talent Acquisition Specialist", "HR Operations", "Training Coordinator"],
        "Finance": ["Accountant", "Financial Analyst", "Auditor", "Payroll Specialist"]
    }

    st.markdown('<div class="section-title">👤 New Employee Details</div>', unsafe_allow_html=True)
    col_name, col_email = st.columns(2)
    with col_name:
        emp_name = st.text_input("Employee Name", placeholder="e.g. John Doe", key="ob_name")
    with col_email:
        emp_email = st.text_input("Contact Email (Welcome sent here)", placeholder="e.g. john@gmail.com", key="ob_email")

    col_dept, col_role, col_run = st.columns([2, 2, 1])
    with col_dept:
        dept = st.selectbox("Department", list(DEPARTMENTS.keys()), key="ob_dept")
    with col_role:
        role = st.selectbox("Role", DEPARTMENTS[dept], key="ob_role")
    with col_run:
        st.markdown("<br>", unsafe_allow_html=True)
        run_btn = st.button("▶ Start Onboarding", type="primary", use_container_width=True, key="run_onboard")

    if run_btn:
        if not emp_name or not emp_name.strip():
            st.error("Please enter the employee name.")
        elif not emp_email or not emp_email.strip():
            st.error("Please enter the employee email (where the welcome mail will be sent).")
        else:
            ob_agents_steps = ["PlannerAgent","ExecutorAgent","ValidatorAgent","RecoveryAgent","LoggerAgent"]
            ob_labels = ["Building Plan","Executing Steps","Validating Data","Recovering","Writing Audit"]
            progress_bar = st.progress(0)
            status_ph = st.empty()

            def update_ob_progress(step_num, total, label):
                progress_bar.progress(step_num / total)
                status_ph.markdown(
                    f'<div style="font-size:.85rem;color:#60a5fa;">{agent_icon(ob_agents_steps[step_num-1])} {label}</div>',
                    unsafe_allow_html=True)

            try:
                with st.spinner(""):
                    ob_ctx = run_onboarding_workflow(
                        employee_name=emp_name.strip(),
                        employee_email=emp_email.strip(),
                        department=dept,
                        role=role,
                        user_id=user_id,
                        progress_callback=update_ob_progress,
                    )
                progress_bar.progress(1.0)
                status_ph.empty()
                st.success("✅ Onboarding workflow completed!")
            except Exception as exc:
                st.error(f"Onboarding error: {exc}")
                st.stop()
            st.session_state["last_ob_ctx"] = ob_ctx

    ob_ctx = st.session_state.get("last_ob_ctx")
    if ob_ctx is not None:
        st.markdown("---")

        # ── Employee Info Card ───────────────────────────────────────────────
        st.markdown('<div class="section-title">📇 Employee Profile</div>', unsafe_allow_html=True)
        st.markdown(f"""
        <div class="ob-info">
            <div class="ob-info-item"><div class="label">Employee ID</div><div class="value accent">{ob_ctx.employee_id}</div></div>
            <div class="ob-info-item"><div class="label">Name</div><div class="value">{ob_ctx.employee_name}</div></div>
            <div class="ob-info-item"><div class="label">Department</div><div class="value">{ob_ctx.department}</div></div>
            <div class="ob-info-item"><div class="label">Role</div><div class="value accent">{ob_ctx.role}</div></div>
            <div class="ob-info-item"><div class="label">Corporate Email</div><div class="value">{ob_ctx.corporate_email}</div></div>
            <div class="ob-info-item"><div class="label">Contact Email</div><div class="value">{ob_ctx.employee_email}</div></div>
            <div class="ob-info-item"><div class="label">Buddy ID</div><div class="value accent">{ob_ctx.buddy_id or 'N/A'}</div></div>
            <div class="ob-info-item"><div class="label">Buddy</div><div class="value">{ob_ctx.buddy_name or 'N/A'} &nbsp;<span style="font-size:.75rem;color:#64748b;">{ob_ctx.buddy_email}</span></div></div>
            <div class="ob-info-item"><div class="label">Orientation</div><div class="value">{ob_ctx.meeting_time or 'N/A'} <span style="font-size:.7rem;color:#64748b;">({ob_ctx.meeting_day})</span></div></div>
        </div>
        """, unsafe_allow_html=True)

        if hasattr(ob_ctx, 'tasks') and ob_ctx.tasks:
            st.markdown('<div class="section-title">📝 Role-Based Onboarding Tasks</div>', unsafe_allow_html=True)
            tasks_html = "<ul style='color:#cbd5e1; font-size: 0.95rem; background-color: #0f172a; padding: 1rem 1rem 1rem 2.5rem; border-radius: 8px; border: 1px solid #1e293b; margin-bottom: 2rem;'>"
            for task in ob_ctx.tasks:
                tasks_html += f"<li style='margin-bottom: 0.4rem;'>{task}</li>"
            tasks_html += "</ul>"
            st.markdown(tasks_html, unsafe_allow_html=True)

        # ── Tabs ─────────────────────────────────────────────────────────────
        t1, t2, t3, t4, t5 = st.tabs(["📋 Onboarding Steps","🤖 Agent Reasoning",
                                        "📊 Execution Status","🗂 Local Audit","🗄 Live DB Logs"])

        with t1:
            st.markdown('<div class="section-title">Onboarding Execution Steps</div>', unsafe_allow_html=True)
            for step in ob_ctx.steps:
                icon = "✅" if step.status == "success" else ("⚠️" if step.status == "escalated" else "❌")
                st.markdown(f"""<div class="glass-card">
                    <div style="display:flex;align-items:center;gap:.8rem;">
                        <span style="font-size:1.2rem;">{icon}</span>
                        <span style="font-weight:600;color:#e2e8f0;">{step.name}</span>
                        {status_badge(step.status)}
                    </div>
                    <div style="color:#94a3b8;font-size:.82rem;margin-top:.4rem;">{step.message}</div>
                </div>""", unsafe_allow_html=True)

            ok = sum(1 for s in ob_ctx.steps if s.status == "success")
            esc = sum(1 for s in ob_ctx.steps if s.status == "escalated")
            failed = sum(1 for s in ob_ctx.steps if s.status == "failed")
            m1,m2,m3,m4 = st.columns(4)
            m1.metric("Total Steps", len(ob_ctx.steps))
            m2.metric("✅ Succeeded", ok)
            m3.metric("↑ Escalated", esc)
            m4.metric("❌ Failed", failed)

        with t2:
            render_agent_reasoning_tab(ob_ctx.agent_reasoning)
        with t3:
            render_execution_status_tab(ob_ctx.audit_log)
        with t4:
            render_local_logs_tab()
        with t5:
            render_db_logs_tab(user_id, user_email)


# ═══════════════════════════════════════════════════════════════════════════════
# SLA MONITORING DASHBOARD UI
# ═══════════════════════════════════════════════════════════════════════════════

def _render_sla_dashboard(user_id, user_email):
    st.markdown('<div class="section-title">🚨 SLA Monitoring Dashboard</div>', unsafe_allow_html=True)
    st.write("Monitor pending Action Items, detect SLA breaches, and trigger autonomous escalations.")

    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"""<div class="glass-card" style="padding: 1rem;">
            <div style="font-size: 0.9rem; color: #cbd5e1; line-height: 1.5;">The <b>MonitoringAgent</b> will scan the Supabase <code>tasks</code> table for tasks that are currently <b>pending</b> or <b>blocked</b>.<br><br>
            <b>SLA Tiers (* 1 minute = simulated hours):</b><br>
            🟢 <b>Normal:</b> &lt; 2 minutes<br>
            🟡 <b>Warning:</b> &gt; 2 minutes<br>
            🔴 <b>Breach:</b> &gt; 5 minutes (Escalates intelligently to Senior Manager or IT Support)</div>
        </div>""", unsafe_allow_html=True)
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("▶ Check SLA Breaches", type="primary", use_container_width=True):
            with st.spinner("MonitoringAgent is analyzing pending tasks..."):
                try:
                    from main import run_sla_monitoring
                    ctx = run_sla_monitoring(user_id)
                    st.session_state["last_sla_ctx"] = ctx
                    st.success("SLA Check Complete!")
                except Exception as exc:
                    st.error(f"SLA Check Failed: {exc}")

    if st.session_state.get("last_sla_ctx"):
        ctx = st.session_state["last_sla_ctx"]
        st.markdown("---")
        t1, t2 = st.tabs(["📊 Audit Trail", "🗄 DB Logs Workflow"])
        with t1:
            render_execution_status_tab(ctx.audit_log)
        with t2:
            render_db_logs_tab(user_id, user_email)
        st.markdown("---")

    client = get_supabase_client()
    if not client:
        st.warning("Supabase client offline. Cannot fetch SLA dashboard metrics.")
        return

    c_left, c_right = st.columns(2)
    
    with c_left:
        st.markdown('<div class="section-title" style="margin-top: 0;">⏳ Active Tasks (Pending / Blocked)</div>', unsafe_allow_html=True)
        try:
            # Fetch all then filter in python to bypass Supabase exact syntax limitations
            resp = client.table("tasks").select("*").execute()
            all_tasks = resp.data or []
            tasks = [t for t in all_tasks if t.get("status") in ("pending", "blocked")]
            
            if tasks:
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc)
                for t in tasks:
                    created_str = t.get("created_at")
                    if created_str.endswith("Z"): created_str = created_str[:-1] + "+00:00"
                    created_at = datetime.fromisoformat(created_str)
                    if created_at.tzinfo is None: created_at = created_at.replace(tzinfo=timezone.utc)
                    
                    delay_mins = (now - created_at).total_seconds() / 60.0
                    t["Delay"] = f"{delay_mins:.1f}m"
                    if delay_mins > 5.0:
                        t["SLA State"] = "🔴 Breach"
                    elif delay_mins > 2.0:
                        t["SLA State"] = "🟡 Warning"
                    else:
                        t["SLA State"] = "🟢 Normal"
                        
                import pandas as pd
                df = pd.DataFrame(tasks)
                df.rename(columns={"name": "Task Name", "owner": "Owner", "status": "Status"}, inplace=True)
                st.dataframe(df[["Task Name", "Owner", "Status", "Delay", "SLA State"]], use_container_width=True, height=350)
            else:
                st.info("No active tasks found.")
        except Exception as exc:
            st.error(f"Failed to fetch tasks: {exc}")

    with c_right:
        st.markdown('<div class="section-title" style="margin-top: 0;">📜 Recent SLA Breaches</div>', unsafe_allow_html=True)
        try:
            resp_b = client.table("sla_breaches").select("*").order("created_at", desc=True).limit(20).execute()
            breaches = resp_b.data or []
            if breaches:
                import pandas as pd
                df_b = pd.DataFrame(breaches)
                df_b["delay"] = df_b["delay_duration"]
                st.dataframe(df_b[["task_name", "new_owner", "delay", "email_sent"]], use_container_width=True, height=350)
            else:
                st.info("No SLAs breached yet.")
        except Exception as exc:
            st.error(f"Failed to fetch breaches: {exc}")


# ═══════════════════════════════════════════════════════════════════════════════
# LANDING PAGE
# ═══════════════════════════════════════════════════════════════════════════════
def landing_page():
    st.markdown("<h1 style='text-align: center; font-size: 3rem; margin-top: 2rem; color: #38bdf8;'>Autonomous Enterprise Workflow AI</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; font-size: 1.2rem; color: #94a3b8; margin-bottom: 3rem;'>AI-powered multi-agent system for enterprise automation</p>", unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        <div style="background-color: #0f172a; padding: 2rem; border-radius: 10px; border: 1px solid #1e293b; height: 100%;">
            <h3 style="color: #60a5fa; margin-top: 0;">🎯 Core Features</h3>
            <ul style="color: #cbd5e1; font-size: 1.1rem; line-height: 1.8; margin-bottom: 0;">
                <li><strong>Meeting Intelligence</strong>: Generate insights and action items</li>
                <li><strong>Employee Onboarding</strong>: Role-based tasks and dynamic buddy assignment</li>
                <li><strong>Error Recovery</strong>: Self-healing agents intelligently escalate issues</li>
                <li><strong>Live Audit Logs</strong>: Immutable execution traces stored securely in Supabase</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div style="background-color: #0f172a; padding: 2rem; border-radius: 10px; border: 1px solid #1e293b; height: 100%; display: flex; flex-direction: column; justify-content: center; align-items: center;">
            <p style="color: #94a3b8; font-size: 1.1rem; text-align: center; margin-bottom: 2rem;">
                Enter the agent workspace to start automating your enterprise workflows.
            </p>
        </div>
        """, unsafe_allow_html=True)
        # Streamlit doesn't render buttons inside markdown HTML blocks well, so we place it adjacent:
    
    c1, c2, c3 = st.columns([1,1,1])
    with c2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        if st.button("🚀 Login / Start", type="primary", use_container_width=True):
            st.session_state["landing_dismissed"] = True
            st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# ROUTING
# ═══════════════════════════════════════════════════════════════════════════════
if not st.session_state.get("landing_dismissed"):
    landing_page()
elif st.session_state.get("authenticated"):
    main_app()
else:
    login_page()
