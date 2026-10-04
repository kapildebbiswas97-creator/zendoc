"""
Network Sites & Automation Engine Routes.
Exposes public site fronts, provisioning API, and automation action approvals.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from .automation_engine import (
    approve_automation_action,
    create_automation_rule,
    get_automation_ledger,
    list_automation_rules,
    reject_automation_action,
)
from .network_sites import SiteProvisioningAgent, get_site_by_slug, list_network_sites
from .routes import require_api_user
from .security import is_owner


bp = Blueprint("network_sites", __name__)


@bp.get("/sites/<slug>")
def view_network_site(slug: str):
    site = get_site_by_slug(slug)
    if not site:
        return jsonify({"error": {"code": 404, "message": "Site not found"}}), 404
    # If client accepts JSON or API request
    if request.headers.get("Accept") == "application/json" or request.args.get("format") == "json":
        return jsonify({"site": site})
    return render_template("network_site.html", site=site)


@bp.get("/api/v1/network-sites")
def api_list_sites():
    entity_type = request.args.get("entity_type")
    city = request.args.get("city")
    verified_only = request.args.get("verified") in {"1", "true", "True"}
    limit = int(request.args.get("limit") or 50)
    sites = list_network_sites(entity_type=entity_type, city=city, verified_only=verified_only, limit=limit)
    return jsonify({"sites": sites, "count": len(sites)})


@bp.get("/api/v1/network-sites/<slug>")
def api_get_site(slug: str):
    site = get_site_by_slug(slug)
    if not site:
        return jsonify({"error": {"code": 404, "message": "Site not found"}}), 404
    return jsonify({"site": site})


@bp.post("/api/v1/network-sites/provision")
def api_provision_site():
    user, error = require_api_user()
    if error:
        return error
    if user["role"] not in {"admin", "doctor", "hospital", "pharmacy"}:
        return jsonify({"error": {"code": 403, "message": "Only providers or admins can provision sites."}}), 403

    data = request.get_json(silent=True) or {}
    entity_type = data.get("entity_type") or ("doctor" if user["role"] == "doctor" else "clinic")
    entity_id = data.get("entity_id")
    slug = data.get("slug")
    custom_data = {**data, **(data.get("custom_data") or {})}

    try:
        site = SiteProvisioningAgent.provision_site(
            actor=user,
            entity_type=entity_type,
            entity_id=entity_id,
            slug=slug,
            custom_data=custom_data,
        )
        return jsonify({"status": "provisioned", "site": site}), 201
    except ValueError as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400


# Automation Engine Endpoints
@bp.get("/api/v1/automation-rules")
def api_list_rules():
    user, error = require_api_user()
    if error:
        return error
    trigger = request.args.get("trigger_event")
    rules = list_automation_rules(trigger_event=trigger)
    return jsonify({"rules": rules})


@bp.post("/api/v1/automation-rules")
def api_create_rule():
    user, error = require_api_user()
    if error:
        return error
    if not is_owner(user):
        return jsonify({"error": {"code": 403, "message": "Admin authorization required."}}), 403
    data = request.get_json(silent=True) or {}
    try:
        rule = create_automation_rule(data)
        return jsonify({"status": "created", "rule": rule}), 201
    except ValueError as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400


@bp.get("/api/v1/automation-ledger")
def api_get_ledger():
    user, error = require_api_user()
    if error:
        return error
    state = request.args.get("state")
    ledger = get_automation_ledger(limit=50, state=state)
    return jsonify({"ledger": ledger})


@bp.post("/api/v1/automation-actions/<int:action_id>/approve")
def api_approve_action(action_id: int):
    user, error = require_api_user()
    if error:
        return error
    if not is_owner(user):
        return jsonify({"error": {"code": 403, "message": "Admin authorization required."}}), 403
    try:
        result = approve_automation_action(action_id, user)
        return jsonify({"status": "approved", "result": result})
    except (LookupError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400


@bp.post("/api/v1/automation-actions/<int:action_id>/reject")
def api_reject_action(action_id: int):
    user, error = require_api_user()
    if error:
        return error
    if not is_owner(user):
        return jsonify({"error": {"code": 403, "message": "Admin authorization required."}}), 403
    reason = (request.get_json(silent=True) or {}).get("reason", "Operator rejected")
    try:
        result = reject_automation_action(action_id, user, reason=reason)
        return jsonify({"status": "rejected", "result": result})
    except (LookupError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
