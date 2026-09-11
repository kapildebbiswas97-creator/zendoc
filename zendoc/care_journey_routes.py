"""Authenticated durable Care Journey APIs."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from .care_action_ledger import create_action, get_action, list_actions, record_outcome, transition_action
from .care_journey_store import (
    advance_persisted_journey,
    create_persisted_journey,
    get_persisted_journey,
    list_patient_journeys,
)
from .routes import require_api_user


bp = Blueprint("care_journey", __name__)


def _error(exc):
    if isinstance(exc, PermissionError):
        code = 403
    elif isinstance(exc, LookupError):
        code = 404
    else:
        code = 400
    return jsonify({"error": {"code": code, "message": str(exc)}}), code


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
    except (PermissionError, LookupError, TypeError, ValueError) as exc:
        return _error(exc)
    return jsonify({"status": "created", "journey": journey}), 201


@bp.get("/api/v1/care-journeys")
def api_list_care_journeys():
    user, error = require_api_user()
    if error:
        return error
    try:
        journeys = list_patient_journeys(user, patient_id=request.args.get("patient_id"), limit=request.args.get("limit", 25))
    except (PermissionError, LookupError, TypeError, ValueError) as exc:
        return _error(exc)
    return jsonify({"journeys": journeys})


@bp.get("/api/v1/care-journeys/<int:journey_id>")
def api_get_care_journey(journey_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        journey = get_persisted_journey(journey_id, user)
    except (LookupError, PermissionError) as exc:
        return _error(exc)
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
    except (LookupError, PermissionError, TypeError, ValueError) as exc:
        return _error(exc)
    return jsonify({"status": "updated", "journey": journey})


@bp.post("/api/v1/care-journeys/<int:journey_id>/actions")
def api_create_care_action(journey_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        action = create_action(user, journey_id, request.get_json(silent=True) or {})
    except (PermissionError, LookupError, TypeError, ValueError) as exc:
        return _error(exc)
    return jsonify({"status": "created", "action": action}), 201


@bp.get("/api/v1/care-journeys/<int:journey_id>/actions")
def api_list_care_actions(journey_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        actions = list_actions(user, journey_id)
    except (PermissionError, LookupError, TypeError, ValueError) as exc:
        return _error(exc)
    return jsonify({"actions": actions})


@bp.get("/api/v1/care-actions/<int:action_id>")
def api_get_care_action(action_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        action = get_action(user, action_id)
    except (PermissionError, LookupError, TypeError, ValueError) as exc:
        return _error(exc)
    return jsonify({"action": action})


@bp.post("/api/v1/care-actions/<int:action_id>/transition")
def api_transition_care_action(action_id):
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        action = transition_action(
            user,
            action_id,
            data.get("target_status"),
            note=data.get("note"),
            provenance=data.get("provenance") if isinstance(data.get("provenance"), dict) else {},
        )
    except (PermissionError, LookupError, TypeError, ValueError) as exc:
        return _error(exc)
    return jsonify({"status": "updated", "action": action})


@bp.post("/api/v1/care-actions/<int:action_id>/outcomes")
def api_record_care_outcome(action_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        outcome = record_outcome(user, action_id, request.get_json(silent=True) or {})
    except (PermissionError, LookupError, TypeError, ValueError) as exc:
        return _error(exc)
    return jsonify({"status": "created", "outcome": outcome}), 201
