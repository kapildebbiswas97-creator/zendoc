"""User-facing/API routes for the bounded ZENDOC specialist Agent OS."""
from __future__ import annotations

from flask import Blueprint, flash, g, jsonify, render_template, request

from .agent_autonomy import bounded_autonomy_manifest
from .agent_fleet import list_fleet_agents
from .agent_handoffs import handoff_for_intent, handoff_manifest
from .careloop_integration import link_registered_appointment
from .db import get_db
from .provider_service import book_provider_slot
from .routes import audit, create_notification, login_required, require_api_user
from .specialist_orchestrator import orchestrate_specialist
from .startup_analytics import record_product_activity


bp = Blueprint("specialist_agents", __name__)


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
    }


def _attach_handoff(result):
    result["handoff_chain"] = handoff_for_intent(result.get("intent"))
    return result


@bp.route("/agent-os", methods=("GET", "POST"))
@login_required
def agent_os_page():
    result = None
    command = request.values.get("command", "")
    if request.method == "POST":
        try:
            result = _attach_handoff(orchestrate_specialist(g.user, command, _browser_context()))
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


@bp.post("/api/v1/agent/orchestrate")
def api_orchestrate_specialist():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        result = _attach_handoff(orchestrate_specialist(
            user,
            data.get("message", ""),
            data.get("context") if isinstance(data.get("context"), dict) else {},
        ))
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

    The model never calls this endpoint by itself. The authenticated patient/app
    must send ``user_confirmed: true`` together with the exact provider and slot
    selected from the read-only Booking Agent result.
    """
    user, error = require_api_user()
    if error:
        return error
    if str(user["role"] or "") != "patient":
        return _api_error(PermissionError("Only an authenticated patient can confirm an Agent OS appointment."))

    data = request.get_json(silent=True) or {}
    if data.get("user_confirmed") is not True:
        return _api_error(PermissionError("Fresh explicit user confirmation is required before booking."))
    try:
        provider_profile_id = int(data.get("provider_profile_id") or 0)
    except (TypeError, ValueError):
        provider_profile_id = 0
    scheduled_for = str(data.get("scheduled_for") or "").strip()[:32]
    reason = str(data.get("reason") or "Requested through ZENDOC Agent OS").strip()[:500]
    if not provider_profile_id or not scheduled_for:
        return _api_error(ValueError("provider_profile_id and scheduled_for are required."))

    try:
        appointment_id = book_provider_slot(user, provider_profile_id, scheduled_for, reason)
    except (ValueError, PermissionError) as exc:
        return _api_error(exc)

    warnings = []
    careloop_action_id = None
    try:
        careloop_action_id = link_registered_appointment(user, appointment_id=appointment_id)
    except Exception:
        warnings.append("Appointment was created, but CareLoop linking needs reconciliation.")

    try:
        create_notification(user["id"], "Appointment requested", "Your Agent OS appointment request was saved.")
        record_product_activity(user, event_type="appointment_requested")
        audit("create", "agent_os_connected_appointment", str(appointment_id), actor=user)
        get_db().commit()
    except Exception:
        get_db().rollback()
        warnings.append("Appointment was created, but one or more secondary notification/audit updates need reconciliation.")

    return jsonify({
        "status": "REQUESTED",
        "appointment_id": appointment_id,
        "provider_profile_id": provider_profile_id,
        "scheduled_for": scheduled_for,
        "careloop_action_id": careloop_action_id,
        "provider_confirmation_state": "requested",
        "payment_executed": False,
        "user_confirmed": True,
        "warnings": warnings,
        "truth_notice": (
            "The appointment request is persisted for a verified connected ZENDOC provider. "
            "It is not provider-confirmed until the provider accepts it, and no payment was executed by AI."
        ),
    }), 201


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
