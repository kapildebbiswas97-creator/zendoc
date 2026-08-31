import secrets
import hashlib
from functools import wraps
from datetime import datetime, timezone

from flask import abort, current_app, flash, g, redirect, request, session, url_for

from .db import get_db


SESSION_EXPIRED_MESSAGE = "Your session expired. Please log in again."


def new_token():
    return secrets.token_urlsafe(40)


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return get_db().execute("SELECT * FROM users WHERE id = ? AND active = 1", (user_id,)).fetchone()


def start_user_session(user, remember=False):
    """Rotate all client session state after successful authentication."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    session.clear()
    session["user_id"] = int(user["id"])
    session["role"] = str(user["role"])
    session["session_nonce"] = secrets.token_urlsafe(24)
    session["authenticated_at"] = now
    session["last_activity_at"] = now
    session["csrf_token"] = secrets.token_urlsafe(32)
    session.permanent = bool(remember)


def _session_is_idle_expired():
    if not session.get("user_id"):
        return False
    value = session.get("last_activity_at")
    if not value:
        return False
    try:
        last_activity = datetime.fromisoformat(str(value))
        if last_activity.tzinfo is None:
            last_activity = last_activity.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return True
    idle_minutes = max(5, int(current_app.config.get("SESSION_IDLE_MINUTES", 120)))
    return (datetime.now(timezone.utc) - last_activity).total_seconds() > idle_minutes * 60


def _safe_login_role(value, default="patient"):
    role = str(value or default).strip().lower()
    return role if role in {"patient", "doctor", "hospital", "pharmacy", "government", "admin"} else default


def _value(user, key, default=None):
    if user is None:
        return default
    if hasattr(user, "keys") and key in user.keys():
        return user[key]
    return user.get(key, default) if isinstance(user, dict) else default


def is_owner(user):
    """Return True only for the environment-configured ZENDOC owner account."""
    if _value(user, "role") != "admin" or not bool(_value(user, "active", 1)):
        return False
    configured_email = str(current_app.config.get("ADMIN_EMAIL") or "").strip().lower()
    account_email = str(_value(user, "email_normalized") or _value(user, "email") or "").strip().lower()
    return bool(configured_email and account_email == configured_email)


def assert_owner(user):
    if not is_owner(user):
        raise PermissionError("Only the ZENDOC owner may access Admin operations.")
    return user


def load_user_and_check_csrf():
    g.session_expired = False
    g.login_role = "patient"
    if _session_is_idle_expired():
        g.login_role = _safe_login_role(session.get("role"))
        session.clear()
        g.session_expired = True
        flash(SESSION_EXPIRED_MESSAGE, "warning")
        g.user = None
        if request.method == "POST" and not request.path.startswith("/api/"):
            return redirect(url_for("main.login", role=g.login_role))
        return None

    g.user = current_user()
    if session.get("user_id") and g.user is None:
        g.login_role = _safe_login_role(session.get("role"))
        session.clear()
        g.session_expired = True
        flash(SESSION_EXPIRED_MESSAGE, "warning")
    elif g.user is not None:
        session["last_activity_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if request.method == "POST" and not request.path.startswith("/api/"):
        token = request.form.get("csrf_token")
        if not token or token != session.get("csrf_token"):
            abort(400, "Invalid form token")
    return None


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            if not g.get("session_expired", False):
                flash("Please log in to continue.", "warning")
            return redirect(url_for("main.login", role=g.get("login_role", "patient")))
        return view(*args, **kwargs)

    return wrapped


def owner_required(view):
    """Protect an owner-only web route using server-configured identity, not client role claims."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("main.login", role="admin" if not g.get("session_expired") else g.get("login_role", "admin")))
        if not is_owner(g.user):
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.user is None:
                return redirect(url_for("main.login", role=g.get("login_role", "patient")))
            if g.user["role"] == "admin" and not is_owner(g.user):
                abort(403)
            if g.user["role"] not in roles and g.user["role"] != "admin":
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator
