from flask import Blueprint, jsonify, redirect, url_for
from .database_reliability import readiness_report

bp = Blueprint("release_probe", __name__)

@bp.get("/register")
def register_entry():
    return redirect(url_for("main.register", role="patient"), code=302)

@bp.get("/healthz")
def healthz():
    try:
        report = readiness_report()
    except Exception:
        return jsonify({"status": "not_ready"}), 503
    ready = str(report.get("status") or "").lower() == "ready"
    return jsonify({"status": "ready" if ready else "not_ready"}), 200 if ready else 503
