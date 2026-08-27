import secrets
import hashlib
from functools import wraps

from flask import abort, flash, g, redirect, request, session, url_for

from .db import get_db


def new_token():
    return secrets.token_urlsafe(40)


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return get_db().execute("SELECT * FROM users WHERE id = ? AND active = 1", (user_id,)).fetchone()


def load_user_and_check_csrf():
    g.user = current_user()
    if request.method == "POST" and not request.path.startswith("/api/"):
        token = request.form.get("csrf_token")
        if not token or token != session.get("csrf_token"):
            abort(400, "Invalid form token")


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("main.login", role="patient"))
        return view(*args, **kwargs)

    return wrapped


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.user is None:
                return redirect(url_for("main.login", role="patient"))
            if g.user["role"] not in roles and g.user["role"] != "admin":
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator
