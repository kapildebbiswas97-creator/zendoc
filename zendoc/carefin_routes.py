"""Authenticated CareFin discovery and durable case-tracking routes."""
from __future__ import annotations

from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, url_for

from .carefin_cases import (
    apply_carefin_partner_response,
    build_claim_packet,
    carefin_case_options,
    create_carefin_case,
    get_carefin_case,
    list_carefin_cases,
    owner_transition_case,
    request_case_verification,
    submit_case_evidence,
)
from .carefin_engine import discover_benefits
from .routes import audit, require_api_user
from .security import login_required, owner_required


bp = Blueprint("carefin", __name__)


def _context(user, data):
    return {
        "geography": data.get("geography"),
        "state": data.get("state"),
        "district": data.get("district") or _value(user, "city"),
        "age": data.get("age") if data.get("age") not in (None, "") else _value(user, "age"),
        "occupation": data.get("occupation"),
        "employment_type": data.get("employment_type"),
        "income_band": data.get("income_band"),
        "government_category": data.get("government_category"),
        "existing_insurer": data.get("existing_insurer"),
        "employer_name": data.get("employer_name"),
        "needs_charitable_support": data.get("needs_charitable_support", False),
        "desired_categories": data.get("desired_categories") or [],
    }


@bp.route("/carefin", methods=("GET", "POST"))
@login_required
def carefin_page():
    result = None
    form_data = {
        "state": request.form.get("state", ""),
        "district": request.form.get("district", ""),
        "age": request.form.get("age", ""),
        "occupation": request.form.get("occupation", ""),
        "income_band": request.form.get("income_band", ""),
        "existing_insurer": request.form.get("existing_insurer", ""),
        "needs_charitable_support": request.form.get("needs_charitable_support") in {"1", "yes", "true", "on"},
    }
    if request.method == "POST":
        action = str(request.form.get("action") or "discover").strip()
        try:
            if action == "discover":
                result = discover_benefits(_context(g.user, request.form))
            elif action == "create_case":
                item = create_carefin_case(
                    g.user,
                    request.form.get("source_id"),
                    note=request.form.get("note"),
                    initial_state=request.form.get("initial_state"),
                )
                audit("create", "carefin_case", str(item["id"]), actor=g.user)
                flash("CareFin case created. ZENDOC will not mark it approved without authoritative evidence.", "success")
                return redirect(url_for("carefin.carefin_page"))
            elif action == "evidence":
                item = submit_case_evidence(
                    g.user,
                    int(request.form.get("case_id") or 0),
                    evidence_type=request.form.get("evidence_type"),
                    evidence_reference=request.form.get("evidence_reference"),
                    note=request.form.get("note"),
                )
                audit("update", "carefin_case", str(item["id"]), actor=g.user)
                flash("Evidence reference saved.", "success")
                return redirect(url_for("carefin.carefin_page"))
            elif action == "request_verification":
                item = request_case_verification(g.user, int(request.form.get("case_id") or 0))
                audit("request", "carefin_verification", str(item["id"]), actor=g.user)
                flash("Verification requested. An authoritative response is still required.", "success")
                return redirect(url_for("carefin.carefin_page"))
            else:
                raise ValueError("Unsupported CareFin action.")
        except (TypeError, ValueError, LookupError, PermissionError) as exc:
            flash(str(exc), "error")

    return render_template(
        "carefin.html",
        result=result,
        form_data=form_data,
        cases=list_carefin_cases(g.user),
        case_options=carefin_case_options(),
    )


@bp.get("/carefin/cases/<int:case_id>/claim-packet.json")
@login_required
def carefin_claim_packet(case_id):
    try:
        packet = build_claim_packet(g.user, case_id)
        response = jsonify(packet)
        response.headers["Content-Disposition"] = f'attachment; filename="zendoc-carefin-case-{case_id}.json"'
        response.headers["Cache-Control"] = "no-store"
        return response
    except PermissionError as exc:
        return jsonify({"error":{"code":403,"message":str(exc)}}),403
    except (TypeError,ValueError,LookupError) as exc:
        return jsonify({"error":{"code":404,"message":str(exc)}}),404


@bp.route("/admin/carefin-cases", methods=("GET", "POST"))
@login_required
@owner_required
def carefin_admin_page():
    if request.method == "POST":
        try:
            item = owner_transition_case(
                g.user,
                int(request.form.get("case_id") or 0),
                target_state=request.form.get("target_state"),
                evidence_type=request.form.get("evidence_type"),
                evidence_reference=request.form.get("evidence_reference"),
                note=request.form.get("note"),
            )
            audit("review", "carefin_case", str(item["id"]), actor=g.user)
            flash("CareFin case state updated with audit evidence.", "success")
        except (TypeError, ValueError, LookupError, PermissionError) as exc:
            flash(str(exc), "error")
        return redirect(url_for("carefin.carefin_admin_page"))

    selected = None
    selected_id = request.args.get("case_id")
    if selected_id:
        try:
            selected = get_carefin_case(g.user, int(selected_id))
        except (TypeError, ValueError, LookupError, PermissionError):
            selected = None
    return render_template(
        "carefin_admin.html",
        cases=list_carefin_cases(g.user, limit=300),
        selected=selected,
        case_options=carefin_case_options(),
    )


@bp.post("/api/v1/carefin/discover")
def api_carefin_discover():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    result = discover_benefits(_context(user, data))
    result["personal_data_source"] = "authenticated_user_plus_explicit_request"
    result["authoritative_coverage_verified"] = False
    return jsonify(result)


@bp.route("/api/v1/carefin/cases", methods=("GET", "POST"))
def api_carefin_cases():
    user, error = require_api_user()
    if error:
        return error
    if request.method == "GET":
        return jsonify({"cases": list_carefin_cases(user)})
    data = request.get_json(silent=True) or {}
    try:
        item = create_carefin_case(
            user,
            data.get("source_id"),
            note=data.get("note"),
            initial_state=data.get("initial_state"),
        )
        return jsonify({"case": item}), 201
    except (TypeError, ValueError, LookupError, PermissionError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400


@bp.post("/api/v1/carefin/cases/<int:case_id>/evidence")
def api_carefin_case_evidence(case_id):
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        item = submit_case_evidence(
            user,
            case_id,
            evidence_type=data.get("evidence_type"),
            evidence_reference=data.get("evidence_reference"),
            note=data.get("note"),
        )
        return jsonify({"case": item})
    except PermissionError as exc:
        return jsonify({"error": {"code": 403, "message": str(exc)}}), 403
    except (TypeError, ValueError, LookupError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400


@bp.post("/api/v1/carefin/cases/<int:case_id>/request-verification")
def api_carefin_case_request_verification(case_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        item = request_case_verification(user, case_id)
        return jsonify({"case": item})
    except PermissionError as exc:
        return jsonify({"error": {"code": 403, "message": str(exc)}}), 403
    except (TypeError, ValueError, LookupError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400


def _value(user, key, default=None):
    if user is None:
        return default
    if hasattr(user, "keys") and key in user.keys():
        return user[key]
    if isinstance(user, dict):
        return user.get(key, default)
    return default



@bp.post("/api/v1/carefin/webhook")
def carefin_partner_webhook():
    raw=request.get_data(cache=True)
    payload=request.get_json(silent=True) or {}
    try:
        item=apply_carefin_partner_response(
            payload,raw,request.headers.get("X-ZENDOC-CareFin-Signature","")
        )
        return jsonify({
            "accepted":True,
            "case_id":item["id"],
            "state":item["state"],
            "authoritative_confirmation":bool(item["authoritative_confirmation"]),
        })
    except PermissionError as exc:
        return jsonify({"error":{"code":403,"message":str(exc)}}),403
    except (TypeError,ValueError,LookupError) as exc:
        return jsonify({"error":{"code":400,"message":str(exc)}}),400
