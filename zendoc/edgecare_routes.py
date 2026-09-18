"""EdgeCare runtime inspection, local-AI smoke tests, and bounded local ASR."""
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for

from .db import get_db
from .edgecare_asr import get_edgecare_asr
from .edgecare_runtime import EdgeCareSettings, build_edgecare_status, load_benchmark_evidence
from .model_router import get_model_router
from .routes import audit, require_api_user
from .security import assert_owner, login_required, owner_required


bp = Blueprint("edgecare", __name__)


def _api_error(error, status_override=None):
    if status_override is not None:
        status = int(status_override)
    elif isinstance(error, PermissionError):
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
    asr_status = get_edgecare_asr().status(check_health=check_health)
    evidence = load_benchmark_evidence(Path(current_app.root_path).resolve().parent, settings)
    edgecare = build_edgecare_status(
        local_ai_status=router_status.get("local_ai"),
        settings=settings,
        evidence=evidence,
    )
    edgecare["local_asr"] = asr_status
    edgecare["claims"]["local_asr_ready"] = asr_status.get("status") == "ready"
    return {"edgecare": edgecare, "model_router": router_status}


@bp.get("/admin/edgecare")
@owner_required
def edgecare_admin_page():
    """Human-readable owner dashboard for competition/runtime verification."""
    return render_template("edgecare_admin.html", snapshot=_runtime_snapshot(check_health=True))


@bp.post("/admin/edgecare/test-local-ai")
@owner_required
def edgecare_admin_test_local_ai():
    """Run the fixed harmless local-model test from the owner dashboard."""
    from flask import g

    result = get_model_router().test_local_ai(actor_id=g.user["id"])
    audit(
        "test_edgecare_local_ai",
        "model_provider",
        f"{result.provider}:{'success' if result.success else result.error_category or 'failed'}",
        actor=g.user,
    )
    get_db().commit()
    if result.success:
        flash(f"Local AI smoke test passed with {result.provider} / {result.model}.", "success")
    else:
        flash(
            f"Local AI smoke test did not pass: {result.error_category or 'runtime unavailable'}.",
            "warning",
        )
    return redirect(url_for("edgecare.edgecare_admin_page"))


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


@bp.post("/edgecare/asr/transcribe")
@login_required
def web_edgecare_transcribe():
    """Transcribe one bounded audio clip through the configured local ASR runtime.

    CSRF validation is provided by the application's normal non-API POST guard.
    The transcript is returned to the browser and is not persisted by this route.
    """
    upload = request.files.get("audio")
    if upload is None:
        return _api_error("Missing audio clip.", 400)

    asr = get_edgecare_asr()
    audio = upload.stream.read(asr.settings.max_audio_bytes + 1)
    if len(audio) > asr.settings.max_audio_bytes:
        return _api_error("Audio clip is too large.", 413)

    result = asr.transcribe(
        audio,
        filename=upload.filename or "voice.webm",
        mimetype=upload.mimetype or "audio/webm",
    )

    # Keep a metadata-only evidence link for the care chain. The audio and
    # transcript are deliberately excluded from audit_logs.
    from flask import g

    audit_entity_id = (
        f"{str(result.provider or 'local')[:60]}:"
        f"{str(result.model or 'unknown')[:80]}:"
        f"{'success' if result.success else str(result.error_category or 'failed')[:60]}"
    )
    audit(
        "edgecare_asr_transcribe",
        "local_asr",
        audit_entity_id,
        actor=g.user,
    )
    audit_row = get_db().execute(
        """
        SELECT id FROM audit_logs
        WHERE actor_id=? AND action='edgecare_asr_transcribe'
          AND entity_type='local_asr' AND entity_id=?
        ORDER BY id DESC LIMIT 1
        """,
        (int(g.user["id"]), audit_entity_id),
    ).fetchone()
    get_db().commit()
    audit_id = int(audit_row["id"]) if audit_row else None

    payload = result.to_dict()
    payload["audit_log_id"] = audit_id
    payload["audit_contains_transcript"] = False
    payload["audio_persisted"] = False

    if not result.success:
        status = 503 if result.error_category in {
            "disabled",
            "integration_required",
            "model_not_configured",
            "model_missing",
            "provider_unavailable",
            "provider_error",
            "unsafe_provider_url",
        } else 400
        return jsonify({"result": payload}), status
    return jsonify({"result": payload})
