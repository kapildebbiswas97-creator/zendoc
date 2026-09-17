"""User-facing/API routes for the bounded ZENDOC specialist Agent OS."""
from __future__ import annotations

from flask import Blueprint, flash, g, jsonify, render_template, request

from .agent_autonomy import bounded_autonomy_manifest
from .agent_fleet import list_fleet_agents
from .db import get_db
from .routes import audit, login_required, require_api_user
from .specialist_orchestrator import orchestrate_specialist


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


@bp.route("/agent-os", methods=("GET", "POST"))
@login_required
def agent_os_page():
    result = None
    command = request.values.get("command", "")
    if request.method == "POST":
        try:
            result = orchestrate_specialist(g.user, command, _browser_context())
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
    )


@bp.post("/api/v1/agent/orchestrate")
def api_orchestrate_specialist():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        result = orchestrate_specialist(
            user,
            data.get("message", ""),
            data.get("context") if isinstance(data.get("context"), dict) else {},
        )
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


@bp.get("/api/v1/agent/autonomy")
def api_agent_autonomy():
    user, error = require_api_user()
    if error:
        return error
    return jsonify({
        "autonomy": bounded_autonomy_manifest(),
        "fleet": list_fleet_agents(),
        "actor_role": str(user["role"] or ""),
        "notice": "Fleet metadata does not grant tool permissions; every execution remains server-side permission checked.",
    })
