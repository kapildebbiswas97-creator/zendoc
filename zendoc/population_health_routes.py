"""
ZENDOC Population & Public Health OS Routes.
Manages cohorts, aggregate analytics, public health campaigns, and enrollment.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from .population_health_os import (
    create_health_cohort,
    create_public_health_campaign,
    enroll_patient_in_campaign,
    enroll_patient_in_cohort,
    get_campaign_analytics,
    get_cohort_aggregate_analytics,
    list_campaigns,
    list_cohort_members,
    list_cohorts,
)
from .routes import require_api_user

bp = Blueprint("population_health", __name__)


# ── Cohort Endpoints ────────────────────────────────────────────────────────

@bp.post("/api/v1/population/cohorts")
def api_create_cohort():
    user, error = require_api_user()
    if error:
        return error

    data = request.get_json(silent=True) or {}
    name = data.get("name")
    inclusion_criteria = data.get("inclusion_criteria") or {}
    description = data.get("description")

    try:
        cohort = create_health_cohort(
            actor=user,
            name=name,
            inclusion_criteria=inclusion_criteria,
            description=description,
        )
        return jsonify(cohort), 201
    except ValueError as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
    except PermissionError as exc:
        return jsonify({"error": {"code": 403, "message": str(exc)}}), 403


@bp.get("/api/v1/population/cohorts")
def api_list_cohorts():
    user, error = require_api_user()
    if error:
        return error

    try:
        cohorts = list_cohorts(actor=user)
        return jsonify({"cohorts": cohorts, "count": len(cohorts)})
    except PermissionError as exc:
        return jsonify({"error": {"code": 403, "message": str(exc)}}), 403


@bp.post("/api/v1/population/cohorts/<cohort_uid>/enroll")
def api_enroll_cohort(cohort_uid: str):
    user, error = require_api_user()
    if error:
        return error

    data = request.get_json(silent=True) or {}
    patient_id = data.get("patient_id")
    enrollment_reason = data.get("enrollment_reason")
    if not patient_id:
        return jsonify({"error": {"code": 400, "message": "patient_id is required."}}), 400

    try:
        result = enroll_patient_in_cohort(
            actor=user,
            cohort_uid=cohort_uid,
            patient_id=int(patient_id),
            enrollment_reason=enrollment_reason,
        )
        return jsonify(result), 200
    except LookupError as exc:
        return jsonify({"error": {"code": 404, "message": str(exc)}}), 404
    except ValueError as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
    except PermissionError as exc:
        return jsonify({"error": {"code": 403, "message": str(exc)}}), 403


@bp.get("/api/v1/population/cohorts/<cohort_uid>/members")
def api_list_cohort_members(cohort_uid: str):
    user, error = require_api_user()
    if error:
        return error

    try:
        members = list_cohort_members(actor=user, cohort_uid=cohort_uid)
        return jsonify({"members": members, "count": len(members)})
    except LookupError as exc:
        return jsonify({"error": {"code": 404, "message": str(exc)}}), 404
    except PermissionError as exc:
        return jsonify({"error": {"code": 403, "message": str(exc)}}), 403


@bp.get("/api/v1/population/cohorts/<cohort_uid>/analytics")
def api_cohort_analytics(cohort_uid: str):
    user, error = require_api_user()
    if error:
        return error

    try:
        analytics = get_cohort_aggregate_analytics(actor=user, cohort_uid=cohort_uid)
        return jsonify(analytics), 200
    except LookupError as exc:
        return jsonify({"error": {"code": 404, "message": str(exc)}}), 404
    except PermissionError as exc:
        return jsonify({"error": {"code": 403, "message": str(exc)}}), 403


# ── Public Health Campaign Endpoints ────────────────────────────────────────

@bp.post("/api/v1/population/campaigns")
def api_create_campaign():
    user, error = require_api_user()
    if error:
        return error

    data = request.get_json(silent=True) or {}
    try:
        campaign = create_public_health_campaign(
            actor=user,
            title=data.get("title"),
            campaign_type=data.get("campaign_type"),
            start_date=data.get("start_date"),
            target_condition=data.get("target_condition"),
            target_population=data.get("target_population"),
            geographic_scope=data.get("geographic_scope"),
            end_date=data.get("end_date"),
            content=data.get("content"),
        )
        return jsonify(campaign), 201
    except ValueError as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
    except PermissionError as exc:
        return jsonify({"error": {"code": 403, "message": str(exc)}}), 403


@bp.get("/api/v1/population/campaigns")
def api_list_campaigns():
    status = request.args.get("status")
    campaigns = list_campaigns(status=status)
    return jsonify({"campaigns": campaigns, "count": len(campaigns)})


@bp.post("/api/v1/population/campaigns/<campaign_uid>/enroll")
def api_enroll_campaign(campaign_uid: str):
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

    try:
        result = enroll_patient_in_campaign(
            actor=user,
            campaign_uid=campaign_uid,
            patient_id=int(patient_id),
        )
        return jsonify(result), 200
    except LookupError as exc:
        return jsonify({"error": {"code": 404, "message": str(exc)}}), 404
    except ValueError as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
    except PermissionError as exc:
        return jsonify({"error": {"code": 403, "message": str(exc)}}), 403


@bp.get("/api/v1/population/campaigns/<campaign_uid>/analytics")
def api_campaign_analytics(campaign_uid: str):
    user, error = require_api_user()
    if error:
        return error

    try:
        analytics = get_campaign_analytics(actor=user, campaign_uid=campaign_uid)
        return jsonify(analytics), 200
    except LookupError as exc:
        return jsonify({"error": {"code": 404, "message": str(exc)}}), 404
    except PermissionError as exc:
        return jsonify({"error": {"code": 403, "message": str(exc)}}), 403
