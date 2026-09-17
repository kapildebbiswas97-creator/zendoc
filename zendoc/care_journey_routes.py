"""Authenticated durable Care Journey APIs."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from .appointment_continuity import complete_follow_up
from .care_action_ledger import create_action, get_action, list_actions, record_outcome, transition_action
from .care_continuity import build_care_continuity_snapshot
from .care_journey_store import (
    advance_persisted_journey,
    create_persisted_journey,
    get_persisted_journey,
    list_patient_journeys,
)
from .context_engine import verify_context_authorization
from .db import get_db
from .routes import require_api_user


bp = Blueprint("care_journey", __name__)

_PROVIDER_SYNCHRONIZED_APPOINTMENT_STATES = {"CONFIRMED", "IN_PROGRESS", "COMPLETED"}

# These states require real appointment/provider/outcome/follow-up evidence.
# A generic user transition endpoint must never manufacture them.
_EVIDENCE_BOUND_JOURNEY_TARGETS = {
    "WAITING_PROVIDER",
    "WAITING_VISIT",
    "CONSULTATION",
    "FOLLOW_UP",
    "COMPLETED",
}


def _error(exc):
    if isinstance(exc, PermissionError):
        code = 403
    elif isinstance(exc, LookupError):
        code = 404
    else:
        code = 400
    return jsonify({"error": {"code": code, "message": str(exc)}}), code


def _enforce_careloop_context_scope(user, *, journey_id=None, action_id=None):
    """Require minimum-necessary consent before delegated CareLoop access.

    Patient self-access and owner override remain handled by the context engine.
    Any delegated actor must have authorization for the care_graph purpose, which
    requires timeline scope and honors revocation/expiry in the consent engine.
    """
    if journey_id is not None:
        row = get_db().execute(
            "SELECT patient_id FROM care_journeys WHERE id=?",
            (int(journey_id),),
        ).fetchone()
        if not row:
            raise LookupError("Care journey not found.")
    elif action_id is not None:
        row = get_db().execute(
            "SELECT patient_id FROM care_actions WHERE id=?",
            (int(action_id),),
        ).fetchone()
        if not row:
            raise LookupError("Care action not found.")
    else:
        raise ValueError("A care journey or care action is required.")
    verify_context_authorization(user, int(row["patient_id"]), "care_graph")


def _enforce_linked_action_state_authority(user, action_id, target_status):
    """Keep provider-synchronized appointment state separate from ledger reports.

    A CareLoop action linked to a real registered-provider appointment may expose
    provider confirmation/completion only when that state arrives through the
    appointment lifecycle synchronizer. The generic ledger transition endpoint
    must never be able to manufacture the same provider-backed state.
    """
    target = str(target_status or "").strip().upper()
    if target not in _PROVIDER_SYNCHRONIZED_APPOINTMENT_STATES:
        return
    action = get_action(user, action_id)
    if action.get("integration_source_type") == "appointment":
        raise PermissionError(
            "Linked registered-provider appointment confirmation and completion must be "
            "synchronized from the appointment lifecycle; this ledger endpoint cannot assert provider state."
        )


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
        journeys = list_patient_journeys(
            user,
            patient_id=request.args.get("patient_id"),
            limit=request.args.get("limit", 25),
        )
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


@bp.get("/api/v1/care-journeys/<int:journey_id>/continuity")
def api_get_care_journey_continuity(journey_id):
    """Return one permission-checked, evidence-backed longitudinal care snapshot."""
    user, error = require_api_user()
    if error:
        return error
    try:
        snapshot = build_care_continuity_snapshot(user, journey_id)
    except (LookupError, PermissionError, TypeError, ValueError) as exc:
        return _error(exc)
    return jsonify({"continuity": snapshot})


@bp.post("/api/v1/care-journeys/<int:journey_id>/transition")
def api_transition_care_journey(journey_id):
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    target_state = str(data.get("target_state") or "").strip().upper()
    try:
        if target_state in _EVIDENCE_BOUND_JOURNEY_TARGETS:
            raise PermissionError(
                "This Care Journey state is evidence-bound and must be advanced by its dedicated booking/provider/outcome/follow-up workflow."
            )
        journey = advance_persisted_journey(
            user,
            journey_id,
            target_state=target_state,
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


@bp.post("/api/v1/care-journeys/<int:journey_id>/follow-up/complete")
def api_complete_care_journey_follow_up(journey_id):
    """Patient-only, evidence-bound completion of post-visit follow-up."""
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        result = complete_follow_up(
            user,
            journey_id,
            user_confirmed=data.get("user_confirmed") is True,
        )
    except (LookupError, PermissionError, TypeError, ValueError) as exc:
        return _error(exc)
    return jsonify({"status": "completed", "follow_up": result})


@bp.post("/api/v1/care-journeys/<int:journey_id>/actions")
def api_create_care_action(journey_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        _enforce_careloop_context_scope(user, journey_id=journey_id)
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
        _enforce_careloop_context_scope(user, journey_id=journey_id)
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
        _enforce_careloop_context_scope(user, action_id=action_id)
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
        _enforce_careloop_context_scope(user, action_id=action_id)
        _enforce_linked_action_state_authority(user, action_id, data.get("target_status"))
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
        _enforce_careloop_context_scope(user, action_id=action_id)
        outcome = record_outcome(user, action_id, request.get_json(silent=True) or {})
    except (PermissionError, LookupError, TypeError, ValueError) as exc:
        return _error(exc)
    return jsonify({"status": "created", "outcome": outcome}), 201
