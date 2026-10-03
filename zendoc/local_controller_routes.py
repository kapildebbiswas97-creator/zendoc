"""Owner-only API for the ZENDOC laptop/local controller."""
from flask import Blueprint, jsonify, request

from .local_controller import (
    execute_safe_local_controller_command,
    local_controller_snapshot,
    preview_local_controller_command,
)
from .routes import require_api_user
from .security import is_owner


bp = Blueprint("local_controller", __name__)


def _owner_api_user():
    user, error = require_api_user()
    if error:
        return None, error
    if not is_owner(user):
        return None, (
            jsonify({"error": {"code": 403, "message": "Configured owner access is required."}}),
            403,
        )
    return user, None


def _error(exc):
    code = 403 if isinstance(exc, PermissionError) else 400
    return jsonify({"error": {"code": code, "message": str(exc)}}), code


@bp.get("/api/v1/admin/local-controller/status")
def api_local_controller_status():
    user, error = _owner_api_user()
    if error:
        return error
    check_health = str(request.args.get("check_health") or "").strip().lower() in {"1", "true", "yes", "on"}
    try:
        return jsonify(local_controller_snapshot(user, check_health=check_health))
    except (PermissionError, TypeError, ValueError) as exc:
        return _error(exc)


@bp.post("/api/v1/admin/local-controller/command")
def api_local_controller_command():
    user, error = _owner_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    context = data.get("context") if isinstance(data.get("context"), dict) else {}
    mode = str(data.get("mode") or "preview").strip().lower()
    try:
        if mode == "preview":
            result = preview_local_controller_command(user, data.get("command"), context=context)
        elif mode == "execute_safe":
            result = execute_safe_local_controller_command(user, data.get("command"), context=context)
        else:
            raise ValueError("mode must be preview or execute_safe.")
        return jsonify(result)
    except (PermissionError, LookupError, TypeError, ValueError) as exc:
        return _error(exc)
