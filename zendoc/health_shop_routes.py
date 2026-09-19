"""Dedicated B2C health-shop discovery and outbound attribution routes."""
from flask import Blueprint, g, jsonify, redirect, render_template, request

from .health_commerce import commerce_category_catalog, commerce_ethics_policy, search_health_products
from .health_shop import affiliate_readiness, build_outbound_handoff
from .routes import require_api_user
from .security import login_required

bp = Blueprint("health_shop", __name__)


@bp.get("/health-shop")
@login_required
def health_shop_page():
    query = request.args.get("q", "")
    category = request.args.get("category", "general_wellness")
    products = search_health_products(query, category)
    return render_template(
        "health_shop.html",
        q=query,
        selected_category=category,
        categories=commerce_category_catalog(),
        products=products,
        ethics=commerce_ethics_policy(),
        affiliate=affiliate_readiness(),
    )


@bp.get("/health-shop/out/<merchant_id>")
@login_required
def outbound(merchant_id):
    handoff = build_outbound_handoff(
        g.user,
        merchant_id,
        request.args.get("q", ""),
        request.args.get("category", "general_wellness"),
    )
    return redirect(handoff["url"])


@bp.get("/api/v1/health-shop/search")
def api_health_shop_search():
    user, error = require_api_user()
    if error:
        return error
    products = search_health_products(
        request.args.get("q", ""),
        request.args.get("category", "general_wellness"),
    )
    return jsonify({
        "products": products,
        "affiliate": affiliate_readiness(),
        "user_id": int(user["id"]),
    })
