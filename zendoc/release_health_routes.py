"""Small production-facing compatibility and health routes.

These endpoints intentionally avoid application mutations. They provide a
stable registration entry point and a lightweight deployment health probe.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, redirect, url_for

from .database_reliability import readiness_report


bp = Blueprint("release_health", __name__)


@bp.get("/register")
def register_entry():
    """Send generic registration traffic to the patient signup flow."""
    return redirect(url_for("main.register", role="patient"), code=302)


@bp.get("/healthz")
def healthz():
    """Return a dependency-aware health response for deployment probes."""
    try:
        report = readiness_report()
    except Exception:
        return jsonify({"status": "not_ready"}), 503

    ready = str(report.get("status") or "").lower() == "ready"
    payload = {
        "status": "ready" if ready else "not_ready",
        "database": report.get("status"),
    }
    return jsonify(payload), 200 if ready else 503
