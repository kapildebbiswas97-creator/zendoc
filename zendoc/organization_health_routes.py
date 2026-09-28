"""Web and API surfaces for organization health programs."""
from __future__ import annotations

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for

from .organization_health_service import (
    BENEFIT_TYPES,
    create_benefit_plan,
    list_benefit_plans,
    list_my_health_organizations,
    list_organization_memberships,
    organization_health_snapshot,
    request_health_organization_membership,
    review_organization_membership,
    set_benefit_plan_active,
)
from .organization_service import ORG_TYPES, create_organization, verify_organization
from .routes import login_required, require_api_user
from .security import is_owner


bp = Blueprint("organization_health", __name__)


def _api_error(exc):
    if isinstance(exc, PermissionError):
        code = 403
    elif isinstance(exc, LookupError):
        code = 404
    else:
        code = 400
    return jsonify({"error": {"code": code, "message": str(exc)}}), code


@bp.route("/organizations", methods=("GET", "POST"))
@login_required
def organizations_home():
    if request.method == "POST":
        if not is_owner(g.user):
            abort(403)
        try:
            organization = create_organization(
                g.user,
                {
                    "name": request.form.get("name"),
                    "organization_type": request.form.get("organization_type"),
                    "address": request.form.get("address"),
                    "city": request.form.get("city"),
                    "state": request.form.get("state"),
                    "postal_code": request.form.get("postal_code"),
                },
            )
            flash(
                f"Organization created. Verify {organization['name']} before member enrollment.",
                "success",
            )
            return redirect(url_for("organization_health.organization_page", organization_id=organization["id"]))
        except (PermissionError, LookupError, ValueError) as exc:
            flash(str(exc), "error")

    organizations = list_my_health_organizations(g.user)
    return render_template(
        "organizations.html",
        organizations=organizations,
        organization_types=sorted(ORG_TYPES),
        owner_mode=is_owner(g.user),
    )


@bp.post("/organizations/join")
@login_required
def join_organization():
    try:
        membership = request_health_organization_membership(
            g.user,
            request.form.get("organization_uid"),
        )
        flash(
            "Membership request submitted. An organization owner/admin must approve it before organization benefits become available.",
            "success",
        )
        return redirect(url_for("organization_health.organizations_home"))
    except (PermissionError, LookupError, ValueError) as exc:
        flash(str(exc), "error")
        return redirect(url_for("organization_health.organizations_home"))


@bp.get("/organizations/<int:organization_id>")
@login_required
def organization_page(organization_id):
    snapshot = None
    memberships = []
    try:
        snapshot = organization_health_snapshot(g.user, organization_id, days=request.args.get("days", 30))
        memberships = list_organization_memberships(g.user, organization_id)
    except LookupError:
        abort(404)
    except PermissionError:
        pass
    try:
        plans = list_benefit_plans(
            g.user,
            organization_id,
            include_inactive=bool(snapshot),
        )
    except LookupError:
        abort(404)
    except PermissionError:
        if is_owner(g.user):
            plans = []
        else:
            abort(403)
    return render_template(
        "organization_health.html",
        organization_id=organization_id,
        plans=plans,
        snapshot=snapshot,
        memberships=memberships,
        benefit_types=sorted(BENEFIT_TYPES),
        owner_mode=is_owner(g.user),
    )


@bp.post("/organizations/<int:organization_id>/verify")
@login_required
def verify_health_organization(organization_id):
    if not is_owner(g.user):
        abort(403)
    try:
        verify_organization(
            g.user,
            organization_id,
            request.form.get("status", "verified"),
        )
        flash("Organization verification state updated.", "success")
    except (PermissionError, LookupError, ValueError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("organization_health.organization_page", organization_id=organization_id))


@bp.post("/organizations/<int:organization_id>/benefits")
@login_required
def create_organization_benefit(organization_id):
    try:
        create_benefit_plan(g.user, organization_id, request.form)
        flash("Organization benefit plan added.", "success")
    except (PermissionError, LookupError, ValueError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("organization_health.organization_page", organization_id=organization_id))


@bp.post("/organizations/<int:organization_id>/benefits/<int:benefit_id>/state")
@login_required
def update_organization_benefit_state(organization_id, benefit_id):
    try:
        set_benefit_plan_active(
            g.user,
            organization_id,
            benefit_id,
            str(request.form.get("active") or "").lower() in {"1", "true", "yes", "on"},
        )
        flash("Benefit plan state updated.", "success")
    except (PermissionError, LookupError, ValueError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("organization_health.organization_page", organization_id=organization_id))


@bp.post("/organizations/<int:organization_id>/memberships/<int:membership_id>/review")
@login_required
def review_membership(organization_id, membership_id):
    try:
        review_organization_membership(
            g.user,
            organization_id,
            membership_id,
            request.form.get("status", "active"),
        )
        flash("Membership state updated.", "success")
    except (PermissionError, LookupError, ValueError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("organization_health.organization_page", organization_id=organization_id))


@bp.get("/api/v1/organizations/<int:organization_id>/health-command-center")
def api_organization_health_command_center(organization_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        return jsonify({
            "status": "OK",
            "snapshot": organization_health_snapshot(
                user,
                organization_id,
                days=request.args.get("days", 30),
            ),
        })
    except (PermissionError, LookupError, ValueError) as exc:
        return _api_error(exc)


@bp.get("/api/v1/organizations/<int:organization_id>/benefits")
def api_organization_benefits(organization_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        return jsonify({"benefits": list_benefit_plans(user, organization_id)})
    except (PermissionError, LookupError, ValueError) as exc:
        return _api_error(exc)
