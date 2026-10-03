"""Authenticated referral/waiting-list APIs."""
from flask import Blueprint, jsonify, request

from .referral_service import create_referral, get_referral, list_referrals, transition_referral
from .routes import require_api_user


bp = Blueprint("referrals", __name__)


def _error(exc):
    if isinstance(exc, PermissionError):
        code = 403
    elif isinstance(exc, LookupError):
        code = 404
    else:
        code = 400
    return jsonify({"error": {"code": code, "message": str(exc)}}), code


@bp.post("/api/v1/referrals")
def api_create_referral():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        referral = create_referral(
            user,
            patient_id=int(data.get("patient_id")),
            destination_provider_id=int(data.get("destination_provider_id")),
            journey_id=int(data.get("journey_id")),
            reason=data.get("reason"),
            specialty=data.get("specialty"),
            priority=data.get("priority") or "routine",
            packet_summary=data.get("packet_summary"),
            record_ids=data.get("record_ids") or [],
            provenance=data.get("provenance") if isinstance(data.get("provenance"), dict) else {},
        )
        return jsonify({"status": "created", "referral": referral}), 201
    except (PermissionError, LookupError, TypeError, ValueError) as exc:
        return _error(exc)


@bp.get("/api/v1/referrals")
def api_list_referrals():
    user, error = require_api_user()
    if error:
        return error
    try:
        referrals = list_referrals(
            user,
            patient_id=request.args.get("patient_id"),
            limit=request.args.get("limit", 50),
        )
        return jsonify({"referrals": referrals})
    except (PermissionError, LookupError, TypeError, ValueError) as exc:
        return _error(exc)


@bp.get("/api/v1/referrals/<int:referral_id>")
def api_get_referral(referral_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        return jsonify({"referral": get_referral(user, referral_id)})
    except (PermissionError, LookupError, TypeError, ValueError) as exc:
        return _error(exc)


@bp.post("/api/v1/referrals/<int:referral_id>/transition")
def api_transition_referral(referral_id):
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        referral = transition_referral(
            user,
            referral_id,
            data.get("target_status"),
            note=data.get("note"),
            scheduled_for=data.get("scheduled_for"),
            specialist_opinion=data.get("specialist_opinion"),
            outcome=data.get("outcome"),
            provenance=data.get("provenance") if isinstance(data.get("provenance"), dict) else {},
        )
        return jsonify({"status": "updated", "referral": referral})
    except (PermissionError, LookupError, TypeError, ValueError) as exc:
        return _error(exc)
