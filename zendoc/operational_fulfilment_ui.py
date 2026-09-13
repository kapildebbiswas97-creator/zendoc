"""Session-authenticated web console for diagnostic and home-health fulfilment."""
from __future__ import annotations

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .db import get_db
from .operational_fulfilment import (
    HOME_HEALTH_SERVICE_IDS,
    assign_home_health_provider,
    list_assigned_home_health_requests,
    list_home_health_providers,
    publish_home_health_service,
    update_diagnostic_booking_status,
    update_home_health_request_status,
)
from .operational_fulfilment_release import (
    link_diagnostic_report,
    list_diagnostic_provider_requests,
    list_my_home_health_capabilities,
    list_patient_diagnostic_requests,
    list_patient_home_health_requests,
    release_readiness,
)
from .security import is_owner, login_required


bp = Blueprint("operational_fulfilment_ui", __name__)


def _safe_provider_diagnostics(actor):
    try:
        return list_diagnostic_provider_requests(actor)
    except PermissionError:
        return []


def _safe_home_assignments(actor):
    try:
        return list_assigned_home_health_requests(actor)
    except PermissionError:
        return []


def _safe_capabilities(actor):
    try:
        return list_my_home_health_capabilities(actor)
    except PermissionError:
        return []


def _patient_provider_options(actor, requests):
    options = {}
    for item in requests:
        if item.get("provider_id"):
            continue
        try:
            options[int(item["id"])] = list_home_health_providers(
                str(item.get("service_type") or ""),
                city=str(item.get("city") or actor.get("city") or "").strip() or None,
            )
        except (LookupError, PermissionError, ValueError):
            options[int(item["id"])] = []
    return options


def _provider_reports(actor, bookings):
    reports = {}
    actor_id = int(actor["id"])
    db = get_db()
    for booking in bookings:
        if str(booking.get("status") or "").lower() != "completed" or booking.get("report_record_id"):
            continue
        rows = db.execute(
            """
            SELECT id,title,category,created_at
            FROM medical_records
            WHERE owner_id=? AND uploaded_by=?
            ORDER BY created_at DESC,id DESC
            LIMIT 50
            """,
            (int(booking["patient_id"]), actor_id),
        ).fetchall()
        reports[int(booking["id"])] = [dict(row) for row in rows]
    return reports


@bp.route("/operations/fulfilment", methods=("GET", "POST"))
@login_required
def fulfilment_console():
    actor = dict(g.user)
    role = str(actor.get("role") or "")
    if role not in {"patient", "doctor", "hospital", "admin"}:
        abort(403)
    if role == "admin" and not is_owner(actor):
        abort(403)

    if request.method == "POST":
        action = str(request.form.get("action") or "").strip()
        try:
            if action == "diagnostic_status":
                update_diagnostic_booking_status(
                    actor,
                    int(request.form.get("booking_id") or 0),
                    request.form.get("status"),
                    note=request.form.get("note"),
                )
                flash("Diagnostic workflow updated.", "success")
            elif action == "diagnostic_report":
                link_diagnostic_report(
                    actor,
                    int(request.form.get("booking_id") or 0),
                    int(request.form.get("record_id") or 0),
                )
                flash("Diagnostic report linked to the completed booking.", "success")
            elif action == "home_status":
                update_home_health_request_status(
                    actor,
                    int(request.form.get("request_id") or 0),
                    request.form.get("status"),
                    note=request.form.get("note"),
                )
                flash("Home-health workflow updated.", "success")
            elif action == "home_capability":
                publish_home_health_service(
                    actor,
                    request.form.get("service_type"),
                    active=str(request.form.get("active") or "1") == "1",
                )
                flash("Home-health capability updated.", "success")
            elif action == "home_assign":
                assign_home_health_provider(
                    actor,
                    int(request.form.get("request_id") or 0),
                    int(request.form.get("provider_id") or 0),
                )
                flash("Verified home-health provider assigned.", "success")
            else:
                raise ValueError("Unsupported fulfilment operation.")
        except (LookupError, PermissionError, ValueError) as error:
            flash(str(error), "error")
        return redirect(url_for("operational_fulfilment_ui.fulfilment_console"))

    patient_diagnostics = []
    patient_home = []
    provider_diagnostics = []
    provider_home = []
    capabilities = []
    provider_options = {}
    provider_reports = {}
    readiness = None

    if role == "patient":
        patient_diagnostics = list_patient_diagnostic_requests(actor)
        patient_home = list_patient_home_health_requests(actor)
        provider_options = _patient_provider_options(actor, patient_home)
    elif role in {"doctor", "hospital"}:
        provider_diagnostics = _safe_provider_diagnostics(actor)
        provider_home = _safe_home_assignments(actor)
        capabilities = _safe_capabilities(actor)
        provider_reports = _provider_reports(actor, provider_diagnostics)
    else:
        readiness = release_readiness(actor)

    return render_template(
        "fulfilment_operations.html",
        patient_diagnostics=patient_diagnostics,
        patient_home=patient_home,
        provider_diagnostics=provider_diagnostics,
        provider_home=provider_home,
        capabilities=capabilities,
        provider_options=provider_options,
        provider_reports=provider_reports,
        readiness=readiness,
        supported_home_services=sorted(HOME_HEALTH_SERVICE_IDS),
    )
