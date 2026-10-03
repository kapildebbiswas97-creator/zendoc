"""Authenticated API surface for the ZENDOC interoperability control plane."""
from flask import Blueprint, g, jsonify, request

from .interoperability_gateway import build_exchange_plan, interoperability_manifest
from .security import login_required


bp = Blueprint("interoperability", __name__)


@bp.get("/api/v1/interoperability")
@login_required
def interoperability_capabilities():
    return jsonify(interoperability_manifest())


@bp.post("/api/v1/interoperability/plan")
@login_required
def interoperability_plan():
    payload = request.get_json(silent=True) or {}
    try:
        plan = build_exchange_plan(
            g.user,
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
