"""Private, operator-attested hospital ward/bed API.

Not a public admission system, a source of verified live-bed availability,
or permission for autonomous clinical decisions.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from .hospital_bed_board import (
    bed_state_history,
    change_hospital_bed_state,
    create_hospital_bed,
    list_hospital_beds,
)
from .routes import require_api_user


bp = Blueprint("hospital_bed_board", __name__)


def _error(exc: Exception):
    if isinstance(exc, PermissionError):
        code = 403
    elif isinstance(exc, LookupError):
        code = 404
    elif isinstance(exc, RuntimeError):
        code = 409
    else:
        code = 400
    return jsonify({"error": {"code": code, "message": str(exc)}}), code


@bp.get("/api/v1/hospital/beds")
def api_list_beds():
    user, error = require_api_user()
    if error:
        return error
    try:
        return jsonify(list_hospital_beds(user, limit=request.args.get("limit", 200)))
    except (ValueError, PermissionError) as exc:
        return _error(exc)


@bp.post("/api/v1/hospital/beds")
def api_create_bed():
    user, error = require_api_user()
    if error:
        return error
    try:
        result = create_hospital_bed(user, request.get_json(silent=True) or {})
    except (ValueError, PermissionError) as exc:
        return _error(exc)
    return jsonify({"status": "created", "bed": result}), 201


@bp.post("/api/v1/hospital/beds/<int:bed_id>/state")
def api_change_bed_state(bed_id: int):
    user, error = require_api_user()
    if error:
        return error
    try:
        result = change_hospital_bed_state(user, bed_id, request.get_json(silent=True) or {})
    except (ValueError, PermissionError, LookupError, RuntimeError) as exc:
        return _error(exc)
    return jsonify({"status": "updated", "bed": result})


@bp.get("/api/v1/hospital/beds/<int:bed_id>/history")
def api_bed_history(bed_id: int):
    user, error = require_api_user()
    if error:
        return error
    try:
        history = bed_state_history(user, bed_id)
    except (PermissionError, LookupError) as exc:
        return _error(exc)
    return jsonify({"status": "OPERATOR_ATTESTED_ONLY", "history": history})
