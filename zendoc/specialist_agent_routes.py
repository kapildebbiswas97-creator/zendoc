"""User-facing/API routes for the bounded ZENDOC specialist Agent OS."""
from __future__ import annotations

from flask import Blueprint, current_app, flash, g, jsonify, redirect, render_template, request, url_for

from .agent_autonomy import bounded_autonomy_manifest
from .agentic_decision_layer import decision_layer_manifest
from .agent_fleet import list_fleet_agents
from .agent_handoffs import handoff_for_intent, handoff_manifest
from .appointment_continuity import complete_follow_up, sync_provider_appointment_status
from .care_chain import build_persisted_care_chain, finalize_care_chain, prepare_care_chain
from .care_continuity import get_care_continuity_snapshot
from .care_journey_store import get_persisted_journey
from .careloop_integration import link_registered_appointment
from .db import get_db
from .provider_service import book_provider_slot
from .agent_planner import build_plan
from .agent_executor import TOOL_HANDLERS
from .tool_registry import check_tool_access
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


def _execute_confirmed_specialist_tool(user, tool_name: str, agent_name: str, data: dict) -> dict:
    if data.get("user_confirmed") is not True:
        raise PermissionError("Fresh explicit user confirmation is required before this action.")
    decision = check_tool_access(tool_name, user, agent_name)
    if not decision["allowed"]:
        raise PermissionError(decision["reason"])
    handler = TOOL_HANDLERS.get(tool_name)
    if not handler:
        raise LookupError(f"Tool '{tool_name}' has no bounded server-side handler.")
    return handler(user, data)


@bp.route("/agent-os", methods=("GET", "POST"))
@login_required
def agent_os_page():
    result = None
    follow_up_journey = None
    continuity_snapshot = None
    command = request.values.get("command", "")
    persisted_care_chain = None
    if request.method == "POST":
        try:
            context = _browser_context()
            preview_plan = build_plan(g.user, command)
            if preview_plan.authorization_error:
                raise PermissionError(preview_plan.authorization_error)
            prepared_chain = prepare_care_chain(
                g.user,
                command,
                intent=preview_plan.intent,
                privacy_class=preview_plan.privacy_class,
                input_channel=request.form.get("input_channel", "typed"),
                asr_audit_log_id=request.form.get("asr_audit_log_id"),
            )
            result = _attach_handoff(orchestrate_specialist(g.user, command, context))
            result["care_chain"] = prepared_chain
            result = persist_specialist_result(g.user, result, context)
            result = finalize_care_chain(g.user, result, prepared_chain)
            audit(
                "specialist_agent_orchestrate",
                "agent_os",
                f"{result['assigned_agent']}:{result['intent']}",
                actor=g.user,
            )
            get_db().commit()
        except (ValueError, LookupError, PermissionError) as error:
            flash(str(error), "error")
    elif request.args.get("journey_id"):
        try:
            journey_id = int(request.args.get("journey_id"))
            follow_up_journey = get_persisted_journey(journey_id, g.user)
            continuity_snapshot = get_care_continuity_snapshot(g.user, journey_id)
            persisted_care_chain = build_persisted_care_chain(g.user, journey_id)
        except (TypeError, ValueError, LookupError, PermissionError) as error:
            flash(str(error), "error")
    return render_template(
        "agent_os.html",
        result=result,
        follow_up_journey=follow_up_journey,
        continuity_snapshot=continuity_snapshot,
        persisted_care_chain=persisted_care_chain,
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


@bp.post("/agent-os/care-journeys/<int:journey_id>/follow-up/complete")
@login_required
def agent_os_follow_up_complete(journey_id):
    """Browser patient gate for completing evidence-backed post-visit follow-up."""
    try:
        result = complete_follow_up(
            g.user,
            journey_id,
            user_confirmed=request.form.get("user_confirmed") == "true",
        )
        audit("complete_follow_up", "care_journey", str(journey_id), actor=g.user)
        get_db().commit()
        flash("Post-visit follow-up marked complete.", "success")
    except (ValueError, LookupError, PermissionError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("specialist_agents.agent_os_page", journey_id=journey_id))


@bp.post("/api/v1/agent/orchestrate")
def api_orchestrate_specialist():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    context = data.get("context") if isinstance(data.get("context"), dict) else {}
    message = data.get("message", "")
    try:
        preview_plan = build_plan(user, message)
        if preview_plan.authorization_error:
            raise PermissionError(preview_plan.authorization_error)
        prepared_chain = prepare_care_chain(
            user,
            message,
            intent=preview_plan.intent,
            privacy_class=preview_plan.privacy_class,
            input_channel=data.get("input_channel", "typed"),
            asr_audit_log_id=data.get("asr_audit_log_id"),
        )
        result = _attach_handoff(orchestrate_specialist(
            user,
            message,
            context,
        ))
        result["care_chain"] = prepared_chain
        result = persist_specialist_result(user, result, context)
        result = finalize_care_chain(user, result, prepared_chain)
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


@bp.post("/api/v1/agent/home-health/confirm")
def api_confirm_agent_home_health():
    """Human gate for a prepared Home Health intake.

    This records a ZENDOC intake request only. Provider assignment/acceptance
    remains authoritative in the provider-controlled workflow.
    """
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        result = _execute_confirmed_specialist_tool(
            user,
            "confirm_home_health_request",
            "HomeHealthAgent",
            data,
        )
        audit("create", "agent_os_home_health_request", str(result.get("id") or ""), actor=user)
        get_db().commit()
        return jsonify(result), 201
    except (ValueError, LookupError, PermissionError) as exc:
        return _api_error(exc)


@bp.post("/api/v1/agent/transport/confirm")
def api_confirm_agent_transport():
    """Human gate for a prepared medical-transport intake.

    This never dispatches an ambulance or confirms a vehicle/provider. Emergency
    symptoms continue to use the deterministic Safety Agent path.
    """
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        result = _execute_confirmed_specialist_tool(
            user,
            "confirm_transport_request",
            "TransportAgent",
            data,
        )
        audit("create", "agent_os_transport_request", str(result.get("id") or ""), actor=user)
        get_db().commit()
        return jsonify(result), 201
    except (ValueError, LookupError, PermissionError) as exc:
        return _api_error(exc)


@bp.get("/api/v1/agent/care-journeys/<int:journey_id>/chain")
def api_agent_care_chain(journey_id):
    """Return the authoritative persisted half of one authorized Care Journey."""
    user, error = require_api_user()
    if error:
        return error
    try:
        return jsonify(build_persisted_care_chain(user, journey_id))
    except (ValueError, LookupError, PermissionError) as exc:
        return _api_error(exc)


@bp.get("/api/v1/agent/autonomy")
def api_agent_autonomy():
    user, error = require_api_user()
    if error:
        return error
    return jsonify({
        "autonomy": bounded_autonomy_manifest(),
        "decision_layer": decision_layer_manifest(),
        "handoffs": handoff_manifest(),
        "fleet": list_fleet_agents(),
        "actor_role": str(user["role"] or ""),
        "notice": "Fleet and handoff metadata do not grant tool permissions; every execution remains server-side permission checked.",
    })
