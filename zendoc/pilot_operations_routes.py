"""Controlled beta feedback and cohort administration routes."""
from __future__ import annotations

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for

from .pilot_operations import (
    FEEDBACK_CATEGORIES,
    FEEDBACK_SEVERITIES,
    FEEDBACK_STATUSES,
    anonymized_technical_context,
    assign_cohort,
    cohort_admin_snapshot,
    create_feedback_report,
    deactivate_cohort_membership,
    list_feedback_reports,
    update_feedback_status,
)
from .release_state import release_state
from .security import login_required, owner_required


bp = Blueprint("pilot_operations", __name__)


@bp.get("/feedback")
@login_required
def feedback_page():
    page_path = str(request.args.get("page") or "/").strip()
    if not page_path.startswith("/") or page_path.startswith("//"):
        page_path = "/"
    page_path = page_path.split("?", 1)[0][:240]
    feature = str(request.args.get("feature") or "general").strip()[:120] or "general"
    return render_template(
        "feedback_report.html",
        page_path=page_path,
        feature=feature,
        categories=sorted(FEEDBACK_CATEGORIES),
        severities=["low", "medium", "high", "critical"],
        release=release_state(),
        submitted=request.args.get("submitted") == "1",
    )


@bp.post("/feedback")
@login_required
def feedback_submit():
    state = release_state()
    context = anonymized_technical_context(
        user_agent=request.headers.get("User-Agent"),
        method=request.method,
        endpoint=request.form.get("source_endpoint") or request.endpoint,
    )
    try:
        create_feedback_report(
            g.user,
            request.form,
            endpoint=request.form.get("source_endpoint"),
            technical_context=context,
            application_version=state.get("application_version"),
            release_channel=state.get("channel"),
        )
        flash("Thank you. Your feedback was recorded for the ZenDoc pilot team.", "success")
        return redirect(url_for("pilot_operations.feedback_page", submitted=1))
    except (PermissionError, ValueError) as error:
        flash(str(error), "error")
        return render_template(
            "feedback_report.html",
            page_path=request.form.get("page_path") or "/",
            feature=request.form.get("feature") or "general",
            categories=sorted(FEEDBACK_CATEGORIES),
            severities=["low", "medium", "high", "critical"],
            release=state,
            submitted=False,
        ), 400


@bp.get("/admin/pilot/feedback")
@owner_required
def feedback_admin():
    filters = {
        "role": request.args.get("role", ""),
        "feature": request.args.get("feature", ""),
        "severity": request.args.get("severity", ""),
        "status": request.args.get("status", ""),
        "date_from": request.args.get("date_from", ""),
        "date_to": request.args.get("date_to", ""),
    }
    try:
        reports = list_feedback_reports(g.user, filters)
    except ValueError as error:
        flash(str(error), "error")
        reports = []
    return render_template(
        "admin_pilot_feedback.html",
        reports=reports,
        filters=filters,
        severities=["", "low", "medium", "high", "critical"],
        statuses=["", *sorted(FEEDBACK_STATUSES)],
        release=release_state(),
    )


@bp.post("/admin/pilot/feedback/<int:feedback_id>/status")
@owner_required
def feedback_status_update(feedback_id):
    try:
        update_feedback_status(g.user, feedback_id, request.form.get("status"))
        flash("Feedback status updated.", "success")
    except (LookupError, PermissionError, ValueError) as error:
        flash(str(error), "error")
    return redirect(url_for("pilot_operations.feedback_admin"))


@bp.get("/admin/pilot/cohorts")
@owner_required
def cohort_admin():
    return render_template(
        "admin_pilot_cohorts.html",
        snapshot=cohort_admin_snapshot(g.user),
        release=release_state(),
    )


@bp.post("/admin/pilot/cohorts")
@owner_required
def cohort_assign():
    try:
        assign_cohort(
            g.user,
            entity_type=request.form.get("entity_type"),
            entity_id=int(request.form.get("entity_id")),
            cohort_label=request.form.get("cohort_label"),
        )
        flash("Pilot cohort label assigned.", "success")
    except (LookupError, PermissionError, TypeError, ValueError) as error:
        flash(str(error), "error")
    return redirect(url_for("pilot_operations.cohort_admin"))


@bp.post("/admin/pilot/cohorts/<int:membership_id>/remove")
@owner_required
def cohort_remove(membership_id):
    try:
        deactivate_cohort_membership(g.user, membership_id)
        flash("Pilot cohort label removed.", "success")
    except (LookupError, PermissionError, ValueError) as error:
        flash(str(error), "error")
    return redirect(url_for("pilot_operations.cohort_admin"))
