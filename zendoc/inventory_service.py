"""
ZENDOC Hyperlocal Inventory Truth Engine — Milestone 10
Truthful local inventory observations, freshness evaluation, digitalization levels,
and real distance calculation.

INVENTORY TRUTH STATES:
- CONFIRMED: Observed recently (fresh within threshold) and quantity > 0
- STALE: Last update is older than freshness threshold; cannot be presented as reliable
- UNKNOWN: No stock observation exists for this SKU; never fabricated into "In Stock"
- UNAVAILABLE: Provider explicitly confirmed 0 stock or discontinued

DIGITALIZATION LEVELS:
- LEVEL 1: Manual web updates
- LEVEL 2: CSV / Catalog batch import
- LEVEL 3: POS webhook sync
- LEVEL 4: Partner real-time API
"""
from __future__ import annotations

import csv
import io
import json
import math
from datetime import datetime, timezone
from typing import Any

from .db import get_db, now_iso

DEFAULT_STALE_THRESHOLD_HOURS = 2.0


def calculate_distance_km(
    lat1: float | None,
    lon1: float | None,
    lat2: float | None,
    lon2: float | None,
) -> float | None:
    """
    Calculate geodesic distance in kilometers between two points using the Haversine formula.
    Never fabricates distance: returns None if either coordinate pair is missing.
    """
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return None
    try:
        lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
    except (ValueError, TypeError):
        return None

    # Earth radius in kilometers
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 1)


def evaluate_freshness(
    observed_at_iso: str | None,
    current_status: str = "CONFIRMED",
    stale_hours: float = DEFAULT_STALE_THRESHOLD_HOURS,
) -> tuple[str, str]:
    """
    Evaluate stock freshness.
    Returns tuple: (effective_status, human_freshness_label)
    e.g. ('CONFIRMED', 'Updated 6 minutes ago') or ('STALE', 'Updated 18 hours ago')
    """
    if not observed_at_iso:
        return "UNKNOWN", "Stock unconfirmed"

    try:
        obs_dt = datetime.fromisoformat(observed_at_iso.replace("Z", "+00:00"))
        now_dt = datetime.now(timezone.utc)
        diff = now_dt - obs_dt
        total_seconds = max(0, diff.total_seconds())
    except Exception:
        return "UNKNOWN", "Invalid observation timestamp"

    minutes = int(total_seconds // 60)
    hours = total_seconds / 3600.0

    if minutes < 1:
        label = "Updated just now"
    elif minutes < 60:
        label = f"Updated {minutes} minute{'s' if minutes != 1 else ''} ago"
    elif hours < 24:
        h = int(hours)
        label = f"Updated {h} hour{'s' if h != 1 else ''} ago"
    else:
        days = int(hours // 24)
        label = f"Updated {days} day{'s' if days != 1 else ''} ago"

    if current_status == "UNAVAILABLE":
        return "UNAVAILABLE", label

    if hours > stale_hours:
        return "STALE", label

    return "CONFIRMED", label


def update_inventory_observation(
    pharmacy_id: int,
    sku_id: int,
    quantity: int,
    price_inr: float,
    stock_status: str = "CONFIRMED",
    source: str = "pharmacy_manual",
    discount_percent: float = 0.0,
    notes: str | None = None,
    data_mode: str = "LIVE",
) -> dict[str, Any]:
    """
    Digitalization Level 1 (Manual) or single update:
    Record a verified stock observation for a specific medicine SKU.
    """
    db = get_db()
    now = now_iso()
    price_inr = round(float(price_inr), 2)
    quantity = max(0, int(quantity))
    if quantity == 0 and stock_status == "CONFIRMED":
        stock_status = "UNAVAILABLE"

    cursor = db.execute(
        """
        INSERT INTO inventory_observations
        (pharmacy_id, sku_id, stock_status, quantity_available, price_inr, discount_percent, source, observed_at, notes, data_mode, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(pharmacy_id, sku_id) DO UPDATE SET
            stock_status=excluded.stock_status,
            quantity_available=excluded.quantity_available,
            price_inr=excluded.price_inr,
            discount_percent=excluded.discount_percent,
            source=excluded.source,
            observed_at=excluded.observed_at,
            notes=excluded.notes,
            updated_at=excluded.updated_at
        """,
        (pharmacy_id, sku_id, stock_status, quantity, price_inr, discount_percent, source, now, notes, data_mode, now, now),
    )
    db.commit()

    row = db.execute(
        "SELECT * FROM inventory_observations WHERE pharmacy_id=? AND sku_id=?",
        (pharmacy_id, sku_id),
    ).fetchone()
    return dict(row)


def import_inventory_csv(pharmacy_id: int, csv_content: str) -> dict[str, Any]:
    """
    Digitalization Level 2:
    Batch import inventory via CSV formatted with headers:
    sku_code,quantity,price_inr,in_stock
    """
    db = get_db()
    reader = csv.DictReader(io.StringIO(csv_content.strip()))
    success_count = 0
    errors = []

    for idx, row in enumerate(reader, start=2):
        sku_code = str(row.get("sku_code") or "").strip().upper()
        if not sku_code:
            errors.append(f"Row {idx}: missing sku_code")
            continue

        sku = db.execute("SELECT id, name FROM medication_skus WHERE UPPER(sku_code)=?", (sku_code,)).fetchone()
        if not sku:
            errors.append(f"Row {idx}: unknown sku_code '{sku_code}'")
            continue

        try:
            qty = int(row.get("quantity") or 0)
            price = float(row.get("price_inr") or 0.0)
            in_stock = str(row.get("in_stock", "1")).strip().lower() in {"1", "true", "yes"}
            status = "CONFIRMED" if (in_stock and qty > 0) else "UNAVAILABLE"
        except (ValueError, TypeError) as e:
            errors.append(f"Row {idx}: invalid numbers ({e})")
            continue

        update_inventory_observation(
            pharmacy_id=pharmacy_id,
            sku_id=sku["id"],
            quantity=qty,
            price_inr=price,
            stock_status=status,
            source="csv_import",
        )
        success_count += 1

    # Upgrade pharmacy digitalization level if needed
    db.execute(
        "UPDATE provider_profiles SET digitalization_level=MAX(digitalization_level, 2) WHERE user_id=?",
        (pharmacy_id,),
    )
    db.commit()

    return {
        "success": True,
        "records_imported": success_count,
        "errors": errors,
    }


def search_pharmacy_offers(
    medicine_ids: list[int] | str | None = None,
    city: str | None = None,
    user_lat: float | None = None,
    user_lon: float | None = None,
    radius_km: float = 10.0,
    include_demo: bool = True,
    query: str | None = None,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """
    Query nearby participating pharmacies and return truthful stock observations for the requested SKUs.
    Separates demands from offers; calculates real distance and freshness.
    """
    db = get_db()
    if isinstance(medicine_ids, str):
        query = medicine_ids
        medicine_ids = None

    if "patient_lat" in kwargs and user_lat is None:
        user_lat = kwargs.get("patient_lat")
    if "patient_lon" in kwargs and user_lon is None:
        user_lon = kwargs.get("patient_lon")

    if query and not medicine_ids:
        q_term = f"%{query.strip().lower()}%"
        sku_rows = db.execute(
            "SELECT id FROM medication_skus WHERE LOWER(name) LIKE ? OR LOWER(generic_name) LIKE ?",
            (q_term, q_term),
        ).fetchall()
        medicine_ids = [r["id"] for r in sku_rows]

    where_clauses = ["u.role='pharmacy'", "u.active=1"]
    params: list[Any] = []

    if not include_demo:
        where_clauses.append("pp.data_mode != 'DEMO'")

    if city:
        where_clauses.append("(LOWER(pp.city) LIKE ? OR LOWER(u.city) LIKE ?)")
        city_term = f"%{city.strip().lower()}%"
        params.extend([city_term, city_term])

    where_sql = " AND ".join(where_clauses)
    pharmacy_rows = db.execute(
        f"""
        SELECT pp.*, u.id pharmacy_user_id, u.name pharmacy_name, u.phone pharmacy_phone, u.city user_city
        FROM users u
        LEFT JOIN provider_profiles pp ON pp.user_id=u.id
        WHERE {where_sql}
        ORDER BY pp.verification_status DESC, u.name ASC
        """,
        params,
    ).fetchall()

    results = []
    for pr in pharmacy_rows:
        pharm = dict(pr)
        pharm_uid = pharm.get("user_id") or pharm.get("pharmacy_user_id")
        pharm["user_id"] = pharm_uid
        dist = calculate_distance_km(user_lat, user_lon, pharm.get("latitude"), pharm.get("longitude"))
        if dist is not None and dist > radius_km:
            continue  # Out of radius

        # Fetch inventory for this pharmacy
        sku_filter = ""
        inv_params: list[Any] = [pharm_uid]
        if medicine_ids:
            placeholders = ",".join("?" for _ in medicine_ids)
            sku_filter = f" AND io.sku_id IN ({placeholders})"
            inv_params.extend(medicine_ids)

        observations = db.execute(
            f"""
            SELECT io.*, ms.sku_code, ms.name medicine_name, ms.form, ms.strength, ms.mrp_inr, ms.rx_required
            FROM inventory_observations io
            JOIN medication_skus ms ON ms.id=io.sku_id
            WHERE io.pharmacy_id=? {sku_filter}
            """,
            inv_params,
        ).fetchall()

        items_map = {}
        for obs in observations:
            o_dict = dict(obs)
            eff_status, freshness_label = evaluate_freshness(o_dict.get("observed_at"), o_dict.get("stock_status", "CONFIRMED"))
            o_dict["effective_status"] = eff_status
            o_dict["freshness_label"] = freshness_label
            items_map[o_dict["sku_id"]] = o_dict

        if medicine_ids and not items_map:
            continue

        pharm["distance_km"] = dist
        pharm["distance_text"] = f"{dist} km" if dist is not None else "Distance unavailable"
        pharm["inventory"] = items_map
        if items_map:
            first_item = next(iter(items_map.values()))
            pharm["effective_status"] = first_item["effective_status"]
            pharm["stock_status"] = first_item["stock_status"]
            pharm["freshness_label"] = first_item["freshness_label"]
        else:
            pharm["effective_status"] = "UNKNOWN"
            pharm["stock_status"] = "UNKNOWN"
            pharm["freshness_label"] = "Stock unconfirmed"

        results.append(pharm)

    return results