"""Authenticated CareFin API routes."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from .carefin_engine import discover_benefits
from .routes import require_api_user


bp = Blueprint("carefin", __name__)


@bp.post("/api/v1/carefin/discover")
def api_carefin_discover():
    user, error = require_api_user()
    if error:
        return error

    data = request.get_json(silent=True) or {}
    context = {
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
    result = discover_benefits(context)
    result["personal_data_source"] = "authenticated_user_plus_explicit_request"
    result["authoritative_coverage_verified"] = False
    return jsonify(result)


def _value(user, key, default=None):
    if user is None:
        return default
    if hasattr(user, "keys") and key in user.keys():
        return user[key]
    if isinstance(user, dict):
        return user.get(key, default)
    return default
