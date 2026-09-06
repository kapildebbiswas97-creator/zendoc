"""Authenticated NutritionAgent API routes."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from .nutrition_agent import compare_products, hydration_guidance
from .routes import require_api_user


bp = Blueprint("nutrition_intelligence", __name__)


@bp.post("/api/v1/nutrition/compare")
def api_nutrition_compare():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        result = compare_products(
            data.get("products") or [],
            goal=str(data.get("goal") or "general_wellness"),
            allergens=data.get("allergens") or [],
        )
    except ValueError as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
    result["patient_specific_clinical_advice"] = False
    return jsonify(result)


@bp.post("/api/v1/nutrition/hydration")
def api_hydration_guidance():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    return jsonify(
        hydration_guidance(
            activity_minutes=data.get("activity_minutes"),
            high_heat=bool(data.get("high_heat", False)),
            medical_condition=bool(data.get("medical_condition", False)),
        )
    )
