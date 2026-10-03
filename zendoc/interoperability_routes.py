"""Authenticated API surface for the ZENDOC interoperability control plane."""
from flask import Blueprint, jsonify, request

from .interoperability_gateway import build_exchange_plan, interoperability_manifest
from .routes import require_api_user


bp = Blueprint("interoperability", __name__)


@bp.get("/api/v1/interoperability")
def interoperability_capabilities():
    user, error = require_api_user()
    if error:
        return error
    return jsonify(interoperability_manifest())


@bp.post("/api/v1/interoperability/plan")
def interoperability_plan():
    user, error = require_api_user()
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    try:
        plan = build_exchange_plan(
            user,
            adapter_key=payload.get("adapter_key"),
            resource_type=payload.get("resource_type"),
            direction=payload.get("direction"),
            patient_id=payload.get("patient_id"),
        )
    except LookupError as error:
        return jsonify({"error": {"code": 404, "message": str(error)}}), 404
    except ValueError as error:
        return jsonify({"error": {"code": 400, "message": str(error)}}), 400
    return jsonify(plan)
