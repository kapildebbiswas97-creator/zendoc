"""Small, explicit compatibility routes for common public entry points.

These aliases intentionally cover only well-known URLs. They do not mask real
404s or create a catch-all route.
"""
from flask import Blueprint, jsonify, redirect, url_for


bp = Blueprint("compat", __name__)


@bp.get("/register")
def register_default():
    """Send generic sign-up traffic to the default patient registration flow."""
    return redirect(url_for("main.register", role="patient"), code=302)


@bp.get("/healthz")
def healthz():
    """Conventional lightweight liveness alias for hosts and external probes."""
    return jsonify({"status": "ok", "service": "zendoc", "check": "liveness"}), 200
