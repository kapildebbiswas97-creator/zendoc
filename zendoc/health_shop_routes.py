"""Dedicated B2C health-shop discovery and outbound attribution routes."""
from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, url_for

from .health_commerce import commerce_category_catalog, commerce_ethics_policy, search_health_products
from .health_shop import (
    affiliate_readiness,
    build_outbound_handoff,
    commerce_click_metrics,
    delete_saved_health_shop_item,
    list_saved_health_shop_items,
    save_health_shop_item,
)
from .routes import require_api_user
from .security import login_required, owner_required

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
        selected_category=products["category"],
        categories=commerce_category_catalog(),
        products=products,
        ethics=commerce_ethics_policy(),
        affiliate=affiliate_readiness(),
        saved_items=list_saved_health_shop_items(g.user),
    )


@bp.post("/health-shop/save")
@login_required
def save_health_shop_item_route():
    try:
        item = save_health_shop_item(
            g.user,
            request.form.get("merchant_id"),
            request.form.get("q", ""),
            request.form.get("category", "general_wellness"),
        )
        flash(f"Saved {item['query_text']} for later shopping.", "success")
    except (ValueError, LookupError, PermissionError) as exc:
        flash(str(exc), "error")
    return redirect(url_for(
        "health_shop.health_shop_page",
        q=request.form.get("q", ""),
        category=request.form.get("category", "general_wellness"),
    ))


@bp.post("/health-shop/saved/<int:item_id>/delete")
@login_required
def delete_saved_health_shop_item_route(item_id):
    try:
        delete_saved_health_shop_item(g.user, item_id)
        flash("Removed from your Saved Health List.", "success")
    except (ValueError, LookupError, PermissionError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("health_shop.health_shop_page"))


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



@bp.get("/admin/commerce-referrals")
@login_required
@owner_required
def health_shop_admin_page():
    return render_template(
        "health_shop_admin.html",
        metrics=commerce_click_metrics(),
        affiliate=affiliate_readiness(),
    )
