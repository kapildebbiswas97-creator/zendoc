"""Owner-only API for evidence-gated AI workforce incident cases."""
from flask import Blueprint, jsonify, request

from .incident_runtime import (
    advance_incident_case,
    incident_runtime_snapshot,
    list_incident_runtimes,
    record_owner_production_approval,
)
from .routes import require_api_user
from .security import is_owner


bp = Blueprint("workforce_incidents", __name__)


def _owner_api_user():
    user, error = require_api_user()
    if error:
        return None, error
    if not is_owner(user):
        return None, (jsonify({"error": {"code": 403, "message": "Configured owner access is required."}}), 403)
    return user, None


def _error(exc):
    if isinstance(exc, PermissionError):
        code = 403
    elif isinstance(exc, LookupError):
        code = 404
    else:
        code = 400
    return jsonify({"error": {"code": code, "message": str(exc)}}), code


@bp.get("/api/v1/admin/workforce/incidents")
def api_list_incidents():
    user, error = _owner_api_user()
    if error:
        return error
    try:
        return jsonify({"incidents": list_incident_runtimes(user, limit=request.args.get("limit", 50))})
    except (PermissionError, LookupError, TypeError, ValueError) as exc:
        return _error(exc)


@bp.get("/api/v1/admin/workforce/incidents/<int:task_id>")
def api_incident_status(task_id):
    user, error = _owner_api_user()
    if error:
        return error
    try:
        return jsonify(incident_runtime_snapshot(user, task_id))
    except (PermissionError, LookupError, TypeError, ValueError) as exc:
        return _error(exc)


@bp.post("/api/v1/admin/workforce/incidents/<int:task_id>/advance")
def api_advance_incident(task_id):
    user, error = _owner_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    evidence = data.get("evidence") if isinstance(data.get("evidence"), dict) else {}
    try:
        return jsonify(advance_incident_case(user, task_id, evidence=evidence))
    except (PermissionError, LookupError, TypeError, ValueError) as exc:
        return _error(exc)


@bp.post("/api/v1/admin/workforce/incidents/<int:task_id>/production-approval")
def api_owner_production_approval(task_id):
    user, error = _owner_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    if data.get("approved") is not True:
        return jsonify({"error": {"code": 400, "message": "approved must be true for an explicit owner approval record."}}), 400
    try:
        return jsonify(
            record_owner_production_approval(
                user,
                task_id,
                approval_reference=data.get("approval_reference"),
            )
        )
    except (PermissionError, LookupError, TypeError, ValueError) as exc:
        return _error(exc)
