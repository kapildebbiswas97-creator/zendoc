"""Owner-only ZENDOC Model Evaluation Lab routes for Milestone 8.2."""
from __future__ import annotations

import hmac
import secrets
import time

from flask import Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template, request, session, url_for

from .db import get_db
from .model_candidates import get_model_candidate
from .model_evaluation import (
    DRY_RUN,
    MOCK,
    REAL_CONFIRMATION_PHRASE,
    REAL_LOCAL,
    BenchmarkLimits,
    evaluation_lab_data,
    get_evaluation_run,
    record_human_review,
    request_evaluation_stop,
    run_benchmark,
)
from .routes import audit, require_api_user
from .security import assert_owner, owner_required


bp = Blueprint("milestone82", __name__)
REAL_CONFIRMATION_TTL_SECONDS = 10 * 60
REAL_CONFIRMATION_SESSION_KEY = "model_evaluation_real_confirmation"


def _api_error(error, status=None):
    if status is None:
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


@bp.get("/api/v1/admin/model-evaluation")
def api_evaluation_lab():
    user, error = _api_owner()
    if error:
        return error
    return jsonify(evaluation_lab_data())


@bp.post("/api/v1/admin/model-evaluation/runs")
def api_create_evaluation_run():
    user, error = _api_owner()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    mode = str(data.get("mode") or DRY_RUN).strip().lower()
    if mode == REAL_LOCAL:
        return _api_error(
            PermissionError("Real local evaluation is available only through the owner web confirmation workflow."),
            409,
        )
    if mode not in {DRY_RUN, MOCK}:
        return _api_error(ValueError("API evaluation mode must be dry_run or mock."))
    try:
        run = run_benchmark(
            str(data.get("candidate_id") or "phi4-mini-dev-baseline"),
            mode=mode,
            actor_id=user["id"],
            case_ids=data.get("case_ids"),
            limits=_limits_from_mapping(data),
        )
        audit("evaluate", "model_evaluation_run", f"{run['id']}:{mode}", actor=user)
        get_db().commit()
        return jsonify({"run": run}), 201
    except (ValueError, LookupError, PermissionError) as exc:
        return _api_error(exc)


@bp.get("/api/v1/admin/model-evaluation/runs/<int:run_id>")
def api_evaluation_run(run_id):
    user, error = _api_owner()
    if error:
        return error
    try:
        return jsonify({"run": get_evaluation_run(run_id)})
    except LookupError as exc:
        return _api_error(exc)


@bp.get("/admin/model-evaluation")
@owner_required
def owner_evaluation_lab():
    return render_template("admin_model_evaluation.html", data=evaluation_lab_data())


@bp.post("/admin/model-evaluation/run/<mode>")
@owner_required
def owner_run_safe_evaluation(mode):
    mode = str(mode or "").strip().lower()
    if mode not in {DRY_RUN, MOCK}:
        abort(400, "Real local evaluation requires the preparation workflow.")
    try:
        run = run_benchmark(
            request.form.get("candidate_id", "phi4-mini-dev-baseline"),
            mode=mode,
            actor_id=g.user["id"],
            limits=_limits_from_mapping(request.form),
        )
        audit("evaluate", "model_evaluation_run", f"{run['id']}:{mode}", actor=g.user)
        get_db().commit()
        flash(f"{mode.replace('_', ' ').title()} completed without real model inference.", "success")
    except (ValueError, LookupError, PermissionError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("milestone82.owner_evaluation_lab"))


@bp.post("/admin/model-evaluation/prepare-real")
@owner_required
def owner_prepare_real_evaluation():
    candidate_id = str(request.form.get("candidate_id") or "").strip().lower()
    try:
        if not current_app.config.get("MODEL_EVALUATION_REAL_ENABLED", False):
            raise PermissionError("Real local evaluation is disabled by ZENDOC_MODEL_EVALUATION_REAL_ENABLED.")
        candidate = get_model_candidate(candidate_id, enabled_only=True)
        limits = _limits_from_mapping(request.form)
    except (ValueError, LookupError, PermissionError) as exc:
        flash(str(exc), "error")
        return redirect(url_for("milestone82.owner_evaluation_lab"))
    confirmation = {
        "token": secrets.token_urlsafe(32),
        "candidate_id": candidate["model_id"],
        "expires_at": int(time.time()) + REAL_CONFIRMATION_TTL_SECONDS,
        "limits": limits.to_dict(),
    }
    session[REAL_CONFIRMATION_SESSION_KEY] = confirmation
    audit("prepare", "model_evaluation_real", candidate["model_id"], actor=g.user)
    get_db().commit()
    return render_template(
        "admin_model_evaluation_confirm.html",
        candidate=candidate,
        confirmation=confirmation,
        phrase=REAL_CONFIRMATION_PHRASE,
    )


@bp.post("/admin/model-evaluation/run-real")
@owner_required
def owner_run_real_evaluation():
    try:
        if not current_app.config.get("MODEL_EVALUATION_REAL_ENABLED", False):
            raise PermissionError("Real local evaluation is disabled by ZENDOC_MODEL_EVALUATION_REAL_ENABLED.")
        confirmation = _consume_real_confirmation(
            request.form.get("confirmation_token"),
            request.form.get("candidate_id"),
            request.form.get("confirmation_phrase"),
        )
        limits = BenchmarkLimits(**confirmation["limits"]).validated()
        run = run_benchmark(
            confirmation["candidate_id"],
            mode=REAL_LOCAL,
            actor_id=g.user["id"],
            limits=limits,
            real_authorized=True,
        )
        audit("evaluate", "model_evaluation_run", f"{run['id']}:real_local", actor=g.user)
        get_db().commit()
        flash("Real local evaluation finished. Review safety gates before interpreting quality scores.", "success")
    except (ValueError, LookupError, PermissionError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("milestone82.owner_evaluation_lab"))


@bp.post("/admin/model-evaluation/runs/<int:run_id>/stop")
@owner_required
def owner_stop_evaluation(run_id):
    try:
        request_evaluation_stop(run_id)
        audit("stop", "model_evaluation_run", str(run_id), actor=g.user)
        get_db().commit()
        flash("Evaluation stop requested. The runner will stop before the next case.", "success")
    except (ValueError, LookupError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("milestone82.owner_evaluation_lab"))


@bp.post("/admin/model-evaluation/results/<int:result_id>/review")
@owner_required
def owner_review_evaluation_result(result_id):
    try:
        record_human_review(result_id, int(request.form.get("score", "")), request.form.get("notes", ""))
        audit("review", "model_evaluation_result", str(result_id), actor=g.user)
        get_db().commit()
        flash("Human review recorded.", "success")
    except (TypeError, ValueError, LookupError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("milestone82.owner_evaluation_lab"))


def _limits_from_mapping(data) -> BenchmarkLimits:
    def integer(name, default):
        value = data.get(name, default)
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be an integer.") from exc

    return BenchmarkLimits(
        max_cases=integer("max_cases", 12),
        max_output_tokens=integer("max_output_tokens", 256),
        timeout_seconds=integer("timeout_seconds", 15),
        cooldown_ms=integer("cooldown_ms", 0),
        concurrency=1,
        retries=0,
    ).validated()


def _consume_real_confirmation(token, candidate_id, phrase) -> dict:
    stored = session.pop(REAL_CONFIRMATION_SESSION_KEY, None)
    if not isinstance(stored, dict):
        raise PermissionError("Prepare the real local evaluation before confirming it.")
    if int(stored.get("expires_at") or 0) < int(time.time()):
        raise PermissionError("Real evaluation confirmation expired; prepare it again.")
    if not hmac.compare_digest(str(stored.get("token") or ""), str(token or "")):
        raise PermissionError("Real evaluation confirmation token is invalid.")
    if not hmac.compare_digest(str(stored.get("candidate_id") or ""), str(candidate_id or "")):
        raise PermissionError("Confirmed candidate does not match the prepared candidate.")
    if not hmac.compare_digest(str(phrase or "").strip(), REAL_CONFIRMATION_PHRASE):
        raise PermissionError("Type the exact real-evaluation confirmation phrase.")
    return stored
