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
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

from flask import current_app

from .db import get_db, now_iso

DEFAULT_STALE_THRESHOLD_HOURS = 2.0
VALID_STOCK_STATUSES = {"CONFIRMED", "STALE", "UNKNOWN", "UNAVAILABLE"}
VALID_INVENTORY_SOURCES = {"pharmacy_manual", "csv_import", "pos_integration", "partner_api"}
VALID_DATA_MODES = {"LIVE", "DEMO"}


def _data_mode(explicit: str | None = None) -> str:
    """Resolve an explicit/live/demo boundary; never mix modes implicitly."""
    if explicit is not None:
        mode = str(explicit).strip().upper()
    else:
        try:
            mode = str(current_app.config.get("CONNECTED_CARE_DATA_MODE", "LIVE")).strip().upper()
        except RuntimeError:
            mode = str(os.environ.get("ZENDOC_CONNECTED_CARE_DATA_MODE", "LIVE")).strip().upper()
    if mode not in VALID_DATA_MODES:
        raise ValueError("Connected Care data mode must be LIVE or DEMO.")
    return mode


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

    status = str(current_status or "UNKNOWN").strip().upper()
    if status == "UNAVAILABLE":
        return "UNAVAILABLE", label

    if status in {"UNKNOWN", "PENDING", "INTEGRATION_REQUIRED", "STALE"}:
        # A caller cannot promote a provider's stale/unknown state merely by
        # supplying a recent timestamp.  Stale is a warning state until a new
        # confirmed observation is written.
        return "STALE" if status == "STALE" else "UNKNOWN", label

    if hours > stale_hours:
        return "STALE", label

    return "CONFIRMED" if status == "CONFIRMED" else "UNKNOWN", label


def update_inventory_observation(
    pharmacy_id: int,
    sku_id: int,
    quantity: int,
    price_inr: float | None,
    stock_status: str = "CONFIRMED",
    source: str = "pharmacy_manual",
    discount_percent: float = 0.0,
    notes: str | None = None,
    data_mode: str | None = None,
) -> dict[str, Any]:
    """
    Digitalization Level 1 (Manual) or single update:
    Record a verified stock observation for a specific medicine SKU.
    """
    mode = _data_mode(data_mode)
    db = get_db()
    pharmacy = db.execute(
        "SELECT id, role, active FROM users WHERE id=?", (int(pharmacy_id),)
    ).fetchone()
    if not pharmacy or pharmacy["role"] != "pharmacy" or not bool(pharmacy["active"]):
        raise PermissionError("Inventory can only be recorded for an active pharmacy account.")
    sku = db.execute("SELECT id FROM medication_skus WHERE id=?", (int(sku_id),)).fetchone()
    if not sku:
        raise LookupError(f"Medication SKU #{sku_id} not found.")
    stock_status = str(stock_status or "UNKNOWN").strip().upper()
    if stock_status not in VALID_STOCK_STATUSES:
        raise ValueError(f"Unsupported inventory status '{stock_status}'.")
    source = str(source or "pharmacy_manual").strip().lower()
    if source not in VALID_INVENTORY_SOURCES:
        raise ValueError(f"Unsupported inventory source '{source}'.")
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        raise ValueError("Inventory quantity must be a non-negative integer.")
    if quantity < 0:
        raise ValueError("Inventory quantity must be non-negative.")
    if price_inr is None or str(price_inr).strip() == "":
        stored_price = 0.0
        price_available = 0
    else:
        try:
            stored_price = round(float(price_inr), 2)
        except (TypeError, ValueError):
            raise ValueError("Inventory price must be a non-negative number or null when unavailable.")
        if not math.isfinite(stored_price) or stored_price < 0:
            raise ValueError("Inventory price must be a non-negative number or null when unavailable.")
        price_available = 1
    if stock_status == "CONFIRMED" and quantity == 0:
        stock_status = "UNAVAILABLE"
    if stock_status == "UNAVAILABLE":
        quantity = 0
    now = now_iso()

    existing = db.execute(
        "SELECT id, data_mode FROM inventory_observations WHERE pharmacy_id=? AND sku_id=? AND data_mode=?",
        (pharmacy_id, sku_id, mode),
    ).fetchone()
    values = (stock_status, quantity, stored_price, price_available, discount_percent, source, now, notes, mode, now, pharmacy_id, sku_id)
    if existing:
        db.execute(
            """
            UPDATE inventory_observations
            SET stock_status=?, quantity_available=?, price_inr=?, price_available=?,
                discount_percent=?, source=?, observed_at=?, notes=?, data_mode=?, updated_at=?
            WHERE pharmacy_id=? AND sku_id=? AND data_mode=?
            """,
            (*values, mode),
        )
    else:
        try:
            db.execute(
                """
                INSERT INTO inventory_observations
                (pharmacy_id, sku_id, stock_status, quantity_available, price_inr, price_available,
                 discount_percent, source, observed_at, notes, data_mode, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (pharmacy_id, sku_id, stock_status, quantity, stored_price, price_available,
                 discount_percent, source, now, notes, mode, now, now),
            )
        except sqlite3.IntegrityError as exc:
            # A database created before the data-mode migration has a
            # (pharmacy_id, sku_id) uniqueness constraint.  Refuse to overwrite
            # another mode; never let a demo update mutate live data silently.
            raise ValueError(
                "Inventory data-mode isolation is not available in this database; run the M10 schema migration before recording this observation."
            ) from exc
    db.commit()

    row = db.execute(
        "SELECT * FROM inventory_observations WHERE pharmacy_id=? AND sku_id=? AND data_mode=?",
        (pharmacy_id, sku_id, mode),
    ).fetchone()
    result = dict(row)
    result["price_inr"] = float(result["price_inr"]) if result.get("price_available", 1) else None
    result["data_mode"] = mode
    return result


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
            raw_price = row.get("price_inr")
            if raw_price in (None, ""):
                errors.append(f"Row {idx}: price_inr is required for an inventory offer (use a separate unknown state instead).")
                continue
            price = float(raw_price)
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
    include_demo: bool = False,
    query: str | None = None,
    data_mode: str | None = None,
    include_unknown: bool = False,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """
    Query nearby participating pharmacies and return truthful stock observations for the requested SKUs.
    Separates demands from offers; calculates real distance and freshness.
    """
    mode = _data_mode(data_mode)
    db = get_db()
    if isinstance(medicine_ids, str):
        query = medicine_ids
        medicine_ids = None

    if "patient_lat" in kwargs and user_lat is None:
        user_lat = kwargs.get("patient_lat")
    if "patient_lon" in kwargs and user_lon is None:
        user_lon = kwargs.get("patient_lon")

    query_requested = bool(str(query or "").strip())
    if query_requested and not medicine_ids:
        q_term = f"%{query.strip().lower()}%"
        sku_rows = db.execute(
            "SELECT id FROM medication_skus WHERE LOWER(name) LIKE ? OR LOWER(generic_name) LIKE ?",
            (q_term, q_term),
        ).fetchall()
        medicine_ids = [r["id"] for r in sku_rows]
        if not medicine_ids:
            return []

    where_clauses = ["u.role='pharmacy'", "u.active=1"]
    params: list[Any] = []

    # Inventory rows, not UI defaults, determine whether a pharmacy is a
    # candidate.  Explicit mode matching prevents synthetic rows leaking into
    # live searches (and vice versa).

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
            WHERE io.pharmacy_id=? AND io.data_mode=? {sku_filter}
            """,
            [pharm_uid, mode, *inv_params[1:]],
        ).fetchall()

        items_map = {}
        for obs in observations:
            o_dict = dict(obs)
            eff_status, freshness_label = evaluate_freshness(o_dict.get("observed_at"), o_dict.get("stock_status", "CONFIRMED"))
            if int(o_dict.get("quantity_available") or 0) <= 0 and eff_status == "CONFIRMED":
                eff_status = "UNAVAILABLE"
            o_dict["effective_status"] = eff_status
            o_dict["freshness_label"] = freshness_label
            o_dict["price_inr"] = float(o_dict["price_inr"]) if o_dict.get("price_available", 1) else None
            items_map[o_dict["sku_id"]] = o_dict

        if medicine_ids and not items_map and not include_unknown:
            continue

        pharm["distance_km"] = dist
        pharm["distance_text"] = f"{dist} km" if dist is not None else "Distance unavailable"
        pharm["inventory"] = items_map
        pharm["data_mode"] = mode
        pharm["is_demo"] = mode == "DEMO"
        pharm["provider_status"] = str(pharm.get("verification_status") or "UNVERIFIED").upper()
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
