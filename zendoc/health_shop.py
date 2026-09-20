"""Health-commerce handoffs and referral-attribution readiness.

ZENDOC may record that a user chose to leave for a merchant. It must not claim
affiliate revenue unless a real partner program is configured. Clinical advice,
care ranking and medicine decisions remain independent of commission.
"""
from __future__ import annotations

import os
import uuid
from urllib.parse import quote_plus, urlparse

from .db import get_db, now_iso
from .health_commerce import search_health_products


def ensure_health_shop_schema():
    get_db().executescript(
        """
        CREATE TABLE IF NOT EXISTS health_commerce_clicks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            click_uid TEXT NOT NULL UNIQUE,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            merchant_id TEXT NOT NULL,
            query_text TEXT NOT NULL,
            category TEXT NOT NULL,
            destination_url TEXT NOT NULL,
            affiliate_configured INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_health_commerce_clicks_user
            ON health_commerce_clicks(user_id,created_at);
        CREATE INDEX IF NOT EXISTS idx_health_commerce_clicks_merchant
            ON health_commerce_clicks(merchant_id,created_at);

        CREATE TABLE IF NOT EXISTS health_shop_saved_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            merchant_id TEXT NOT NULL,
            merchant_label TEXT NOT NULL,
            query_text TEXT NOT NULL,
            category TEXT NOT NULL,
            destination_url TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(user_id,merchant_id,query_text,category)
        );
        CREATE INDEX IF NOT EXISTS idx_health_shop_saved_items_user
            ON health_shop_saved_items(user_id,created_at,id);
        """
    )


def _affiliate_template(merchant_id: str) -> str | None:
    key = "ZENDOC_AFFILIATE_" + "".join(ch if ch.isalnum() else "_" for ch in merchant_id.upper()) + "_URL_TEMPLATE"
    value = str(os.environ.get(key) or "").strip()
    return value or None


def affiliate_readiness() -> dict:
    merchant_ids = {
        "amazon_india", "flipkart", "meesho", "blinkit", "bigbasket",
        "zepto", "swiggy_instamart", "zomato", "lenskart", "healthkart",
    }
    configured = sorted(mid for mid in merchant_ids if _affiliate_template(mid))
    return {
        "configured_merchants": configured,
        "affiliate_revenue_claim_allowed": bool(configured),
        "commission_estimation_enabled": False,
        "truth_notice": (
            "Referral tracking is repository-ready, but ZENDOC may claim commission only for merchants "
            "with a real approved partner/affiliate agreement and a configured deep-link template."
        ),
    }


def _format_affiliate_url(template: str, *, destination: str, click_id: str, query: str) -> str:
    try:
        candidate = template.format(
            destination=quote_plus(destination),
            click_id=quote_plus(click_id),
            query=quote_plus(query),
        )
    except Exception as exc:
        raise ValueError("Configured affiliate URL template is invalid.") from exc
    parsed = urlparse(candidate)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Configured affiliate URL must resolve to a valid HTTPS address.")
    return candidate[:3000]


def build_outbound_handoff(user, merchant_id: str, query: str, category: str) -> dict:
    ensure_health_shop_schema()
    result = search_health_products(query, category)
    item = next((row for row in result.get("results", []) if row.get("id") == merchant_id), None)
    if not item:
        raise LookupError("That merchant is not available for this health-product search.")

    click_id = f"hc_{uuid.uuid4().hex}"
    destination = str(item["url"])
    template = _affiliate_template(merchant_id)
    affiliate_configured = bool(template)
    outbound = _format_affiliate_url(
        template, destination=destination, click_id=click_id, query=result["query"]
    ) if template else destination

    get_db().execute(
        """
        INSERT INTO health_commerce_clicks
        (click_uid,user_id,merchant_id,query_text,category,destination_url,affiliate_configured,created_at)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            click_id,
            int(user["id"]) if user else None,
            merchant_id,
            result["query"],
            result["category"],
            destination,
            1 if affiliate_configured else 0,
            now_iso(),
        ),
    )
    get_db().commit()
    return {
        "click_id": click_id,
        "url": outbound,
        "affiliate_configured": affiliate_configured,
        "merchant": item,
        "truth_notice": (
            "This opens an external merchant. ZENDOC does not verify stock, price, seller, delivery or medical suitability."
        ),
    }



def commerce_click_metrics(limit: int = 100) -> dict:
    """Owner-facing outbound attribution metrics; never implies purchase/conversion."""
    ensure_health_shop_schema()
    total = get_db().execute("SELECT COUNT(*) c FROM health_commerce_clicks").fetchone()
    configured = get_db().execute(
        "SELECT COUNT(*) c FROM health_commerce_clicks WHERE affiliate_configured=1"
    ).fetchone()
    unique_users = get_db().execute(
        "SELECT COUNT(DISTINCT user_id) c FROM health_commerce_clicks WHERE user_id IS NOT NULL"
    ).fetchone()
    merchants = get_db().execute(
        """
        SELECT merchant_id,COUNT(*) clicks,
               SUM(CASE WHEN affiliate_configured=1 THEN 1 ELSE 0 END) affiliate_configured_clicks
        FROM health_commerce_clicks
        GROUP BY merchant_id
        ORDER BY clicks DESC,merchant_id ASC
        """
    ).fetchall()
    recent = get_db().execute(
        """
        SELECT id,click_uid,user_id,merchant_id,query_text,category,destination_url,
               affiliate_configured,created_at
        FROM health_commerce_clicks
        ORDER BY created_at DESC,id DESC
        LIMIT ?
        """,
        (max(1, min(int(limit or 100), 500)),),
    ).fetchall()
    return {
        "total_outbound_clicks": int(total["c"] or 0),
        "affiliate_configured_clicks": int(configured["c"] or 0),
        "unique_users": int(unique_users["c"] or 0),
        "merchants": [dict(row) for row in merchants],
        "recent": [dict(row) for row in recent],
        "conversion_tracking": False,
        "revenue_verified": False,
        "truth_notice": (
            "These are ZENDOC outbound-click records only. They do not prove an order, conversion, "
            "commission, merchant settlement, stock availability or price."
        ),
    }



def save_health_shop_item(user, merchant_id: str, query: str, category: str) -> dict:
    """Save a health-product search intent without claiming merchant inventory."""
    ensure_health_shop_schema()
    result = search_health_products(query, category)
    item = next((row for row in result.get("results", []) if row.get("id") == merchant_id), None)
    if not item:
        raise LookupError("That merchant is not available for this health-product search.")
    uid = int(user["id"])
    existing = get_db().execute(
        """
        SELECT * FROM health_shop_saved_items
        WHERE user_id=? AND merchant_id=? AND query_text=? AND category=?
        """,
        (uid, merchant_id, result["query"], result["category"]),
    ).fetchone()
    if existing:
        return dict(existing)
    now = now_iso()
    cursor = get_db().execute(
        """
        INSERT INTO health_shop_saved_items
        (user_id,merchant_id,merchant_label,query_text,category,destination_url,created_at)
        VALUES (?,?,?,?,?,?,?)
        """,
        (
            uid,
            str(item["id"]),
            str(item["label"])[:120],
            result["query"],
            result["category"],
            str(item["url"])[:3000],
            now,
        ),
    )
    get_db().commit()
    row = get_db().execute(
        "SELECT * FROM health_shop_saved_items WHERE id=?",
        (int(cursor.lastrowid),),
    ).fetchone()
    return dict(row)


def list_saved_health_shop_items(user, limit: int = 50) -> list[dict]:
    ensure_health_shop_schema()
    rows = get_db().execute(
        """
        SELECT * FROM health_shop_saved_items
        WHERE user_id=?
        ORDER BY created_at DESC,id DESC
        LIMIT ?
        """,
        (int(user["id"]), max(1, min(int(limit or 50), 200))),
    ).fetchall()
    return [dict(row) for row in rows]


def delete_saved_health_shop_item(user, item_id: int) -> None:
    ensure_health_shop_schema()
    cursor = get_db().execute(
        "DELETE FROM health_shop_saved_items WHERE id=? AND user_id=?",
        (int(item_id), int(user["id"])),
    )
    if int(cursor.rowcount or 0) != 1:
        get_db().rollback()
        raise LookupError("Saved health-shop item not found.")
    get_db().commit()
