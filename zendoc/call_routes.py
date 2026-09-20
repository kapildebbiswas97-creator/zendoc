"""WebRTC call pages and authenticated signaling endpoints."""
from __future__ import annotations

import json
import os

from flask import Blueprint, abort, g, jsonify, render_template, request

from .call_signaling import (
    add_ice_candidate,
    answer_call,
    call_permission,
    create_call,
    end_call,
    get_call_state,
    list_incoming_calls,
)
from .security import login_required

bp = Blueprint("calls", __name__)


def _error(exc):
    if isinstance(exc, PermissionError):
        code = 403
    elif isinstance(exc, LookupError):
        code = 404
    else:
        code = 400
    return jsonify({"error": {"code": code, "message": str(exc)}}), code


def _ice_servers():
    raw = str(os.environ.get("ZENDOC_WEBRTC_ICE_SERVERS_JSON") or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    safe = []
    for item in data[:8]:
        if not isinstance(item, dict):
            continue
        urls = item.get("urls")
        values = [urls] if isinstance(urls, str) else urls if isinstance(urls, list) else []
        values = [str(url) for url in values if str(url).startswith(("stun:", "turn:", "turns:"))]
        if not values:
            continue
        clean = {"urls": values[0] if len(values) == 1 else values}
        if item.get("username"):
            clean["username"] = str(item["username"])[:300]
        if item.get("credential"):
            clean["credential"] = str(item["credential"])[:500]
        safe.append(clean)
    return safe


@bp.get("/calls/start/<int:conversation_id>/<call_type>")
@login_required
def call_start_page(conversation_id, call_type):
    try:
        permission = call_permission(g.user, conversation_id, call_type)
        if not permission["allowed"]:
            raise PermissionError(permission["reason"])
    except (ValueError, LookupError, PermissionError):
        abort(403)
    return render_template(
        "call.html",
        initial_call=None,
        conversation_id=conversation_id,
        call_type=permission["call_type"],
        other_name=permission["other_name"],
        initiator=True,
        ice_servers=_ice_servers(),
    )


@bp.get("/calls/<int:call_id>")
@login_required
def call_page(call_id):
    try:
        state = get_call_state(g.user, call_id)
    except (LookupError, PermissionError):
        abort(404)
    other_name = state["callee_name"] if int(state["actor_id"]) == int(state["initiator_id"]) else state["initiator_name"]
    return render_template(
        "call.html",
        initial_call=state,
        conversation_id=state["conversation_id"],
        call_type=state["call_type"],
        other_name=other_name,
        initiator=int(state["actor_id"]) == int(state["initiator_id"]),
        ice_servers=_ice_servers(),
    )


@bp.get("/calls/incoming")
@login_required
def incoming_calls():
    return jsonify({"calls": list_incoming_calls(g.user)})


@bp.post("/calls/create")
@login_required
def create_call_route():
    try:
        state = create_call(
            g.user,
            int(request.form.get("conversation_id") or 0),
            request.form.get("call_type"),
            request.form.get("offer_json"),
        )
        return jsonify({"call": state}), 201
    except (TypeError, ValueError, LookupError, PermissionError) as exc:
        return _error(exc)


@bp.get("/calls/<int:call_id>/state")
@login_required
def call_state_route(call_id):
    try:
        return jsonify({
            "call": get_call_state(
                g.user,
                call_id,
                after_candidate_id=int(request.args.get("after_candidate_id") or 0),
            )
        })
    except (TypeError, ValueError, LookupError, PermissionError) as exc:
        return _error(exc)


@bp.post("/calls/<int:call_id>/answer")
@login_required
def answer_call_route(call_id):
    try:
        accept = str(request.form.get("accept") or "").lower() in {"1", "true", "yes", "on"}
        state = answer_call(
            g.user,
            call_id,
            accept=accept,
            answer_json=request.form.get("answer_json"),
        )
        return jsonify({"call": state})
    except (TypeError, ValueError, LookupError, PermissionError) as exc:
        return _error(exc)


@bp.post("/calls/<int:call_id>/ice")
@login_required
def add_ice_route(call_id):
    try:
        item = add_ice_candidate(g.user, call_id, request.form.get("candidate_json"))
        return jsonify({"candidate": item}), 201
    except (TypeError, ValueError, LookupError, PermissionError) as exc:
        return _error(exc)


@bp.post("/calls/<int:call_id>/end")
@login_required
def end_call_route(call_id):
    try:
        return jsonify({"call": end_call(g.user, call_id)})
    except (TypeError, ValueError, LookupError, PermissionError) as exc:
        return _error(exc)
