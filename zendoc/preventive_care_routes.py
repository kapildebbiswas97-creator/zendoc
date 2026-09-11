"""Authenticated preventive-care planning API."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from .preventive_care import create_preventive_plan, list_preventive_plans, update_preventive_plan_status
from .routes import require_api_user


bp = Blueprint("preventive_care", __name__)


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


@bp.route("/api/v1/preventive-care/plans", methods=("GET", "POST"))
def api_preventive_plans():
    user, error = require_api_user()
    if error:
        return error
    try:
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            patient_id = _optional_patient_id(data.get("patient_id"))
            plan = create_preventive_plan(user, data, patient_id=patient_id)
            return jsonify({"status": "created", "plan": plan}), 201
        patient_id = _optional_patient_id(request.args.get("patient_id"))
        plans = list_preventive_plans(
            user,
            patient_id=patient_id,
            status=request.args.get("status"),
            limit=request.args.get("limit", 100),
        )
        return jsonify({"plans": plans})
    except (PermissionError, LookupError, ValueError) as service_error:
        return _api_error(service_error)


@bp.post("/api/v1/preventive-care/plans/<int:plan_id>/<action>")
def api_preventive_plan_status(plan_id, action):
    user, error = require_api_user()
    if error:
        return error
    try:
        patient_id = _optional_patient_id(request.args.get("patient_id"))
        plan = update_preventive_plan_status(user, plan_id, action, patient_id=patient_id)
        return jsonify({"status": "updated", "plan": plan})
    except (PermissionError, LookupError, ValueError) as service_error:
        return _api_error(service_error)
