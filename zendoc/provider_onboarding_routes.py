"""Provider onboarding APIs for pilot operations."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from .provider_onboarding import (
    EVIDENCE_TYPES,
    get_provider_evidence,
    list_provider_evidence,
    provider_onboarding_status,
    review_provider_evidence,
    submit_provider_evidence,
)
from .provider_service import PROVIDER_ROLES, get_provider_profile_for_user
from .routes import require_api_user
from .security import is_owner


bp = Blueprint("provider_onboarding", __name__)


@bp.get("/api/v1/provider/onboarding")
def api_provider_onboarding():
    user, error = require_api_user()
    if error:
        return error
    if user["role"] not in PROVIDER_ROLES:
        return jsonify({"error": {"code": 403, "message": "Only provider accounts have an onboarding workflow."}}), 403
    profile = get_provider_profile_for_user(user["id"])
    if not profile:
        return jsonify({
            "status": "PROFILE_REQUIRED",
            "evidence_types": sorted(EVIDENCE_TYPES),
            "message": "Create your provider profile before submitting verification evidence.",
        })
    return jsonify({
        "status": "OK",
        "onboarding": provider_onboarding_status(profile["id"]),
        "evidence": list_provider_evidence(profile["id"]),
        "evidence_types": sorted(EVIDENCE_TYPES),
    })


@bp.post("/api/v1/provider/evidence")
def api_provider_evidence_submit():
    user, error = require_api_user()
    if error:
        return error
    if user["role"] not in PROVIDER_ROLES:
        return jsonify({"error": {"code": 403, "message": "Only provider accounts may submit verification evidence."}}), 403
    data = request.get_json(silent=True) or {}
    try:
        evidence = submit_provider_evidence(
            user,
            evidence_type=data.get("evidence_type"),
            identifier=data.get("identifier"),
            source_name=data.get("source_name"),
            source_url=data.get("source_url"),
            notes=data.get("notes"),
        )
    except LookupError as exc:
        return jsonify({"error": {"code": 404, "message": str(exc)}}), 404
    except ValueError as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
    return jsonify({"status": "submitted", "evidence": evidence}), 201


@bp.get("/api/v1/admin/provider-evidence")
def api_admin_provider_evidence():
    user, error = require_api_user()
    if error:
        return error
    if not is_owner(user):
        return jsonify({"error": {"code": 403, "message": "Only the ZENDOC owner may review provider evidence."}}), 403
    status = str(request.args.get("status") or "pending").strip().lower()
    if status not in {"pending", "verified", "rejected", "all"}:
        return jsonify({"error": {"code": 400, "message": "Invalid evidence status filter."}}), 400
    db = __import__("zendoc.db", fromlist=["get_db"]).get_db()
    if status == "all":
        rows = db.execute(
            """
            SELECT e.*,p.organization,p.provider_type,u.name provider_name,u.email provider_email
            FROM provider_verification_evidence e
            JOIN provider_profiles p ON p.id=e.provider_profile_id
            JOIN users u ON u.id=p.user_id
            ORDER BY e.created_at DESC LIMIT 100
            """
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT e.*,p.organization,p.provider_type,u.name provider_name,u.email provider_email
            FROM provider_verification_evidence e
            JOIN provider_profiles p ON p.id=e.provider_profile_id
            JOIN users u ON u.id=p.user_id
            WHERE e.status=?
            ORDER BY e.created_at DESC LIMIT 100
            """,
            (status,),
        ).fetchall()
    return jsonify({"status": status, "evidence": [dict(row) for row in rows]})


@bp.post("/api/v1/admin/provider-evidence/<int:evidence_id>/review")
def api_admin_provider_evidence_review(evidence_id):
    user, error = require_api_user()
    if error:
        return error
    if not is_owner(user):
        return jsonify({"error": {"code": 403, "message": "Only the ZENDOC owner may review provider evidence."}}), 403
    data = request.get_json(silent=True) or {}
    try:
        evidence = review_provider_evidence(
            user,
            evidence_id,
            status=data.get("status"),
            notes=data.get("notes"),
        )
    except LookupError as exc:
        return jsonify({"error": {"code": 404, "message": str(exc)}}), 404
    except ValueError as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
    return jsonify({"status": "reviewed", "evidence": evidence})
