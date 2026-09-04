"""
ZENDOC Diagnostic Marketplace — Milestone 10
Lab test catalog, nearby lab price comparison, home sample collection booking,
and seamless integration with Health Memory report intelligence.
"""
from __future__ import annotations

import json
from typing import Any

from .db import get_db, now_iso
from .inventory_service import calculate_distance_km


def _user_id(actor: Any) -> int:
    if actor is None:
        return 0
    if isinstance(actor, (int, float)):
        return int(actor)
    try:
        val = actor["id"]
        if val is not None:
            return int(val)
    except Exception:
        pass
    try:
        val = getattr(actor, "id", None)
        if val is not None:
            return int(val)
    except Exception:
        pass
    return 0


def list_diagnostic_catalog(category: str | None = None) -> list[dict[str, Any]]:
    """Return available diagnostic tests."""
    db = get_db()
    if category:
        rows = db.execute("SELECT * FROM diagnostic_catalog WHERE LOWER(category)=LOWER(?) ORDER BY name", (category,)).fetchall()
    else:
        rows = db.execute("SELECT * FROM diagnostic_catalog ORDER BY category, name").fetchall()
    return [dict(r) for r in rows]


def search_lab_offers(
    test_code_or_id: str | int,
    city: str | None = None,
    user_lat: float | None = None,
    user_lon: float | None = None,
) -> list[dict[str, Any]]:
    """
    Search nearby verified labs offering the requested diagnostic test.
    Compares standard prices, home collection availability, and distance.
    """
    db = get_db()
    test_row = db.execute(
        "SELECT * FROM diagnostic_catalog WHERE id=? OR UPPER(code)=UPPER(?)",
        (test_code_or_id, str(test_code_or_id)),
    ).fetchone()
    if not test_row:
        return []

    test_id = test_row["id"]
    where_parts = ["do.test_id=?", "u.active=1"]
    params: list[Any] = [test_id]

    if city:
        where_parts.append("(LOWER(pp.city) LIKE ? OR LOWER(u.city) LIKE ?)")
        ct = f"%{city.strip().lower()}%"
        params.extend([ct, ct])

    where_sql = " AND ".join(where_parts)
    offers = db.execute(
        f"""
        SELECT do.*, u.name lab_name, u.phone lab_phone, pp.address, pp.city, pp.latitude, pp.longitude,
               pp.verification_status, dc.name test_name, dc.category, dc.fasting_required, dc.sample_type, dc.tat_hours
        FROM diagnostic_offers do
        JOIN users u ON u.id=do.lab_id
        JOIN diagnostic_catalog dc ON dc.id=do.test_id
        LEFT JOIN provider_profiles pp ON pp.user_id=u.id
        WHERE {where_sql}
        ORDER BY do.price_inr ASC
        """,
        params,
    ).fetchall()

    results = []
    for off in offers:
        item = dict(off)
        dist = calculate_distance_km(user_lat, user_lon, item.get("latitude"), item.get("longitude"))
        item["distance_km"] = dist
        item["distance_text"] = f"{dist} km" if dist is not None else "Distance unconfirmed"
        results.append(item)
    return results


def book_diagnostic_test(
    actor: Any,
    patient_id: int,
    test_id: int,
    lab_id: int | None,
    scheduled_date: str,
    address: str,
    collection_type: str = "home_collection",
    slot_time: str = "08:00 - 10:00",
) -> dict[str, Any]:
    """Book a diagnostic lab test or home sample collection."""
    aid = _user_id(actor)
    from .context_engine import verify_context_authorization
    verify_context_authorization(actor, patient_id, "diagnostic_booking")

    db = get_db()
    test_row = db.execute("SELECT * FROM diagnostic_catalog WHERE id=?", (test_id,)).fetchone()
    if not test_row:
        raise LookupError(f"Diagnostic test #{test_id} not found.")

    # Determine price from offer or standard price
    price = float(test_row["standard_price_inr"])
    if lab_id:
        offer = db.execute("SELECT price_inr FROM diagnostic_offers WHERE lab_id=? AND test_id=?", (lab_id, test_id)).fetchone()
        if offer:
            price = float(offer["price_inr"])

    now = now_iso()
    uid = f"diag_{patient_id}_{test_id}_{now[:10].replace('-', '')}"
    cursor = db.execute(
        """
        INSERT INTO diagnostic_bookings
        (booking_uid, patient_id, booked_by, lab_id, test_id, collection_type, scheduled_date, slot_time, address, status, price_inr, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'confirmed', ?, ?, ?)
        """,
        (uid, patient_id, aid, lab_id, test_id, collection_type, scheduled_date, slot_time, address, price, now, now),
    )
    booking_id = cursor.lastrowid

    # Record continuity event in Health Memory
    from .care_graph import record_care_continuity_event
    record_care_continuity_event(
        patient_id=patient_id,
        event_type="DIAGNOSTIC_BOOKED",
        title=f"Diagnostic booked: {test_row['name']}",
        summary=f"Sample collection scheduled for {scheduled_date} ({collection_type.replace('_', ' ').title()}).",
        source="USER_REPORTED",
        source_ref=f"diagnostic:{booking_id}",
        actor_id=aid,
        metadata={"booking_id": booking_id, "test_name": test_row["name"]},
    )
    db.commit()

    return {
        "success": True,
        "booking_id": booking_id,
        "booking_uid": uid,
        "test_name": test_row["name"],
        "status": "confirmed",
        "price_inr": price,
    }


def complete_diagnostic_test(
    actor: Any,
    booking_id: int,
    results_summary: str = "Test completed successfully",
) -> dict[str, Any]:
    """Complete a diagnostic test, attach to Health Memory, and enable review."""
    db = get_db()
    booking_row = db.execute("SELECT * FROM diagnostic_bookings WHERE id=?", (booking_id,)).fetchone()
    if not booking_row:
        raise LookupError(f"Diagnostic booking #{booking_id} not found.")

    now = now_iso()
    db.execute(
        "UPDATE diagnostic_bookings SET status='completed', updated_at=? WHERE id=?",
        (now, booking_id),
    )

    from .care_graph import record_care_continuity_event
    record_care_continuity_event(
        patient_id=booking_row["patient_id"],
        event_type="DIAGNOSTIC_COMPLETED",
        title="Diagnostic report ready",
        summary=results_summary,
        source="PROVIDER_RECORDED",
        source_ref=f"diagnostic:{booking_id}",
        actor_id=_user_id(actor),
        metadata={"booking_id": booking_id},
    )
    db.commit()
    return {"success": True, "booking_id": booking_id, "status": "completed"}