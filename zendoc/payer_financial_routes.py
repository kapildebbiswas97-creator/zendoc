"""
ZENDOC Payer & Financial OS Routes.
Handles insurance coverage verification, prior authorization requests,
and non-binding patient benefit estimation.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from .payer_financial_os import (
    estimate_patient_benefit,
    list_coverage_requests,
    list_prior_authorizations,
    record_prior_auth_decision,
    submit_coverage_verification_request,
    submit_prior_authorization,
    update_coverage_request_status,
)
from .routes import require_api_user

bp = Blueprint("payer_financial", __name__)


@bp.post("/api/v1/payer/coverage/verify")
def api_submit_coverage_request():
    user, error = require_api_user()
    if error:
        return error

    data = request.get_json(silent=True) or {}
    patient_id = data.get("patient_id")
    if not patient_id:
        if user["role"] == "patient":
            patient_id = user["id"]
        else:
            return jsonify({"error": {"code": 400, "message": "patient_id is required."}}), 400

    insurer_name = data.get("insurer_name")
    coverage_type = data.get("coverage_type")
    service_type = data.get("service_type")
    policy_number = data.get("policy_number")
    estimated_cost_inr = data.get("estimated_cost_inr")

    try:
        result = submit_coverage_verification_request(
            actor=user,
            patient_id=int(patient_id),
            insurer_name=insurer_name,
            coverage_type=coverage_type,
            service_type=service_type,
            policy_number=policy_number,
            estimated_cost_inr=float(estimated_cost_inr) if estimated_cost_inr is not None else None,
        )
        return jsonify(result), 201
    except (ValueError, LookupError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
    except PermissionError as exc:
        return jsonify({"error": {"code": 403, "message": str(exc)}}), 403


@bp.get("/api/v1/payer/coverage/requests")
def api_list_coverage_requests():
    user, error = require_api_user()
    if error:
        return error

    patient_id = request.args.get("patient_id")
    if not patient_id:
        if user["role"] == "patient":
            patient_id = user["id"]
        else:
            return jsonify({"error": {"code": 400, "message": "patient_id query param is required."}}), 400

    try:
        results = list_coverage_requests(actor=user, patient_id=int(patient_id))
        return jsonify({"coverage_requests": results, "count": len(results)})
    except PermissionError as exc:
        return jsonify({"error": {"code": 403, "message": str(exc)}}), 403


@bp.post("/api/v1/payer/coverage/requests/<request_uid>/status")
def api_update_coverage_status(request_uid: str):
    user, error = require_api_user()
    if error:
        return error

    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    verification_notes = data.get("verification_notes")
    response_data = data.get("response_data")

    try:
        result = update_coverage_request_status(
            actor=user,
            request_uid=request_uid,
            new_status=new_status,
            verification_notes=verification_notes,
            response_data=response_data,
        )
        return jsonify(result), 200
    except LookupError as exc:
        return jsonify({"error": {"code": 404, "message": str(exc)}}), 404
    except ValueError as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
    except PermissionError as exc:
        return jsonify({"error": {"code": 403, "message": str(exc)}}), 403


@bp.post("/api/v1/payer/prior-auth/submit")
def api_submit_prior_auth():
    user, error = require_api_user()
    if error:
        return error

    data = request.get_json(silent=True) or {}
    patient_id = data.get("patient_id")
    if not patient_id:
        return jsonify({"error": {"code": 400, "message": "patient_id is required."}}), 400

    try:
        result = submit_prior_authorization(
            actor=user,
            patient_id=int(patient_id),
            insurer_name=data.get("insurer_name"),
            treatment_type=data.get("treatment_type"),
            policy_number=data.get("policy_number"),
            icd10_codes=data.get("icd10_codes"),
            cpt_codes=data.get("cpt_codes"),
            requesting_provider=data.get("requesting_provider"),
            clinical_notes=data.get("clinical_notes"),
        )
        return jsonify(result), 201
    except (ValueError, LookupError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
    except PermissionError as exc:
        return jsonify({"error": {"code": 403, "message": str(exc)}}), 403


@bp.get("/api/v1/payer/prior-auth/requests")
def api_list_prior_auths():
    user, error = require_api_user()
    if error:
        return error

    patient_id = request.args.get("patient_id")
    if not patient_id:
        if user["role"] == "patient":
            patient_id = user["id"]
        else:
            return jsonify({"error": {"code": 400, "message": "patient_id query param is required."}}), 400

    try:
        results = list_prior_authorizations(actor=user, patient_id=int(patient_id))
        return jsonify({"prior_authorizations": results, "count": len(results)})
    except PermissionError as exc:
        return jsonify({"error": {"code": 403, "message": str(exc)}}), 403


@bp.post("/api/v1/payer/prior-auth/requests/<request_uid>/decision")
def api_record_prior_auth_decision(request_uid: str):
    user, error = require_api_user()
    if error:
        return error

    data = request.get_json(silent=True) or {}
    decision = data.get("decision")
    payer_response = data.get("payer_response")
    payer_auth_number = data.get("payer_auth_number")

    try:
        result = record_prior_auth_decision(
            actor=user,
            request_uid=request_uid,
            decision=decision,
            payer_response=payer_response,
            payer_auth_number=payer_auth_number,
        )
        return jsonify(result), 200
    except LookupError as exc:
        return jsonify({"error": {"code": 404, "message": str(exc)}}), 404
    except ValueError as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
    except PermissionError as exc:
        return jsonify({"error": {"code": 403, "message": str(exc)}}), 403


@bp.post("/api/v1/payer/benefits/estimate")
def api_estimate_benefits():
    user, error = require_api_user()
    if error:
        return error

    data = request.get_json(silent=True) or {}
    patient_id = data.get("patient_id")
    if not patient_id:
        if user["role"] == "patient":
            patient_id = user["id"]
        else:
            return jsonify({"error": {"code": 400, "message": "patient_id is required."}}), 400

    service_type = data.get("service_type")
    estimated_cost_inr = data.get("estimated_cost_inr")
    estimated_coverage_pct = data.get("estimated_coverage_pct")
    calculation_basis = data.get("calculation_basis") or "ILLUSTRATIVE_EXAMPLE"

    try:
        result = estimate_patient_benefit(
            actor=user,
            patient_id=int(patient_id),
            service_type=service_type,
            estimated_cost_inr=float(estimated_cost_inr) if estimated_cost_inr is not None else 0.0,
            estimated_coverage_pct=float(estimated_coverage_pct) if estimated_coverage_pct is not None else 0.0,
            calculation_basis=calculation_basis,
        )
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
    except PermissionError as exc:
        return jsonify({"error": {"code": 403, "message": str(exc)}}), 403
