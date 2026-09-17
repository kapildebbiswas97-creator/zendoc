"""User-facing/API routes for the bounded ZENDOC specialist Agent OS."""
from __future__ import annotations

from flask import Blueprint, current_app, flash, g, jsonify, redirect, render_template, request, url_for

from .agent_autonomy import bounded_autonomy_manifest
from .agent_fleet import list_fleet_agents
from .agent_handoffs import handoff_for_intent, handoff_manifest
from .appointment_continuity import sync_provider_appointment_status
from .careloop_integration import link_registered_appointment
from .db import get_db
from .provider_service import book_provider_slot
from .routes import audit, create_notification, login_required, require_api_user
from .specialist_orchestrator import orchestrate_specialist
from .specialist_workflow_store import (
    mark_booking_requested,
    persist_specialist_result,
    validate_booking_confirmation,
)
from .startup_analytics import record_product_activity


bp = Blueprint("specialist_agents", __name__)


@bp.after_app_request
def reconcile_provider_appointment_outcome(response):
    """Post-commit continuity hook for the authoritative provider status route.

    The main appointment route remains the source of truth and commits first.
    This hook never turns an Agent OS/model assertion into provider truth. If
    continuity reconciliation fails, the legitimate provider status change is
    preserved and the failure is logged for repair rather than rolled back.
    """
    if (
        request.method != "POST"
        or request.endpoint != "main.appointment_status"
        or response.status_code >= 400
        or not getattr(g, "user", None)
    ):
        return response
    appointment_id = (request.view_args or {}).get("appointment_id")
    if not appointment_id:
        return response
    try:
        sync_provider_appointment_status(g.user, int(appointment_id))
    except Exception:
        current_app.logger.exception(
            "Appointment continuity reconciliation failed for appointment %s",
            appointment_id,
        )
    return response


def _api_error(error):
    if isinstance(error, PermissionError):
        status = 403
    elif isinstance(error, LookupError):
        status = 404
    else:
        status = 400
    return jsonify({"error": {"code": status, "message": str(error)}}), status


def _browser_context():
    return {
        "provider_profile_id": request.form.get("provider_profile_id"),
        "date": request.form.get("date"),
        "category": request.form.get("category"),
        "journey_id": request.form.get("journey_id"),
        "workflow_task_id": request.form.get("workflow_task_id"),
    }


def _attach_handoff(result):
    result["handoff_chain"] = handoff_for_intent(result.get("intent"))
    return result


def _confirm_connected_booking(user, data: dict, *, require_persisted_refs: bool = False) -> dict:
    """Create one connected booking request after deterministic human-gate checks."""
    if str(user["role"] or "") != "patient":
        raise PermissionError("Only an authenticated patient can confirm an Agent OS appointment.")
    if data.get("user_confirmed") is not True:
        raise PermissionError("Fresh explicit user confirmation is required before booking.")

    try:
        provider_profile_id = int(data.get("provider_profile_id") or 0)
    except (TypeError, ValueError):
        provider_profile_id = 0
    scheduled_for = str(data.get("scheduled_for") or "").strip()[:32]
    reason = str(data.get("reason") or "Requested through ZENDOC Agent OS").strip()[:500]
    if not provider_profile_id or not scheduled_for:
        raise ValueError("provider_profile_id and scheduled_for are required.")

    journey_id = data.get("journey_id")
    workflow_task_id = data.get("workflow_task_id")
    if require_persisted_refs and (not journey_id or not workflow_task_id):
        raise PermissionError("The booking flow requires its persisted Agent OS task and Care Journey references.")

    # Validate workflow ownership/state before any appointment side effect.
    validate_booking_confirmation(
        user,
        journey_id=journey_id,
        workflow_task_id=workflow_task_id,
    )

    appointment_id = book_provider_slot(user, provider_profile_id, scheduled_for, reason)

    warnings = []
    careloop_action_id = None
    try:
        careloop_action_id = link_registered_appointment(
            user,
            appointment_id=appointment_id,
            journey_id=journey_id,
        )
        get_db().commit()
    except Exception:
        get_db().rollback()
        warnings.append("Appointment was created, but CareLoop linking needs reconciliation.")

    persisted = {"workflow_task": None, "care_journey": None}
    try:
        persisted = mark_booking_requested(
            user,
            appointment_id=appointment_id,
            provider_profile_id=provider_profile_id,
            journey_id=journey_id,
            workflow_task_id=workflow_task_id,
        )
    except Exception:
        get_db().rollback()
        warnings.append("Appointment was created, but Agent OS workflow state needs reconciliation.")

    try:
        create_notification(user["id"], "Appointment requested", "Your Agent OS appointment request was saved.")
        record_product_activity(user, event_type="appointment_requested")
        audit("create", "agent_os_connected_appointment", str(appointment_id), actor=user)
        get_db().commit()
    except Exception:
        get_db().rollback()
        warnings.append("Appointment was created, but one or more secondary notification/audit updates need reconciliation.")

    return {
        "status": "REQUESTED",
        "appointment_id": appointment_id,
        "provider_profile_id": provider_profile_id,
        "scheduled_for": scheduled_for,
        "careloop_action_id": careloop_action_id,
        "workflow_task": persisted.get("workflow_task"),
        "care_journey": persisted.get("care_journey"),
        "provider_confirmation_state": "requested",
        "payment_executed": False,
        "user_confirmed": True,
        "warnings": warnings,
        "truth_notice": (
            "The appointment request is persisted for a verified connected ZENDOC provider on the same Care Journey. "
            "It is not provider-confirmed until the provider accepts it, and no payment was executed by AI."
        ),
    }


@bp.route("/agent-os", methods=("GET", "POST"))
@login_required
def agent_os_page():
    result = None
    command = request.values.get("command", "")
    if request.method == "POST":
        try:
            context = _browser_context()
            result = _attach_handoff(orchestrate_specialist(g.user, command, context))
            result = persist_specialist_result(g.user, result, context)
            audit(
                "specialist_agent_orchestrate",
                "agent_os",
                f"{result['assigned_agent']}:{result['intent']}",
                actor=g.user,
            )
            get_db().commit()
        except (ValueError, LookupError, PermissionError) as error:
            flash(str(error), "error")
    return render_template(
        "agent_os.html",
        result=result,
        command=command,
        fleet=list_fleet_agents(),
        autonomy=bounded_autonomy_manifest(),
        handoffs=handoff_manifest(),
    )


@bp.post("/agent-os/booking/confirm")
@login_required
def agent_os_booking_confirm():
    """Browser human-gate for an already staged connected provider slot."""
    data = {
        "provider_profile_id": request.form.get("provider_profile_id"),
        "scheduled_for": request.form.get("scheduled_for"),
        "reason": request.form.get("reason"),
        "journey_id": request.form.get("journey_id"),
        "workflow_task_id": request.form.get("workflow_task_id"),
        "user_confirmed": request.form.get("user_confirmed") == "true",
    }
    try:
        result = _confirm_connected_booking(g.user, data, require_persisted_refs=True)
    except (ValueError, LookupError, PermissionError) as exc:
        flash(str(exc), "error")
        return redirect(url_for("specialist_agents.agent_os_page"))

    flash(
        f"Appointment request #{result['appointment_id']} saved. Provider confirmation is still pending.",
        "success",
    )
    for warning in result.get("warnings") or []:
        flash(warning, "warning")
    return redirect(url_for("main.appointments"))


@bp.post("/api/v1/agent/orchestrate")
def api_orchestrate_specialist():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    context = data.get("context") if isinstance(data.get("context"), dict) else {}
    try:
        result = _attach_handoff(orchestrate_specialist(
            user,
            data.get("message", ""),
            context,
        ))
        result = persist_specialist_result(user, result, context)
        audit(
            "specialist_agent_orchestrate",
            "agent_os",
            f"{result['assigned_agent']}:{result['intent']}",
            actor=user,
        )
        get_db().commit()
        return jsonify(result)
    except (ValueError, LookupError, PermissionError) as exc:
        return _api_error(exc)


@bp.post("/api/v1/agent/booking/confirm")
def api_confirm_agent_booking():
    """Finalize a previously inspected connected slot after fresh user consent.

    The model never receives an arbitrary HTTP/browser tool for this endpoint.
    The authenticated patient/app must send ``user_confirmed: true`` together
    with the exact provider and slot selected from the read-only Booking Agent
    result plus the persisted Agent OS task and Care Journey references.
    """
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(_confirm_connected_booking(user, data, require_persisted_refs=True)), 201
    except (ValueError, LookupError, PermissionError) as exc:
        return _api_error(exc)


@bp.get("/api/v1/agent/autonomy")
def api_agent_autonomy():
    user, error = require_api_user()
    if error:
        return error
    return jsonify({
        "autonomy": bounded_autonomy_manifest(),
        "handoffs": handoff_manifest(),
        "fleet": list_fleet_agents(),
        "actor_role": str(user["role"] or ""),
        "notice": "Fleet and handoff metadata do not grant tool permissions; every execution remains server-side permission checked.",
    })
