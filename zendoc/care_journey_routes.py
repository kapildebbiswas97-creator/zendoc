"""Authenticated durable Care Journey APIs."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from .care_journey_store import (
    advance_persisted_journey,
    create_persisted_journey,
    get_persisted_journey,
    list_patient_journeys,
)
from .routes import require_api_user


bp = Blueprint("care_journey", __name__)


@bp.post("/api/v1/care-journeys")
def api_create_care_journey():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        journey = create_persisted_journey(
            user,
            patient_id=data.get("patient_id"),
            provenance=data.get("provenance") if isinstance(data.get("provenance"), dict) else {},
        )
    except PermissionError as exc:
        return jsonify({"error": {"code": 403, "message": str(exc)}}), 403
    except LookupError as exc:
        return jsonify({"error": {"code": 404, "message": str(exc)}}), 404
    except (TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
    return jsonify({"status": "created", "journey": journey}), 201


@bp.get("/api/v1/care-journeys")
def api_list_care_journeys():
    user, error = require_api_user()
    if error:
        return error
    try:
        journeys = list_patient_journeys(
            user,
            patient_id=request.args.get("patient_id"),
            limit=request.args.get("limit", 25),
        )
    except PermissionError as exc:
        return jsonify({"error": {"code": 403, "message": str(exc)}}), 403
    except LookupError as exc:
        return jsonify({"error": {"code": 404, "message": str(exc)}}), 404
    except (TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
    return jsonify({"journeys": journeys})


@bp.get("/api/v1/care-journeys/<int:journey_id>")
def api_get_care_journey(journey_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        journey = get_persisted_journey(journey_id, user)
    except LookupError:
        return jsonify({"error": {"code": 404, "message": "Care journey not found."}}), 404
    except PermissionError as exc:
        return jsonify({"error": {"code": 403, "message": str(exc)}}), 403
    return jsonify({"journey": journey})


@bp.post("/api/v1/care-journeys/<int:journey_id>/transition")
def api_transition_care_journey(journey_id):
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        journey = advance_persisted_journey(
            user,
            journey_id,
            target_state=data.get("target_state"),
            reason=data.get("reason"),
            actor_type="user",
            next_safe_action=data.get("next_safe_action"),
            required_actor=data.get("required_actor"),
            required_consent=data.get("required_consent"),
            blocked_reason=data.get("blocked_reason"),
            provenance=data.get("provenance") if isinstance(data.get("provenance"), dict) else {},
        )
    except LookupError:
        return jsonify({"error": {"code": 404, "message": "Care journey not found."}}), 404
    except PermissionError as exc:
        return jsonify({"error": {"code": 403, "message": str(exc)}}), 403
    except (TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
    return jsonify({"status": "updated", "journey": journey})
