"""Owner-managed financial KPI layer for ZENDOC startup operations.

All values are owner-entered bookkeeping/management data. ZENDOC never invents
revenue, funding, cash balance, or runway.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from .db import get_db, now_iso
from .security import assert_owner


ENTRY_TYPES = {"revenue", "cost"}
REVENUE_CATEGORIES = {
    "pilot",
    "subscription",
    "enterprise_contract",
    "api",
    "marketplace",
    "grant",
    "other_revenue",
}
COST_CATEGORIES = {
    "cloud",
    "software",
    "data",
    "legal_compliance",
    "marketing",
    "operations",
    "contractor",
    "salary",
    "travel",
    "other_cost",
}


def create_financial_entry(actor: Any, data: dict) -> dict:
    assert_owner(actor)
    entry_type = str(data.get("entry_type") or "").strip().lower()
    category = str(data.get("category") or "").strip().lower()
    if entry_type not in ENTRY_TYPES:
        raise ValueError("entry_type must be revenue or cost.")
    allowed = REVENUE_CATEGORIES if entry_type == "revenue" else COST_CATEGORIES
    if category not in allowed:
        raise ValueError("Unsupported financial category.")

    amount = float(data.get("amount_inr") or 0)
    if amount < 0:
        raise ValueError("amount_inr must be non-negative.")
    entry_date = str(data.get("entry_date") or date.today().isoformat()).strip()
    _validate_date(entry_date)
    recurring = 1 if _as_bool(data.get("recurring")) else 0
    now = now_iso()

    cursor = get_db().execute(
        """
        INSERT INTO startup_financial_entries
        (entry_uid,entry_date,entry_type,category,amount_inr,recurring,description,source_ref,created_by,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            f"fin_{uuid.uuid4().hex[:20]}",
            entry_date,
            entry_type,
            category,
            amount,
            recurring,
            _clean(data.get("description"), 1000),
            _clean(data.get("source_ref"), 500),
            int(actor["id"]),
            now,
            now,
        ),
    )
    get_db().commit()
    return get_financial_entry(int(cursor.lastrowid))


def create_financial_snapshot(actor: Any, data: dict) -> dict:
    assert_owner(actor)
    month = str(data.get("snapshot_month") or "").strip()
    if not month:
        raise ValueError("snapshot_month is required in YYYY-MM format.")
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError as exc:
        raise ValueError("snapshot_month must use YYYY-MM format.") from exc

    cash = data.get("cash_balance_inr")
    cash_value = None if cash in (None, "") else float(cash)
    if cash_value is not None and cash_value < 0:
        raise ValueError("cash_balance_inr must be non-negative.")

    db = get_db()
    now = now_iso()
    existing = db.execute(
        "SELECT id FROM startup_financial_snapshots WHERE snapshot_month=?",
        (month,),
    ).fetchone()
    if existing:
        db.execute(
            """
            UPDATE startup_financial_snapshots
            SET cash_balance_inr=?,notes=?,created_by=?,updated_at=?
            WHERE id=?
            """,
            (cash_value, _clean(data.get("notes"), 1000), int(actor["id"]), now, int(existing["id"])),
        )
        snapshot_id = int(existing["id"])
    else:
        cursor = db.execute(
            """
            INSERT INTO startup_financial_snapshots
            (snapshot_month,cash_balance_inr,notes,created_by,created_at,updated_at)
            VALUES (?,?,?,?,?,?)
            """,
            (month, cash_value, _clean(data.get("notes"), 1000), int(actor["id"]), now, now),
        )
        snapshot_id = int(cursor.lastrowid)
    db.commit()
    row = db.execute("SELECT * FROM startup_financial_snapshots WHERE id=?", (snapshot_id,)).fetchone()
    return dict(row)


def get_financial_entry(entry_id: int) -> dict:
    row = get_db().execute("SELECT * FROM startup_financial_entries WHERE id=?", (int(entry_id),)).fetchone()
    if not row:
        raise LookupError(f"Financial entry #{entry_id} not found.")
    return dict(row)


def list_financial_entries(actor: Any, *, limit: int = 200) -> list[dict]:
    assert_owner(actor)
    limit = max(1, min(int(limit or 200), 1000))
    rows = get_db().execute(
        "SELECT * FROM startup_financial_entries ORDER BY entry_date DESC,id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def financial_kpis(actor: Any, *, month: str | None = None) -> dict:
    assert_owner(actor)
    db = get_db()
    target_month = str(month or date.today().strftime("%Y-%m"))
    try:
        datetime.strptime(target_month, "%Y-%m")
    except ValueError as exc:
        raise ValueError("month must use YYYY-MM format.") from exc

    rows = db.execute(
        """
        SELECT * FROM startup_financial_entries
        WHERE substr(entry_date,1,7)=?
        ORDER BY entry_date,id
        """,
        (target_month,),
    ).fetchall()

    revenue = sum(float(row["amount_inr"] or 0) for row in rows if row["entry_type"] == "revenue")
    costs = sum(float(row["amount_inr"] or 0) for row in rows if row["entry_type"] == "cost")
    recurring_revenue = sum(
        float(row["amount_inr"] or 0)
        for row in rows
        if row["entry_type"] == "revenue" and int(row["recurring"] or 0) == 1
    )
    recurring_costs = sum(
        float(row["amount_inr"] or 0)
        for row in rows
        if row["entry_type"] == "cost" and int(row["recurring"] or 0) == 1
    )

    snapshot = db.execute(
        """
        SELECT * FROM startup_financial_snapshots
        WHERE snapshot_month<=?
        ORDER BY snapshot_month DESC
        LIMIT 1
        """,
        (target_month,),
    ).fetchone()
    cash_balance = float(snapshot["cash_balance_inr"]) if snapshot and snapshot["cash_balance_inr"] is not None else None

    net_burn = max(0.0, costs - revenue)
    runway = None
    if cash_balance is not None and net_burn > 0:
        runway = round(cash_balance / net_burn, 2)

    return {
        "month": target_month,
        "revenue_inr": round(revenue, 2),
        "recurring_revenue_inr": round(recurring_revenue, 2),
        "costs_inr": round(costs, 2),
        "recurring_costs_inr": round(recurring_costs, 2),
        "net_cash_flow_inr": round(revenue - costs, 2),
        "net_burn_inr": round(net_burn, 2),
        "cash_balance_inr": round(cash_balance, 2) if cash_balance is not None else None,
        "runway_months": runway,
        "entry_count": len(rows),
        "truth_notice": (
            "These KPIs are calculated only from owner-entered financial entries and cash snapshots. "
            "They are management metrics, not audited financial statements."
        ),
    }


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _clean(value: Any, limit: int) -> str | None:
    text = str(value or "").strip()
    return text[:limit] or None


def _validate_date(value: str) -> None:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("entry_date must use YYYY-MM-DD format.") from exc
