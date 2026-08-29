"""Milestone 8 APIs and owner command-center workflow actions."""
from __future__ import annotations

from flask import Blueprint, abort, flash, g, jsonify, redirect, request, url_for

from .agent_alerts import acknowledge_alert, list_alerts, resolve_alert, run_proactive_alert_check
from .agent_approvals import list_approvals, list_approvals_for_actor, resolve_approval
from .agent_registry import list_agents
from .agent_task_engine import create_agent_task, execute_safe_task, get_agent_task, list_agent_tasks, retry_task
from .capability_registry import get_capability_registry
from .db import get_db
from .event_bus import list_events
from .infrastructure import infrastructure_status
from .model_router import get_model_router
from .routes import audit, require_api_user
from .security import assert_owner, owner_required
from .tool_registry import list_tools_for_actor


bp = Blueprint("milestone8", __name__)

OWNER_TASK_TYPES = {
    "proactive_alert_check": {
        "assigned_agent": "OperationsAgent",
        "risk_level": "low_risk",
    },
}


def _api_error(error):
    if isinstance(error, PermissionError):
        status = 403
    elif isinstance(error, LookupError):
        status = 404
    else:
        status = 400
    return jsonify({"error": {"code": status, "message": str(error)}}), status


def _api_user():
    return require_api_user()


def _api_owner():
    user, error = require_api_user()
    if error:
        return None, error
    try:
        assert_owner(user)
    except PermissionError as exc:
        return None, _api_error(exc)
    return user, None


def _handler_for_task(task, actor):
    if task["task_type"] == "proactive_alert_check":
        assert_owner(actor)
        return f"Created {len(run_proactive_alert_check())} new deterministic operational alert(s)."
    raise LookupError(f"No bounded handler is registered for task type '{task['task_type']}'.")


@bp.get("/api/v1/capabilities")
def api_capabilities():
    user, error = _api_user()
    if error:
        return error
    return jsonify({"capabilities": get_capability_registry()})


@bp.get("/api/v1/agent/registry")
def api_agent_registry():
    user, error = _api_user()
    if error:
        return error
    role = user["role"]
    return jsonify({"agents": [agent for agent in list_agents() if role in agent["allowed_actor_roles"]]})


@bp.get("/api/v1/agent/tools")
def api_tool_registry():
    user, error = _api_user()
    if error:
        return error
    return jsonify({"tools": list_tools_for_actor(user)})


@bp.get("/api/v1/admin/model-router")
def api_model_router_status():
    user, error = _api_owner()
    if error:
        return error
    return jsonify(get_model_router().status())


@bp.get("/api/v1/admin/infrastructure")
def api_infrastructure_status():
    user, error = _api_owner()
    if error:
        return error
    return jsonify(infrastructure_status())


@bp.get("/api/v1/agent/tasks")
def api_agent_tasks():
    user, error = _api_user()
    if error:
        return error
    try:
        tasks = list_agent_tasks(request.args.get("status"), request.args.get("limit", 50), actor=user)
        return jsonify({"tasks": tasks})
    except (ValueError, PermissionError) as exc:
        return _api_error(exc)


@bp.post("/api/v1/admin/agent/tasks")
def api_create_owner_task():
    user, error = _api_owner()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    task_type = str(data.get("task_type") or "").strip()
    definition = OWNER_TASK_TYPES.get(task_type)
    if not definition:
        return _api_error(ValueError("Unsupported owner task type."))
    try:
        task = create_agent_task(
            task_type=task_type,
            requested_by=user["id"],
            assigned_agent=definition["assigned_agent"],
            risk_level=definition["risk_level"],
            priority=str(data.get("priority") or "normal"),
            idempotency_key=data.get("idempotency_key"),
            metadata={"source": "owner_api"},
            actor=user,
        )
        audit("create", "agent_task", str(task["id"]), actor=user)
        get_db().commit()
        return jsonify({"task": task}), 201
    except (ValueError, LookupError, PermissionError) as exc:
        return _api_error(exc)


@bp.get("/api/v1/agent/tasks/<int:task_id>")
def api_agent_task(task_id):
    user, error = _api_user()
    if error:
        return error
    try:
        task = get_agent_task(task_id, actor=user)
        attempts = [dict(row) for row in get_db().execute(
            "SELECT * FROM agent_task_attempts WHERE task_id=? ORDER BY id", (task_id,)
        ).fetchall()]
        return jsonify({"task": task, "attempts": attempts})
    except (LookupError, PermissionError) as exc:
        return _api_error(exc)


@bp.post("/api/v1/agent/tasks/<int:task_id>/execute")
def api_execute_agent_task(task_id):
    user, error = _api_user()
    if error:
        return error
    try:
        task = execute_safe_task(task_id, user, handler_fn=lambda row: _handler_for_task(row, user))
        audit("execute", "agent_task", str(task_id), actor=user)
        get_db().commit()
        return jsonify({"task": task})
    except (ValueError, LookupError, PermissionError) as exc:
        return _api_error(exc)


@bp.post("/api/v1/agent/tasks/<int:task_id>/retry")
def api_retry_agent_task(task_id):
    user, error = _api_user()
    if error:
        return error
    try:
        task = retry_task(task_id, user)
        audit("retry", "agent_task", str(task_id), actor=user)
        get_db().commit()
        return jsonify({"task": task})
    except (ValueError, LookupError, PermissionError) as exc:
        return _api_error(exc)


@bp.get("/api/v1/admin/approvals")
def api_approvals():
    user, error = _api_owner()
    if error:
        return error
    return jsonify({"approvals": list_approvals(request.args.get("status"), request.args.get("limit", 50))})


@bp.get("/api/v1/agent/approvals")
def api_actor_approvals():
    user, error = _api_user()
    if error:
        return error
    try:
        return jsonify({"approvals": list_approvals_for_actor(user, request.args.get("status"), request.args.get("limit", 50))})
    except (ValueError, PermissionError) as exc:
        return _api_error(exc)


@bp.post("/api/v1/agent/approvals/<int:approval_id>/decision")
def api_actor_resolve_approval(approval_id):
    user, error = _api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        approval = resolve_approval(approval_id, user, data.get("decision"), data.get("note", ""))
        audit("resolve", "agent_approval", f"{approval_id}:{approval['status']}", actor=user)
        get_db().commit()
        return jsonify({"approval": approval})
    except (ValueError, LookupError, PermissionError) as exc:
        return _api_error(exc)


@bp.post("/api/v1/admin/approvals/<int:approval_id>/decision")
def api_resolve_approval(approval_id):
    user, error = _api_owner()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        approval = resolve_approval(approval_id, user, data.get("decision"), data.get("note", ""))
        audit("resolve", "agent_approval", f"{approval_id}:{approval['status']}", actor=user)
        get_db().commit()
        return jsonify({"approval": approval})
    except (ValueError, LookupError, PermissionError) as exc:
        return _api_error(exc)


@bp.get("/api/v1/admin/alerts")
def api_alerts():
    user, error = _api_owner()
    if error:
        return error
    status = request.args.get("status", "active")
    if status == "all":
        status = None
    return jsonify({"alerts": list_alerts(status, request.args.get("limit", 50))})


@bp.post("/api/v1/admin/alerts/check")
def api_run_alert_check():
    user, error = _api_owner()
    if error:
        return error
    alerts = run_proactive_alert_check()
    audit("check", "agent_alerts", str(len(alerts)), actor=user)
    get_db().commit()
    return jsonify({"created_alerts": alerts})


@bp.post("/api/v1/admin/alerts/<int:alert_id>/acknowledge")
def api_acknowledge_alert(alert_id):
    user, error = _api_owner()
    if error:
        return error
    try:
        return jsonify({"alert": acknowledge_alert(alert_id, user)})
    except (ValueError, LookupError, PermissionError) as exc:
        return _api_error(exc)


@bp.post("/api/v1/admin/alerts/<int:alert_id>/resolve")
def api_resolve_alert(alert_id):
    user, error = _api_owner()
    if error:
        return error
    try:
        return jsonify({"alert": resolve_alert(alert_id, user)})
    except (ValueError, LookupError, PermissionError) as exc:
        return _api_error(exc)


@bp.get("/api/v1/events")
def api_events():
    user, error = _api_user()
    if error:
        return error
    try:
        events = list_events(user, request.args.get("after_id", 0), request.args.get("limit", 100))
        return jsonify({"events": events, "next_after_id": events[-1]["id"] if events else int(request.args.get("after_id", 0) or 0)})
    except ValueError as exc:
        return _api_error(exc)


# Owner Command Center form actions. Every button maps to one of the workflows above.
@bp.post("/admin/agent-alerts/check")
@owner_required
def owner_alert_check():
    created = run_proactive_alert_check()
    flash(f"Operational scan completed: {len(created)} new alert(s).", "success")
    return redirect(url_for("milestone7.admin_agent_command_center"))


@bp.post("/admin/agent-alerts/<int:alert_id>/<action>")
@owner_required
def owner_alert_action(alert_id, action):
    try:
        if action == "acknowledge":
            acknowledge_alert(alert_id, g.user)
        elif action == "resolve":
            resolve_alert(alert_id, g.user)
        else:
            abort(404)
        flash("Alert updated.", "success")
    except (ValueError, LookupError, PermissionError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("milestone7.admin_agent_command_center"))


@bp.post("/admin/agent-approvals/<int:approval_id>/<decision>")
@owner_required
def owner_approval_action(approval_id, decision):
    try:
        resolve_approval(approval_id, g.user, decision, request.form.get("note", ""))
        flash(f"Approval {decision}.", "success")
    except (ValueError, LookupError, PermissionError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("milestone7.admin_agent_command_center"))


@bp.post("/admin/agent-tasks/<int:task_id>/retry")
@owner_required
def owner_task_retry(task_id):
    try:
        retry_task(task_id, g.user)
        flash("Safe task queued for retry.", "success")
    except (ValueError, LookupError, PermissionError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("milestone7.admin_agent_command_center"))
