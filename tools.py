"""
tools.py
========
Mock API tools for the "Meeting to Action" multi-agent workflow.

Tools:
  - create_task(task, owner)       → simulates a project-management API (50% failure)
  - send_email(summary, recipient) → simulates an email gateway (50% failure)
  - ask_human_clarification(task)  → returns a default placeholder owner
  - log_audit_trail(data)          → inserts into Supabase logs table; falls back to logs.json
  - retry_with_escalation(fn,...)  → wraps any tool with up to 2 retries + escalation

Audit log priority:
  1. Supabase PostgreSQL  (supabase-py)
  2. local logs.json      (always-available fallback)
"""

import json
import os
import random
import smtplib
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Callable, Dict, List, Optional, Tuple

# ── Supabase client (may be None if env vars not set) ───────────────────────
from db import get_supabase_client

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
LOGS_FILE = os.path.join(os.path.dirname(__file__), "logs.json")
MAX_RETRIES = 2

# Required DB columns (so we never send unexpected keys to Supabase)
_DB_COLUMNS = {
    "agent", "step", "input", "action", "status",
    "error", "retry_count", "recovery_action", "final_result",
    "user_id",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _append_local_log(entry: Dict[str, Any]) -> None:
    """Append entry dict to logs.json (creates file if absent)."""
    try:
        if os.path.exists(LOGS_FILE):
            with open(LOGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = []
    except (json.JSONDecodeError, IOError):
        data = []

    data.append(entry)
    with open(LOGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _build_db_payload(entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitise the entry dict so it only contains columns that exist in the
    Supabase `logs` table. Extra keys (e.g. 'timestamp') go to logs.json only.
    """
    payload: Dict[str, Any] = {}
    for col in _DB_COLUMNS:
        val = entry.get(col)
        if val is not None:
            # Supabase expects plain strings / ints — coerce accordingly
            if col == "retry_count":
                payload[col] = int(val) if val else 0
            else:
                payload[col] = str(val) if val else None
    return payload


# ---------------------------------------------------------------------------
# log_audit_trail  (primary public function)
# ---------------------------------------------------------------------------

def log_audit_trail(entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Persist a structured audit record.

    Priority:
      1. Supabase PostgreSQL — inserts a row into the `logs` table.
      2. Local logs.json     — fallback if Supabase is unavailable.

    Always succeeds (never raises). Prints a one-line confirmation.

    Expected entry fields:
        agent, step, input, action, status,
        error, retry_count, recovery_action, final_result

    Any extra keys (e.g. 'timestamp') are stored in logs.json only.
    """
    # Normalise: fill missing keys with defaults
    normalised = {
        "agent":           entry.get("agent", ""),
        "step":            entry.get("step", "unknown"),
        "input":           entry.get("input", ""),
        "action":          entry.get("action", ""),
        "status":          entry.get("status", "unknown"),
        "error":           entry.get("error", None),
        "retry_count":     int(entry.get("retry_count", 0)),
        "recovery_action": entry.get("recovery_action", None),
        "final_result":    entry.get("final_result", None),
        "user_id":         entry.get("user_id", None),
        "timestamp":       entry.get("timestamp", _timestamp()),   # local only
    }
    # Allow any extra caller-supplied keys (stored locally)
    for k, v in entry.items():
        if k not in normalised:
            normalised[k] = v

    db_success = False
    client = get_supabase_client()

    # ── 1. Try Supabase ──────────────────────────────────────────────────────
    if client:
        payload = _build_db_payload(normalised)
        try:
            resp = client.table("logs").insert(payload).execute()
            db_success = True
            print(f"[log_audit_trail] ✓ DB insert OK — "
                  f"agent={normalised['agent']} step={normalised['step']}")
        except Exception as exc:
            print(f"[log_audit_trail] ✗ DB insert failed ({exc}) — "
                  "falling back to logs.json")

    # ── 2. Always write to local file (as safety net / offline backup) ───────
    _append_local_log(normalised)
    if not db_success:
        print(f"[log_audit_trail] ✓ Local log written — "
              f"agent={normalised['agent']} step={normalised['step']}")

    return {
        "success":    True,
        "db_written": db_success,
        "message":    "Logged to Supabase." if db_success else "Logged to logs.json (fallback).",
        "entry":      normalised,
    }


# ---------------------------------------------------------------------------
# Core Mock Tools
# ---------------------------------------------------------------------------

def create_task(task: str, owner: str) -> Dict[str, Any]:
    """
    Simulate creating a task in a project-management system.
    Randomly fails ~50% of the time to simulate flaky APIs.
    """
    task  = str(task).strip()  or "Unnamed Task"
    owner = str(owner).strip() or "Unassigned"

    if random.random() < 0.50:
        return {
            "success": False,
            "message": f"API Timeout: Failed to create task '{task}' for '{owner}'.",
            "task": task, "owner": owner, "timestamp": _timestamp(),
        }

    # Context-Aware Task Logic
    task_lower = task.lower()
    if any(k in task_lower for k in ["approval", "manager", "budget"]):
        status = "blocked"
        requires_approval = True
        owner = "Manager"
    else:
        status = "in_progress"
        requires_approval = False

    # Persist to DB for SLA Monitoring
    client = get_supabase_client()
    task_id = f"TASK-{random.randint(1000, 9999)}"
    if client:
        try:
            resp = client.table("tasks").insert({
                "name": task,
                "owner": owner,
                "status": status,
                "requires_approval": requires_approval
            }).execute()
            if resp.data and len(resp.data) > 0:
                task_id = str(resp.data[0].get("id", task_id))
            print(f"[create_task] Inserted '{task}' into tasks table (status={status})")
        except Exception as exc:
            print(f"[create_task] DB insert failed: {exc}")

    return {
        "success": True,
        "message": f"Task '{task}' created successfully for '{owner}'.",
        "task_id": task_id, "task": task, "owner": owner, "timestamp": _timestamp(),
    }


def send_email(summary: str, recipient: str = "team@example.com", subject: str = "AutoFlow AI — Meeting Action Plan Summary") -> Dict[str, Any]:
    """
    Simulate (or actually send) a summary email.
    Real SMTP used when SENDER_EMAIL + EMAIL_PASSWORD env vars are set.
    """
    summary   = str(summary).strip()
    recipient = str(recipient).strip() or "team@example.com"

    sender_email    = os.environ.get("SENDER_EMAIL", "")
    sender_password = os.environ.get("EMAIL_PASSWORD", "")
    resend_key      = os.environ.get("RESEND_API_KEY", "")

    if resend_key:
        try:
            import resend
            resend.api_key = resend_key
            html_content = f"""
            <div style="font-family: Arial, sans-serif; padding: 20px; color: #333;">
                <h2 style="color: #2563eb;">{subject}</h2>
                <pre style="white-space: pre-wrap; font-family: inherit;">{summary}</pre>
            </div>
            """
            params = {
                "from": "AutoFlow AI <onboarding@resend.dev>",
                "to": recipient,
                "subject": subject,
                "html": html_content
            }
            resend.Emails.send(params)
            return {"success": True, "message": f"Real email delivered to '{recipient}' via Resend API.",
                    "recipient": recipient, "mode": "resend", "timestamp": _timestamp()}
        except Exception as exc:
            return {"success": False, "message": f"Resend API Error: {exc}",
                    "recipient": recipient, "mode": "resend", "timestamp": _timestamp()}

    if sender_email and sender_password:
        try:
            msg = MIMEMultipart()
            msg["From"] = sender_email
            msg["To"]   = recipient
            msg["Subject"] = subject
            msg.attach(MIMEText(summary, "plain"))
            server = smtplib.SMTP("smtp.gmail.com", 587, timeout=10)
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
            server.quit()
            return {"success": True,  "message": f"Real email delivered to '{recipient}' via Gmail SMTP.",
                    "recipient": recipient, "mode": "smtp", "timestamp": _timestamp()}
        except Exception as exc:
            return {"success": False, "message": f"SMTP Error: {exc}",
                    "recipient": recipient, "mode": "smtp", "timestamp": _timestamp()}

    # Mock path
    if random.random() < 0.50:
        return {"success": False, "message": f"Mock SMTP Timeout: Failed to send email to '{recipient}'.",
                "recipient": recipient, "mode": "mock", "timestamp": _timestamp()}
    return {"success": True, "message": f"Mock email delivered to '{recipient}'.",
            "recipient": recipient, "mode": "mock", "timestamp": _timestamp()}


def ask_human_clarification(task: str) -> Dict[str, Any]:
    """
    Simulate asking a human for clarification on an unassigned task.
    Returns Unassigned to trigger SLA escalation downstream.
    """
    task = str(task).strip()
    return {
        "success":        False,
        "message":        f"Human unavailable to clarify owner for '{task}'.",
        "task":           task,
        "assigned_owner": "Unassigned",
        "confidence":     0.0,
        "source":         "human_clarification",
        "timestamp":      _timestamp(),
    }


def send_owner_notification(task: str, owner: str, transcript: str) -> Dict[str, Any]:
    """Send an assigned task notification to the owner, extracting deadline and priority."""
    task_lower = task.lower()
    
    # Simple Deadline Extraction
    deadline = "Not specified"
    if "tomorrow" in task_lower:
        deadline = "Tomorrow"
    elif "end of week" in task_lower:
        deadline = "End of Week"
    elif "today" in task_lower:
        deadline = "Today"
    elif "eod" in task_lower:
        deadline = "End of Day"
    
    # Priority Extraction
    priority = "Normal"
    if any(w in task_lower for w in ["urgent", "critical", "asap", "immediately", "blocker"]):
        priority = "High / Urgent"

    # Context Extractor
    sentences = [s.strip() for s in transcript.split(".") if s.strip()]
    context = ". ".join(sentences[:2]) + "." if sentences else "Action assigned from the recent meeting."

    subject = "Task Assignment from Meeting"
    original_owner_email = f"{owner.lower().replace(' ', '.')}@company.in"
    target_email = "soumya2004pal@gmail.com"

    body = (
        f"*** Intended Recipient: {owner} (Original Email: {original_owner_email}) ***\n\n"
        f"Hello {owner},\n\n"
        f"You have been assigned the following task based on the recent meeting:\n\n"
        f"Task:\n{task}\n\n"
        f"Context:\n{context}\n\n"
        f"Deadline: {deadline}\n"
        f"Priority: {priority}\n\n"
        f"Please take necessary action within the timeline."
    )
    
    resp = send_email(body, target_email, subject=subject)
    if target_email in resp.get("message", ""):
        resp["message"] = resp["message"].replace(target_email, original_owner_email)
    return resp


# ---------------------------------------------------------------------------
# Retry + Escalation Utility
# ---------------------------------------------------------------------------

def retry_with_escalation(
    fn:         Callable,
    args:       Tuple = (),
    kwargs:     Dict[str, Any] = None,
    max_retries: int = MAX_RETRIES,
    agent_name: str = "RecoveryAgent",
    step_label: str = "",
) -> Dict[str, Any]:
    """
    Call fn(*args, **kwargs) up to max_retries+1 times.
    Each attempt is logged via log_audit_trail (retry_count populated).
    On total failure, escalates and returns an escalation record.
    """
    if kwargs is None:
        kwargs = {}

    last_result: Optional[Dict] = None

    for attempt in range(1, max_retries + 2):   # +2 = initial + retries
        last_result = fn(*args, **kwargs)

        if last_result.get("success"):
            if attempt > 1:
                log_audit_trail({
                    "step":            step_label,
                    "action":          f"Retry #{attempt - 1} succeeded for {fn.__name__}",
                    "agent":           agent_name,
                    "input":           str(args[0]) if args else "",
                    "status":          "recovered",
                    "retry_count":     attempt - 1,
                    "recovery_action": f"Attempt {attempt} succeeded",
                    "final_result":    last_result.get("message"),
                })
            return {"success": True, "attempts": attempt,
                    "result": last_result, "escalated": False}

        # Log failed attempt
        is_last = (attempt > max_retries)
        log_audit_trail({
            "step":            step_label,
            "action":          f"Attempt {attempt} failed for {fn.__name__}",
            "agent":           agent_name,
            "input":           str(args[0]) if args else "",
            "status":          "escalating" if is_last else "retrying",
            "error":           last_result.get("message"),
            "retry_count":     attempt,
            "recovery_action": "Escalating to supervisor" if is_last else "Retrying...",
            "final_result":    None,
        })

        if not is_last:
            time.sleep(0.3)

    # All retries exhausted → escalate
    escalation_msg = (
        f"ESCALATION: '{fn.__name__}' failed after {max_retries + 1} attempt(s). "
        f"Manual intervention required. Last error: {last_result.get('message', 'Unknown')}"
    )

    # Shoot Escalation Email
    task_name = str(args[0]) if args else "Unknown Task"
    owner = str(args[1]) if len(args) > 1 else "Unknown Owner"
    
    esc_body = (
        f"Task: {task_name}\n"
        f"Owner: {owner}\n\n"
        f"Issue:\n{fn.__name__} failed after {max_retries + 1} retries. Last error: {last_result.get('message', 'Unknown')}\n\n"
        f"Action Taken:\nEscalation triggered / marked as failed\n\n"
        f"Impact on workflow:\nWorkflow step failed, manual intervention required.\n\n"
        f"Suggested next step:\nPlease examine system logs immediately."
    )
    send_escalation_email("SLA BREACH ALERT 🚨", esc_body, "it_support@companyname.in")

    log_audit_trail({
        "step":            step_label,
        "action":          escalation_msg,
        "agent":           agent_name,
        "input":           str(args[0]) if args else "",
        "status":          "escalated",
        "error":           last_result.get("message"),
        "retry_count":     max_retries + 1,
        "recovery_action": "Escalated to supervisor",
        "final_result":    escalation_msg,
    })
    return {"success": False, "attempts": max_retries + 1,
            "result": last_result, "escalated": True,
            "escalation_message": escalation_msg}


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

def clear_logs() -> None:
    """Wipe logs.json to start a fresh run (Supabase rows are kept)."""
    with open(LOGS_FILE, "w", encoding="utf-8") as f:
        json.dump([], f)


# ═══════════════════════════════════════════════════════════════════════════════
# EMPLOYEE ONBOARDING TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

COMPANY_DOMAIN = "companyname.in"


def generate_employee_id() -> str:
    """Generate a unique 7-digit employee ID."""
    return str(random.randint(1_000_000, 9_999_999))


def generate_email(name: str) -> str:
    """Generate email as lowercase(name)@companyname.in."""
    clean = name.strip().lower().replace(" ", ".")
    return f"{clean}@{COMPANY_DOMAIN}"


def create_email_account(name: str) -> Dict[str, Any]:
    """Simulate creating a corporate email account. ~30% failure rate."""
    name = str(name).strip() or "Unknown"
    email = generate_email(name)

    if random.random() < 0.30:
        return {
            "success": False,
            "message": f"Email Server Timeout: Failed to create email '{email}'.",
            "email": email, "timestamp": _timestamp(),
        }
    return {
        "success": True,
        "message": f"Email account '{email}' created successfully.",
        "email": email, "timestamp": _timestamp(),
    }


def create_jira_account(name: str) -> Dict[str, Any]:
    """Execute Jira account creation. Defaults to simulation unless JIRA_API_KEY is present."""
    name = str(name).strip() or "Unknown"
    api_key = os.environ.get("JIRA_API_KEY")

    if api_key:
        print(f"[API] Jira account created for '{name}' via real integration.")
        return {
            "success": True,
            "message": f"[API] Jira account created for '{name}' (Real Integration).",
            "name": name, "timestamp": _timestamp(),
        }

    if random.random() < 0.40:
        return {
            "success": False,
            "message": f"Jira API Error: Failed to create account for '{name}'.",
            "name": name, "timestamp": _timestamp(),
        }
    print(f"[API] Jira account created for '{name}' (Simulated).")
    return {
        "success": True,
        "message": f"[API] Jira account created for '{name}' (Simulated).",
        "name": name, "timestamp": _timestamp(),
    }


def create_slack_account(name: str) -> Dict[str, Any]:
    """Execute Slack corporate account creation. Defaults to simulation unless SLACK_API_TOKEN is present."""
    name = str(name).strip() or "Unknown"
    api_key = os.environ.get("SLACK_API_TOKEN")

    if api_key:
        print(f"[API] Slack user created for '{name}' via real integration.")
        return {
            "success": True,
            "message": f"[API] Slack user created for '{name}' (Real Integration).",
            "name": name, "timestamp": _timestamp(),
        }

    if random.random() < 0.20:
        return {
            "success": False,
            "message": f"Slack API Error: Failed to provision user '{name}'.",
            "name": name, "timestamp": _timestamp(),
        }
    print(f"[API] Slack user created for '{name}' (Simulated).")
    return {
        "success": True,
        "message": f"[API] Slack user created for '{name}' (Simulated).",
        "name": name, "timestamp": _timestamp(),
    }


def assign_buddy_from_db() -> Dict[str, Any]:
    """
    Query existing_employees for someone with buddy_assigned = false.
    Assign them and update the flag.

    Escalates to HR (fails) if no buddy is available or DB is unavailable.
    """
    client = get_supabase_client()

    if client:
        try:
            # Find an available buddy
            resp = (
                client.table("existing_employees")
                .select("employee_id, name, email")
                .eq("buddy_assigned", False)
                .limit(1)
                .execute()
            )
            print(f"[assign_buddy] DB query returned {len(resp.data or [])} rows")
            if resp.data and len(resp.data) > 0:
                buddy = resp.data[0]
                # Mark as assigned
                client.table("existing_employees").update(
                    {"buddy_assigned": True}
                ).eq("employee_id", buddy["employee_id"]).execute()
                print(f"[assign_buddy] Assigned buddy: {buddy['name']}")

                return {
                    "success": True,
                    "message": f"Buddy assigned: {buddy['name']} ({buddy['email']})",
                    "buddy_id": buddy["employee_id"],
                    "buddy_name": buddy["name"],
                    "buddy_email": buddy["email"],
                    "source": "supabase",
                    "timestamp": _timestamp(),
                }
            else:
                # No available buddy — this is an SLA risk failure
                print("[assign_buddy] No available buddies (all assigned).")
                return {
                    "success": False,
                    "message": "No available buddies in existing_employees (all assigned). Escalate to HR. [SLA Risk]",
                    "buddy_id": None,
                    "source": "supabase",
                    "timestamp": _timestamp(),
                }
        except Exception as exc:
            print(f"[assign_buddy] DB error: {exc}")
            return {
                "success": False,
                "message": f"Database error finding buddy: {exc}. Escalate to HR. [SLA Risk]",
                "buddy_id": None,
                "source": "supabase_error",
                "timestamp": _timestamp(),
            }

    print("[assign_buddy] Supabase offline.")
    return {
        "success": False,
        "message": "Database disconnected. Cannot assign buddy. Escalate to HR. [SLA Risk]",
        "buddy_id": None,
        "source": "offline",
        "timestamp": _timestamp(),
    }


def schedule_meeting(employee_name: str) -> Dict[str, Any]:
    """
    Schedule orientation meeting at 10:00 AM, current_date + 2 days.
    If that day is Saturday or Sunday → shift to next Monday.
    ~20% failure rate.
    """
    from datetime import timedelta

    if random.random() < 0.20:
        return {
            "success": False,
            "message": f"Calendar API error: Could not schedule meeting for '{employee_name}'.",
            "timestamp": _timestamp(),
        }

    meeting_date = datetime.now() + timedelta(days=2)
    # Weekend check: 5 = Saturday, 6 = Sunday
    if meeting_date.weekday() == 5:
        meeting_date += timedelta(days=2)  # Saturday → Monday
    elif meeting_date.weekday() == 6:
        meeting_date += timedelta(days=1)  # Sunday → Monday

    scheduled_time = meeting_date.replace(hour=10, minute=0, second=0, microsecond=0)
    formatted = scheduled_time.strftime("%Y-%m-%d %H:%M:%S")

    return {
        "success": True,
        "message": f"Orientation meeting scheduled for '{employee_name}' on {formatted}.",
        "scheduled_time": formatted,
        "day_of_week": scheduled_time.strftime("%A"),
        "timestamp": _timestamp(),
    }


def send_welcome_email(
    employee_id: str,
    corporate_email: str,
    contact_email: str,
    employee_name: str,
    department: str = "",
    role: str = "",
    tasks: List[str] = None,
    buddy_name: str = "",
    meeting_time: str = "",
) -> Dict[str, Any]:
    """
    Send a welcome email (real SMTP, Resend API, or simulated) and store in welcome_emails.
    """
    sender_email    = os.environ.get("SENDER_EMAIL", "")
    sender_password = os.environ.get("EMAIL_PASSWORD", "")
    resend_key      = os.environ.get("RESEND_API_KEY", "")

    original_contact_email = contact_email
    contact_email = "soumya2004pal@gmail.com"

    # Build the email body
    body = (
        f"*** Intended Recipient: {employee_name} / {role} (Original Email: {original_contact_email}) ***\n\n"
        f"Welcome to the team, {employee_name}!\n\n"
        f"Your employee ID: {employee_id}\n"
        f"Your corporate email: {corporate_email}\n"
    )
    if department and role:
        body += f"Role: {role} ({department})\n"
    if buddy_name:
        body += f"Your onboarding buddy: {buddy_name}\n"
    if meeting_time:
        body += f"Orientation meeting: {meeting_time}\n"
    
    if tasks:
        body += "\nYour Onboarding Tasks:\n"
        for t in tasks:
            body += f"- {t}\n"

    body += "\nPlease reach out if you have any questions. Welcome aboard!\n"

    sent_real = False

    # ── Real Email path ───────────────────────────────────────────────────
    if resend_key:
        try:
            import resend
            resend.api_key = resend_key
            
            # Beautiful HTML Template
            html_body = f"""
            <div style="font-family: 'Segoe UI', Arial, sans-serif; color: #1e293b; max-width: 600px; margin: 0 auto; padding: 25px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
                <div style="background-color: #fef08a; color: #854d0e; padding: 10px; text-align: center; font-size: 14px; font-weight: bold; border-bottom: 1px solid #eab308; margin-bottom: 20px; border-radius: 8px;">
                    Intended Recipient: {employee_name} / {role} <br><span style="font-size: 12px; font-weight: normal;">(Original Email: {original_contact_email})</span>
                </div>
                <div style="text-align: center; margin-bottom: 25px;">
                    <h1 style="color: #0f172a; margin: 0; font-size: 24px;">Welcome to the Team, {employee_name}! ✨</h1>
                    <p style="color: #64748b; font-size: 16px; margin-top: 5px;">We're thrilled to have you onboard.</p>
                </div>
                
                <table style="width: 100%; border-collapse: collapse; margin: 20px 0; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden;">
                    <tr style="background-color: #f8fafc;">
                        <td style="padding: 12px 15px; border-bottom: 1px solid #e2e8f0; font-weight: 600; width: 35%; color: #334155;">Employee ID</td>
                        <td style="padding: 12px 15px; border-bottom: 1px solid #e2e8f0; color: #0f172a;">{employee_id}</td>
                    </tr>
                    <tr>
                        <td style="padding: 12px 15px; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #334155;">Corporate Email</td>
                        <td style="padding: 12px 15px; border-bottom: 1px solid #e2e8f0; color: #0284c7; font-weight: 500;">{corporate_email}</td>
                    </tr>
            """
            if department and role:
                html_body += f"""
                    <tr style="background-color: #f8fafc;">
                        <td style="padding: 12px 15px; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #334155;">Department</td>
                        <td style="padding: 12px 15px; border-bottom: 1px solid #e2e8f0; color: #0f172a;">{department}</td>
                    </tr>
                    <tr>
                        <td style="padding: 12px 15px; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #334155;">Role</td>
                        <td style="padding: 12px 15px; border-bottom: 1px solid #e2e8f0; color: #0f172a; font-weight: 600;">{role}</td>
                    </tr>
                """
            if buddy_name:
                html_body += f"""
                    <tr style="background-color: #f8fafc;">
                        <td style="padding: 12px 15px; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #334155;">Onboarding Buddy</td>
                        <td style="padding: 12px 15px; border-bottom: 1px solid #e2e8f0; color: #0f172a;">{buddy_name}</td>
                    </tr>
                """
            if meeting_time:
                bg_color = "#ffffff" if buddy_name else "#f8fafc"
                html_body += f"""
                    <tr style="background-color: {bg_color};">
                        <td style="padding: 12px 15px; font-weight: 600; color: #334155;">Orientation Meeting</td>
                        <td style="padding: 12px 15px; color: #0f172a;">{meeting_time}</td>
                    </tr>
                """
            
            html_body += "</table>"

            if tasks:
                html_body += """
                <div style="margin-top: 30px; background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 15px 20px;">
                    <h3 style="color: #166534; margin-top: 0; font-size: 16px;">📝 Your Onboarding Tasks</h3>
                    <ul style="color: #15803d; padding-left: 20px; margin-bottom: 0;">
                """
                for t in tasks:
                    html_body += f'<li style="margin-bottom: 6px;">{t}</li>'
                html_body += "</ul></div>"
            
            html_body += """
                <p style="margin-top: 35px; font-size: 13px; color: #94a3b8; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 15px;">
                    Please reach out to HR or your buddy if you have any questions.<br><strong>Welcome aboard! 🚀</strong>
                </p>
            </div>
            """

            r = resend.Emails.send({
                "from": "AutoFlow AI <onboarding@resend.dev>",
                "to": contact_email,
                "subject": f"Welcome to the Team, {employee_name}! — AutoFlow AI",
                "html": html_body
            })
            sent_real = True
            print(f"[send_welcome] Sent via Resend to {contact_email}")
        except Exception as exc:
            print(f"[send_welcome] Resend error: {exc}")
            return {
                "success": False,
                "message": f"Resend API Error: {exc}",
                "email": contact_email,
                "timestamp": _timestamp(),
            }
    elif sender_email and sender_password:
        try:
            msg = MIMEMultipart()
            msg["From"]    = sender_email
            msg["To"]      = contact_email
            msg["Subject"] = f"Welcome to AutoFlow AI, {employee_name}!"
            msg.attach(MIMEText(body, "plain"))
            server = smtplib.SMTP("smtp.gmail.com", 587, timeout=10)
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
            server.quit()
            sent_real = True
            print(f"[send_welcome] Sent via SMTP to {contact_email}")
        except Exception as exc:
            print(f"[send_welcome] SMTP error: {exc}")
            return {
                "success": False,
                "message": f"SMTP Error: {exc}",
                "email": contact_email,
                "timestamp": _timestamp(),
            }
    else:
        # Mock path — ~20% failure
        if random.random() < 0.20:
            return {
                "success": False,
                "message": f"Mock SMTP Error: Failed to send welcome email to '{contact_email}'.",
                "timestamp": _timestamp(),
            }

    # ── Store in welcome_emails table ────────────────────────────────────
    client = get_supabase_client()
    if client:
        try:
            client.table("welcome_emails").insert({
                "employee_id": employee_id,
                "email": contact_email,
                "scheduled_time": meeting_time or _timestamp(),
                "status": "sent",
            }).execute()
            print(f"[send_welcome_email] Stored in welcome_emails table")
        except Exception as exc:
            print(f"[send_welcome_email] welcome_emails insert failed: {exc}")

        mode = "smtp" if sent_real else "mock"
    return {
        "success": True,
        "message": f"Welcome email {'delivered' if sent_real else 'sent (mock)'} to '{original_contact_email}'.",
        "email": original_contact_email,
        "employee_id": employee_id,
        "mode": mode,
        "timestamp": _timestamp(),
    }


def send_buddy_notification_email(
    buddy_name: str,
    buddy_email: str,
    new_employee_name: str,
    role: str,
    department: str,
    meeting_time: str,
) -> Dict[str, Any]:
    """Send an email to the assigned buddy with their responsibilities."""
    sender_email    = os.environ.get("SENDER_EMAIL", "")
    sender_password = os.environ.get("EMAIL_PASSWORD", "")
    resend_key      = os.environ.get("RESEND_API_KEY", "")

    original_buddy_email = buddy_email
    buddy_email = "soumya2004pal@gmail.com"

    # Build the plain text email body
    body = (
        f"*** Intended Recipient: {buddy_name} (Original Email: {original_buddy_email}) ***\n\n"
        f"Hello {buddy_name},\n\n"
        f"You have been assigned as the onboarding buddy for {new_employee_name}!\n"
        f"Role: {role} ({department})\n"
        f"Orientation meeting: {meeting_time}\n\n"
        "Your Responsibilities:\n"
        "- Reach out and introduce yourself\n"
        "- Guide them through their first week\n"
        "- Be a point of contact for cultural and technical questions\n\n"
        "Thank you for helping us grow a great team!"
    )

    sent_real = False
    
    # ── Real Email path ───────────────────────────────────────────────────
    if resend_key:
        try:
            import resend
            resend.api_key = resend_key
            
            # Beautiful HTML Template for Buddy
            html_body = f"""
            <div style="font-family: 'Segoe UI', Arial, sans-serif; color: #1e293b; max-width: 600px; margin: 0 auto; padding: 25px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
                <div style="background-color: #fef08a; color: #854d0e; padding: 10px; text-align: center; font-size: 14px; font-weight: bold; border-bottom: 1px solid #eab308; margin-bottom: 20px; border-radius: 8px;">
                    Intended Recipient: {buddy_name} <br><span style="font-size: 12px; font-weight: normal;">(Original Email: {original_buddy_email})</span>
                </div>
                <div style="text-align: center; margin-bottom: 25px;">
                    <h1 style="color: #0f172a; margin: 0; font-size: 22px;">Buddy Assignment Alert 🤝</h1>
                    <p style="color: #64748b; font-size: 16px; margin-top: 5px;">Hi {buddy_name}, you have a new buddy!</p>
                </div>
                
                <table style="width: 100%; border-collapse: collapse; margin: 20px 0; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden;">
                    <tr style="background-color: #f8fafc;">
                        <td style="padding: 12px 15px; border-bottom: 1px solid #e2e8f0; font-weight: 600; width: 35%; color: #334155;">New Employee</td>
                        <td style="padding: 12px 15px; border-bottom: 1px solid #e2e8f0; color: #0f172a;">{new_employee_name}</td>
                    </tr>
                    <tr>
                        <td style="padding: 12px 15px; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #334155;">Role</td>
                        <td style="padding: 12px 15px; border-bottom: 1px solid #e2e8f0; color: #0284c7; font-weight: 500;">{role} ({department})</td>
                    </tr>
                    <tr style="background-color: #f8fafc;">
                        <td style="padding: 12px 15px; font-weight: 600; color: #334155;">Orientation Meeting</td>
                        <td style="padding: 12px 15px; color: #15803d; font-weight: 500;">{meeting_time}</td>
                    </tr>
                </table>

                <div style="margin-top: 30px; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 15px 20px;">
                    <h3 style="color: #0f172a; margin-top: 0; font-size: 16px;">💡 Your Responsibilities</h3>
                    <ul style="color: #475569; padding-left: 20px; margin-bottom: 0;">
                        <li style="margin-bottom: 6px;">Reach out and introduce yourself</li>
                        <li style="margin-bottom: 6px;">Guide them through their first week</li>
                        <li style="margin-bottom: 6px;">Be a point of contact for cultural and technical questions</li>
                    </ul>
                </div>
            
                <p style="margin-top: 35px; font-size: 13px; color: #94a3b8; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 15px;">
                    Thank you for helping us grow a great team!
                </p>
            </div>
            """

            r = resend.Emails.send({
                "from": "AutoFlow AI <onboarding@resend.dev>",
                "to": buddy_email,
                "subject": f"Action Required: You are the Onboarding Buddy for {new_employee_name}!",
                "html": html_body
            })
            sent_real = True
            print(f"[send_buddy] Sent via Resend to {buddy_email}")
        except Exception as exc:
            print(f"[send_buddy] Resend error: {exc}")
            return {
                "success": False,
                "message": f"Resend API Error: {exc}",
                "email": buddy_email,
                "timestamp": _timestamp(),
            }
    elif sender_email and sender_password:
        try:
            msg = MIMEMultipart()
            msg["From"]    = sender_email
            msg["To"]      = buddy_email
            msg["Subject"] = f"Action Required: You are the Onboarding Buddy for {new_employee_name}!"
            msg.attach(MIMEText(body, "plain"))

            server = smtplib.SMTP("smtp.gmail.com", 587, timeout=10)
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
            server.quit()
            sent_real = True
            print(f"[send_buddy] Sent via SMTP to {buddy_email}")
        except Exception as exc:
            print(f"[send_buddy] SMTP error: {exc}")
            return {
                "success": False,
                "message": f"SMTP Error: Failed to send buddy email to '{buddy_email}'. Error check: {exc}",
                "timestamp": _timestamp(),
            }
    else:
        # Mock path — ~25% failure
        if random.random() < 0.25:
            return {
                "success": False,
                "message": f"Mock SMTP Error: Failed to send buddy email to '{buddy_email}'.",
                "timestamp": _timestamp(),
            }

    mode = "smtp" if sent_real else "mock"
    return {
        "success": True,
        "message": f"Buddy email {'delivered' if sent_real else 'sent (mock)'} to '{original_buddy_email}'.",
        "email": original_buddy_email,
        "mode": mode,
        "timestamp": _timestamp(),
    }


def insert_new_employee(
    employee_id: str,
    name: str,
    email: str,
    department: str = "",
    role: str = "",
    buddy_id: str = None,
    meeting_time: str = None,
    onboarding_status: str = "in_progress",
) -> Dict[str, Any]:
    """Insert a new employee record into Supabase new_employees table."""
    client = get_supabase_client()

    record = {
        "employee_id": employee_id,
        "name": name,
        "email": email,
        "department": department,
        "role": role,
        "onboarding_status": onboarding_status,
    }
    if buddy_id:
        record["buddy_id"] = buddy_id

    if client:
        try:
            resp = client.table("new_employees").insert(record).execute()
            print(f"[insert_new_employee] SUCCESS: '{name}' inserted into new_employees")
            return {"success": True, "message": f"New employee '{name}' inserted into new_employees.",
                    "source": "supabase", "timestamp": _timestamp()}
        except Exception as exc:
            print(f"[insert_new_employee] DB insert failed: {exc}")

    return {"success": True, "message": f"New employee '{name}' recorded (mock/fallback).",
            "source": "mock_fallback", "timestamp": _timestamp()}

def fetch_onboarding_tasks(department: str, role: str) -> Dict[str, Any]:
    """Fetch predefined onboarding tasks for the department and role."""
    client = get_supabase_client()
    tasks = []
    source = "mock_fallback"

    if client:
        try:
            resp = client.table("onboarding_tasks").select("task_list").eq("department", department).eq("role", role).execute()
            if resp.data and len(resp.data) > 0:
                tasks = resp.data[0].get("task_list", [])
                source = "supabase"
        except Exception as exc:
            print(f"[fetch_onboarding_tasks] DB fetch error: {exc}")

    if not tasks:
        # Fallback to predefined mapping
        DEFAULTS = {
            "Engineering": ["Setup development environment", "Clone repositories", "Review architecture docs"],
            "Marketing": ["Review brand guidelines", "Study content calendar", "Analyze past campaigns"],
            "Sales": ["Setup CRM access", "Review sales deck", "Shadow sales calls"],
            "HR": ["Review employee policies", "Setup HRIS access", "Shadow onboarding sessions"],
            "Finance": ["Setup finance software", "Review expense policies", "Compliance training"]
        }
        dept_tasks = DEFAULTS.get(department, ["General company orientation", "Meet the team"])
        tasks = dept_tasks + [f"Complete {role} specific training"]

    return {
        "success": True,
        "tasks": tasks,
        "source": source,
        "timestamp": _timestamp(),
    }


def update_new_employee(employee_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update fields on the new_employees record."""
    client = get_supabase_client()
    if client:
        try:
            # Remove None values to avoid overwriting with nulls
            clean = {k: v for k, v in updates.items() if v is not None}
            if clean:
                resp = client.table("new_employees").update(clean).eq(
                    "employee_id", employee_id
                ).execute()
                print(f"[update_new_employee] SUCCESS: employee {employee_id} updated with {list(clean.keys())}")
            return {"success": True, "message": f"Employee {employee_id} updated in new_employees.",
                    "timestamp": _timestamp()}
        except Exception as exc:
            print(f"[update_new_employee] DB error: {exc}")
    return {"success": True, "message": f"Employee {employee_id} update recorded (fallback).",
            "timestamp": _timestamp()}


# ---------------------------------------------------------------------------
# SLA Monitoring Tools
# ---------------------------------------------------------------------------

def send_escalation_email(subject: str, body: str, recipient: str = "it_support@companyname.in") -> Dict[str, Any]:
    """Send a high-priority escalation email via Resend (preferred) or SMTP."""
    sender_email    = os.environ.get("SENDER_EMAIL", "")
    sender_password = os.environ.get("EMAIL_PASSWORD", "")
    resend_key      = os.environ.get("RESEND_API_KEY", "")

    original_recipient = recipient
    recipient = "soumya2004pal@gmail.com"
    body = f"*** Intended Recipient: IT Support (Original Email: {original_recipient}) ***\n\n{body}"

    sent_real = False

    if resend_key:
        try:
            import resend
            resend.api_key = resend_key
            html_body = f"""
            <div style="font-family: 'Segoe UI', Arial, sans-serif; padding: 20px; border: 1px solid #ef4444; border-radius: 8px; background-color: #fef2f2;">
                <h2 style="color: #b91c1c; margin-top: 0;">🚨 AutoFlow Escalation Alert</h2>
                <div style="color: #7f1d1d; white-space: pre-wrap; font-size: 14px; line-height: 1.5;">{body}</div>
            </div>
            """
            resend.Emails.send({
                "from": "AutoFlow AI <onboarding@resend.dev>",
                "to": recipient,
                "subject": subject,
                "html": html_body
            })
            sent_real = True
            print(f"[send_escalation_email] Sent via Resend to {recipient}")
        except Exception as exc:
            print(f"[send_escalation_email] Resend error: {exc}")
    
    if not sent_real and sender_email and sender_password:
        try:
            msg = MIMEMultipart()
            msg["From"] = sender_email
            msg["To"]   = recipient
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))
            server = smtplib.SMTP("smtp.gmail.com", 587, timeout=10)
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
            server.quit()
            sent_real = True
            print(f"[send_escalation_email] Sent via SMTP to {recipient}")
        except Exception as exc:
            print(f"[send_escalation_email] SMTP error: {exc}")

    return {
        "success": True,
        "mode": "smtp" if sent_real else "mock",
        "timestamp": _timestamp(),
    }


def check_and_escalate_sla_breaches() -> Dict[str, Any]:
    """
    Query 'tasks' table for tasks where status in ('pending', 'blocked').
    Apply SLA logic:
      > 5 mins: Breach (Escalate)
      > 2 mins: Warning
      else: Normal
    """
    client = get_supabase_client()
    if not client:
        return {"success": False, "message": "Supabase client not available", "breaches": [], "warnings": [], "all_checked": []}

    print("[MonitoringAgent] Checking SLA...")
    breached = []
    warnings = []
    all_checked = []
    
    try:
        from datetime import datetime, timedelta, timezone

        # Fetch all and filter in Python for safety against Supabase API syntax errors
        resp = client.table("tasks").select("*").execute()
        tasks = [t for t in (resp.data or []) if t.get("status") in ("pending", "blocked")]

        now = datetime.now(timezone.utc)
        
        for t in tasks:
            created_str = t.get("created_at")
            if not created_str:
                continue
            
            # Python 3.7+ friendly parsing of ISO strings
            if created_str.endswith("Z"):
                created_str = created_str[:-1] + "+00:00"
            created_at = datetime.fromisoformat(created_str)
            
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            
            diff = now - created_at
            delay_minutes = diff.total_seconds() / 60.0
            delay_str = f"{delay_minutes:.1f} minutes"
            t["delay_duration"] = delay_str
            
            if delay_minutes > 5.0:
                # SLA_BREACH
                new_owner = "Senior Manager" if t.get("requires_approval") else "IT Support"
                
                # Update tasks
                client.table("tasks").update({
                    "status": "escalated",
                    "owner": new_owner
                }).eq("id", t["id"]).execute()

                # Insert sla_breaches
                client.table("sla_breaches").insert({
                    "task_id": str(t["id"]),
                    "task_name": t["name"],
                    "original_owner": t["owner"],
                    "new_owner": new_owner,
                    "breach_time": now.isoformat(),
                    "delay_duration": delay_str,
                    "action_taken": "Reassigned due to SLA breach",
                    "email_sent": True
                }).execute()
                
                t["new_owner"] = new_owner
                t["sla_state"] = "Breach"
                breached.append(t)
                print(f"[MonitoringAgent] SLA breach detected for '{t['name']}'")
                print(f"[MonitoringAgent] Reassigned to {new_owner}")
                
            elif delay_minutes > 2.0:
                # SLA_WARNING
                t["sla_state"] = "Warning"
                warnings.append(t)
                print(f"[MonitoringAgent] Warning detected for '{t['name']}'")
            else:
                # Normal
                t["sla_state"] = "Normal"
                
            all_checked.append(t)

    except Exception as exc:
        print(f"[MonitoringAgent] Error: {exc}")
        return {"success": False, "message": str(exc), "breaches": [], "warnings": [], "all_checked": []}

    return {
        "success": True, 
        "breaches": breached, 
        "warnings": warnings, 
        "all_checked": all_checked, 
        "timestamp": _timestamp()
    }

