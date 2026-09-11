"""Authenticated read-only personal-baseline API."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from .db import get_db
from .health_analytics import get_personal_health_baseline
from .routes import audit, require_api_user


bp = Blueprint("personal_health_baseline", __name__)


def _optional_patient_id(value):
    if value in (None, ""):
        return None
    try:
        patient_id = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("patient_id must be an integer.") from error
    if patient_id < 1:
        raise ValueError("patient_id must be a positive integer.")
    return patient_id


def _api_error(error):
    if isinstance(error, PermissionError):
        status = 403
    elif isinstance(error, LookupError):
        status = 404
    else:
        status = 400
    return jsonify({"error": {"code": status, "message": str(error)}}), status


@bp.get("/api/v1/health-baseline")
def api_personal_health_baseline():
    user, error = require_api_user()
    if error:
        return error
    metric_type = str(request.args.get("metric_type") or "").strip()
    if not metric_type:
        return jsonify({"error": {"code": 400, "message": "metric_type is required"}}), 400
    try:
        patient_id = _optional_patient_id(request.args.get("patient_id"))
        result = get_personal_health_baseline(
            user,
            metric_type,
            patient_id=patient_id,
            baseline_days=request.args.get("baseline_days", 90),
            recent_days=request.args.get("recent_days", 7),
        )
        audit("view", "personal_health_baseline", str(result["patient_id"]), actor=user)
        get_db().commit()
        return jsonify(result)
    except (PermissionError, LookupError, ValueError) as service_error:
        return _api_error(service_error)
