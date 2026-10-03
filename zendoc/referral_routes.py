"""Authenticated referral/waiting-list API and role-aware product UI."""
from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for

from .db import get_db, now_iso
from .record_storage import get_record_storage
from .referral_service import (
    create_referral,
    get_referral,
    get_referral_record,
    list_referrals,
    referral_creation_options,
    transition_referral,
)
from .routes import require_api_user
from .security import csrf_token, login_required


bp = Blueprint("referrals", __name__)


def _record_ids_from_form(value):
    if not str(value or "").strip():
        return []
    values = []
    for item in str(value).split(","):
        item = item.strip()
        if not item:
            continue
        try:
            record_id = int(item)
        except ValueError as exc:
            raise ValueError("Record IDs must be comma-separated integers.") from exc
        if record_id not in values:
            values.append(record_id)
    return values


def _web_actor():
    user = getattr(g, "user", None)
    if user is None:
        abort(401)
    if str(user["role"]) not in {"patient", "doctor", "hospital"}:
        abort(403)
    return user


@bp.get("/referrals")
@login_required
def referral_center():
    user = _web_actor()
    try:
        referrals = list_referrals(user, limit=100)
        creation = referral_creation_options(user) if str(user["role"]) in {"doctor", "hospital"} else None
    except (PermissionError, LookupError, TypeError, ValueError) as exc:
        flash(str(exc), "error")
        referrals = []
        creation = None
    return render_template(
        "referrals.html",
        current_user=user,
        referrals=referrals,
        creation=creation,
        csrf_token=csrf_token(),
    )


@bp.post("/referrals")
@login_required
def referral_create_web():
    user = _web_actor()
    raw_pair = str(request.form.get("patient_journey") or "")
    try:
        patient_text, journey_text = raw_pair.split(":", 1)
        referral = create_referral(
            user,
            patient_id=int(patient_text),
            destination_provider_id=int(request.form.get("destination_provider_id") or 0),
            journey_id=int(journey_text),
            reason=request.form.get("reason"),
            specialty=request.form.get("specialty"),
            priority=request.form.get("priority") or "routine",
            packet_summary=request.form.get("packet_summary"),
            record_ids=_record_ids_from_form(request.form.get("record_ids")),
            provenance={"source": "referral_center_web"},
        )
    except (PermissionError, LookupError, TypeError, ValueError) as exc:
        flash(str(exc), "error")
        return redirect(url_for("referrals.referral_center"))
    flash(f"Referral #{referral['id']} created. Prepare the packet, then the patient must consent before it can be sent.", "success")
    return redirect(url_for("referrals.referral_center"))


@bp.post("/referrals/<int:referral_id>/transition")
@login_required
def referral_transition_web(referral_id):
    user = _web_actor()
    try:
        referral = transition_referral(
            user,
            referral_id,
            request.form.get("target_status"),
            note=request.form.get("note"),
            scheduled_for=request.form.get("scheduled_for"),
            specialist_opinion=request.form.get("specialist_opinion"),
            outcome=request.form.get("outcome"),
            provenance={"source": "referral_center_web"},
        )
    except (PermissionError, LookupError, TypeError, ValueError) as exc:
        flash(str(exc), "error")
        return redirect(url_for("referrals.referral_center"))
    flash(f"Referral #{referral['id']} updated to {referral['status'].replace('_', ' ').title()}.", "success")
    return redirect(url_for("referrals.referral_center"))


@bp.get("/referrals/<int:referral_id>/records/<int:record_id>/download")
@login_required
def referral_record_download(referral_id, record_id):
    user = _web_actor()
    try:
        record = get_referral_record(user, referral_id, record_id)
    except LookupError:
        abort(404)
    except PermissionError:
        abort(403)
    get_db().execute(
        """
        INSERT INTO audit_logs (actor_id,action,entity_type,entity_id,created_at)
        VALUES (?, 'referral.record.download', 'medical_record', ?, ?)
        """,
        (int(user["id"]), str(record_id), now_iso()),
    )
    get_db().commit()
    return get_record_storage().response(record["stored_filename"], record["original_filename"])



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
