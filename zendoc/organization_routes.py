from __future__ import annotations

from flask import Blueprint, jsonify, request

from .organization_service import (
    active_membership,
    approve_membership,
    bind_provider_profile,
    create_location,
    create_organization,
    request_membership,
    verify_organization,
)
from .routes import require_api_user
from .security import is_owner

bp = Blueprint("provider_organizations", __name__)


def _error(exc):
    if isinstance(exc, PermissionError):
        code = 403
    elif isinstance(exc, LookupError):
        code = 404
    else:
        code = 400
    return jsonify({"error": {"code": code, "message": str(exc)}}), code


@bp.post("/api/v1/provider-organizations")
def api_create_organization():
    user, error = require_api_user()
    if error:
        return error
    try:
        return jsonify({"organization": create_organization(user, request.get_json(silent=True) or {})}), 201
    except (PermissionError, LookupError, ValueError) as exc:
        return _error(exc)


@bp.post("/api/v1/provider-organizations/<int:organization_id>/memberships")
def api_request_membership(organization_id):
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        membership = request_membership(user, organization_id, data.get("membership_role", "member"))
        return jsonify({"membership": membership}), 201
    except (PermissionError, LookupError, ValueError) as exc:
        return _error(exc)


@bp.post("/api/v1/provider-organizations/memberships/<int:membership_id>/review")
def api_review_membership(membership_id):
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        membership = approve_membership(user, membership_id, data.get("status", "active"))
        return jsonify({"membership": membership})
    except (PermissionError, LookupError, ValueError) as exc:
        return _error(exc)


@bp.post("/api/v1/provider-organizations/<int:organization_id>/bind-profile")
def api_bind_provider_profile(organization_id):
    user, error = require_api_user()
    if error:
        return error
    if user["role"] not in {"doctor", "hospital", "pharmacy"}:
        return jsonify({"error": {"code": 403, "message": "Only provider accounts may bind provider profiles."}}), 403
    data = request.get_json(silent=True) or {}
    try:
        profile = bind_provider_profile(user, organization_id, data.get("location_id"))
        return jsonify({"provider_profile": profile})
    except (PermissionError, LookupError, ValueError) as exc:
        return _error(exc)


@bp.get("/api/v1/provider-organizations/membership")
def api_current_membership():
    user, error = require_api_user()
    if error:
        return error
    membership = active_membership(user["id"])
    return jsonify({"membership": membership})


@bp.get("/api/v1/admin/provider-organizations")
def api_admin_organizations():
    user, error = require_api_user()
    if error:
        return error
    if not is_owner(user):
        return jsonify({"error": {"code": 403, "message": "Only the ZENDOC owner may inspect all provider organizations."}}), 403
    from .db import get_db
    rows = get_db().execute(
        "SELECT * FROM provider_organizations ORDER BY created_at DESC LIMIT 100"
    ).fetchall()
    return jsonify({"organizations": [dict(row) for row in rows]})


@bp.post("/api/v1/admin/provider-organizations/<int:organization_id>/verify")
def api_verify_organization(organization_id):
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        organization = verify_organization(user, organization_id, data.get("status", "verified"))
        return jsonify({"organization": organization})
    except (PermissionError, LookupError, ValueError) as exc:
        return _error(exc)


@bp.post("/api/v1/provider-organizations/<int:organization_id>/locations")
def api_create_organization_location(organization_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        location = create_location(user, organization_id, request.get_json(silent=True) or {})
        return jsonify({"location": location}), 201
    except (PermissionError, LookupError, ValueError) as exc:
        return _error(exc)
