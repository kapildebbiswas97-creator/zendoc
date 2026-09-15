"""Owner-only EdgeCare runtime inspection and harmless local-AI smoke test."""
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify

from .db import get_db
from .edgecare_runtime import EdgeCareSettings, build_edgecare_status, load_benchmark_evidence
from .model_router import get_model_router
from .routes import audit, require_api_user
from .security import assert_owner


bp = Blueprint("edgecare", __name__)


def _api_error(error):
    if isinstance(error, PermissionError):
        status = 403
    elif isinstance(error, LookupError):
        status = 404
    else:
        status = 400
    return jsonify({"error": {"code": status, "message": str(error)}}), status


def _api_owner():
    user, error = require_api_user()
    if error:
        return None, error
    try:
        assert_owner(user)
    except PermissionError as exc:
        return None, _api_error(exc)
    return user, None


def _runtime_snapshot(check_health: bool = True):
    settings = EdgeCareSettings.from_runtime()
    router_status = get_model_router().status(check_health=check_health)
    evidence = load_benchmark_evidence(Path(current_app.root_path).resolve().parent, settings)
    edgecare = build_edgecare_status(
        local_ai_status=router_status.get("local_ai"),
        settings=settings,
        evidence=evidence,
    )
    return {"edgecare": edgecare, "model_router": router_status}


@bp.get("/api/v1/admin/edgecare/runtime")
def api_edgecare_runtime():
    user, error = _api_owner()
    if error:
        return error
    return jsonify(_runtime_snapshot(check_health=True))


@bp.post("/api/v1/admin/edgecare/test")
def api_edgecare_test():
    """Run the existing fixed harmless local-only prompt; caller text is never accepted."""
    user, error = _api_owner()
    if error:
        return error

    result = get_model_router().test_local_ai(actor_id=user["id"])
    audit(
        "test_edgecare_local_ai",
        "model_provider",
        f"{result.provider}:{'success' if result.success else result.error_category or 'failed'}",
        actor=user,
    )
    get_db().commit()
    return jsonify({
        "result": result.to_dict(),
        **_runtime_snapshot(check_health=True),
    })
