"""
db.py
=====
Supabase client singleton + authentication helpers for AutoFlow AI.

Usage:
    from db import get_supabase_client, sign_in, sign_up, sign_out

The client is created once on first call (lazy init) with a 10-second timeout.
If SUPABASE_URL / SUPABASE_KEY are missing, returns None.
"""

import os
import threading
from typing import Any, Dict, Optional, Tuple

# ── Load .env ────────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass

# ── Module-level singleton ───────────────────────────────────────────────────
_client = None
_initialised = False
_lock = threading.Lock()


def get_supabase_client():
    """
    Return the shared Supabase client (or None if unavailable).
    First call initialises with a 10-second timeout.
    """
    global _client, _initialised

    with _lock:
        if _initialised:
            return _client

        url = os.environ.get("SUPABASE_URL", "").strip()
        key = (
            os.environ.get("SUPABASE_ANON_KEY", "").strip()
            or os.environ.get("SUPABASE_KEY", "").strip()
        )

        if not url or not key:
            print("[db.py] WARNING: SUPABASE_URL / SUPABASE_KEY not set — "
                  "falling back to logs.json.")
            _initialised = True
            return None

        result_holder = [None]

        def _create():
            try:
                from supabase import create_client  # type: ignore
                result_holder[0] = create_client(url, key)
            except Exception as exc:
                print(f"[db.py] ERROR: Supabase init failed: {exc}")

        t = threading.Thread(target=_create, daemon=True)
        t.start()
        t.join(timeout=30)  # Increased from 10 to 30 for slow Render environments

        if result_holder[0] is not None:
            _client = result_holder[0]
            _initialised = True
        else:
            print("[db.py] ERROR: Timeout or failure connecting to Supabase. Will retry next time.")
            _initialised = False  # Do not cache a failure state permanently

        if _client:
            print(f"[db.py] SUCCESS: Supabase connected -> {url[:50]}...")
        else:
            print("[db.py] WARNING: Supabase unavailable — falling back to logs.json.")

        return _client


def reset_client() -> None:
    """Force re-initialisation on next call."""
    global _client, _initialised
    with _lock:
        _client = None
        _initialised = False


# ─────────────────────────────────────────────────────────────────────────────
# AUTHENTICATION HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def sign_in(email: str, password: str) -> Tuple[bool, Dict[str, Any]]:
    """
    Sign in with email + password via Supabase Auth.

    Returns:
        (True,  {"user_id": "...", "email": "...", "access_token": "..."})
        (False, {"error": "error message"})
    """
    client = get_supabase_client()
    if not client:
        return False, {"error": "Supabase is not configured. Check .env file."}

    try:
        resp = client.auth.sign_in_with_password({
            "email": email.strip(),
            "password": password,
        })

        user = resp.user
        session = resp.session

        if user and session:
            return True, {
                "user_id": user.id,
                "email": user.email,
                "access_token": session.access_token,
                "created_at": str(getattr(user, "created_at", "")),
                "last_sign_in_at": str(getattr(user, "last_sign_in_at", "")),
            }
        return False, {"error": "Login failed — no user/session returned."}

    except Exception as exc:
        err_msg = str(exc)
        # Make common errors more readable
        if "Invalid login credentials" in err_msg:
            return False, {"error": "Invalid email or password."}
        if "Email not confirmed" in err_msg:
            return False, {"error": "Please confirm your email before logging in."}
        return False, {"error": f"Login error: {err_msg}"}


def sign_up(email: str, password: str) -> Tuple[bool, Dict[str, Any]]:
    """
    Create a new account via Supabase Auth.

    Returns:
        (True,  {"user_id": "...", "email": "...", "message": "..."})
        (False, {"error": "error message"})
    """
    client = get_supabase_client()
    if not client:
        return False, {"error": "Supabase is not configured. Check .env file."}

    try:
        resp = client.auth.sign_up({
            "email": email.strip(),
            "password": password,
        })

        user = resp.user
        if user:
            return True, {
                "user_id": user.id,
                "email": user.email,
                "message": "Account created! Check your email to confirm, then log in.",
            }
        return False, {"error": "Sign-up failed — no user returned."}

    except Exception as exc:
        err_msg = str(exc)
        if "already registered" in err_msg.lower():
            return False, {"error": "This email is already registered. Try logging in."}
        if "password" in err_msg.lower() and "short" in err_msg.lower():
            return False, {"error": "Password must be at least 6 characters."}
        return False, {"error": f"Sign-up error: {err_msg}"}


def sign_out() -> Tuple[bool, str]:
    """
    Sign out the current user.

    Returns:
        (True, "Logged out successfully.")
        (False, "Error message")
    """
    client = get_supabase_client()
    if not client:
        return True, "No Supabase client — session cleared locally."

    try:
        client.auth.sign_out()
        return True, "Logged out successfully."
    except Exception as exc:
        return False, f"Logout error: {exc}"


# ── Quick self-test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("[db.py] Running self-test...")
    client = get_supabase_client()
    if client:
        print(f"[db.py] Client ready: {type(client).__name__}")
        try:
            resp = client.table("logs").select("id").limit(1).execute()
            print(f"[db.py] Table 'logs' accessible — rows: {len(resp.data)}")
        except Exception as exc:
            print(f"[db.py] Table check failed: {exc}")
    else:
        print("[db.py] No Supabase client — local fallback active.")
