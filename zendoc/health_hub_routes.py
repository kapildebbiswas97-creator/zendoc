"""Health Hub web/API routes for education, child continuity and commerce handoffs."""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from .health_commerce import commerce_category_catalog, commerce_ethics_policy, search_health_products
from .health_hub import (
    child_development_plan,
    creator_platform_readiness,
    engagement_policy,
    genomics_readiness,
    health_content_catalog,
)
from .routes import require_api_user
from .security import login_required
from .video_provider import configured_video_provider


bp = Blueprint("health_hub", __name__)


def _video_result(topic):
    topic = " ".join(str(topic or "").strip().split())[:200]
    if not topic:
        return {
            "available": False,
            "provider": "none",
            "query": "",
            "results": [],
            "search_url": None,
            "reason": "Choose a health-education topic to search.",
        }
    return configured_video_provider().search(topic, max_results=6)


def _hub_payload(*, topic="", product_query="", product_category="general_wellness", child_age=None):
    return {
        "content_lanes": health_content_catalog(),
        "engagement": engagement_policy(),
        "creator": creator_platform_readiness(),
        "genomics": genomics_readiness(),
        "child": child_development_plan(child_age),
        "commerce_categories": commerce_category_catalog(),
        "commerce_policy": commerce_ethics_policy(),
        "videos": _video_result(topic),
        "products": search_health_products(product_query, product_category),
    }


@bp.get("/health-hub")
@login_required
def health_hub_page():
    topic = request.args.get("topic", "")
    product_query = request.args.get("product_q", "")
    product_category = request.args.get("product_category", "general_wellness")
    child_age = request.args.get("child_age")
    payload = _hub_payload(
        topic=topic,
        product_query=product_query,
        product_category=product_category,
        child_age=child_age,
    )
    return render_template(
        "health_hub.html",
        topic=topic,
        product_query=product_query,
        product_category=product_category,
        child_age=child_age or "",
        **payload,
    )


@bp.get("/api/v1/health-hub")
def api_health_hub():
    user, error = require_api_user()
    if error:
        return error
    payload = _hub_payload(
        topic=request.args.get("topic", ""),
        product_query=request.args.get("product_q", ""),
        product_category=request.args.get("product_category", "general_wellness"),
        child_age=request.args.get("child_age"),
    )
    return jsonify({"health_hub": payload, "user_id": int(user["id"])})
