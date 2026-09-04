"""
ZENDOC Diagnostic Marketplace — Milestone 10
Lab test catalog, nearby lab price comparison, home sample collection booking,
and seamless integration with Health Memory report intelligence.
"""
from __future__ import annotations

import math
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from .db import get_db, now_iso
from .inventory_service import calculate_distance_km


VALID_DATA_MODES = {"LIVE", "DEMO"}
VALID_COLLECTION_TYPES = {"home_collection", "lab_visit"}


def _explicit_confirmation(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return value is True or value == 1


def _data_mode(explicit: str | None = None) -> str:
    """Resolve the explicit LIVE/DEMO boundary without synthetic fallback."""
    value = explicit
    try:
        from flask import current_app, has_app_context

        if value is None and has_app_context():
            value = current_app.config.get("CONNECTED_CARE_DATA_MODE")
    except RuntimeError:
        pass
    value = value or os.environ.get("ZENDOC_CONNECTED_CARE_DATA_MODE", "LIVE")
    mode = str(value).strip().upper()
    if mode not in VALID_DATA_MODES:
        raise ValueError("Connected Care data mode must be LIVE or DEMO.")
    return mode


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


def _parse_future_date(value: str) -> str:
    """Return a canonical ISO date and reject malformed or past dates."""
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("scheduled_date is required.")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise ValueError("scheduled_date must be an ISO date or datetime.") from exc
    if parsed <= datetime.now(timezone.utc).date():
        raise ValueError("scheduled_date must be a future date.")
    return parsed.isoformat()


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
    data_mode: str | None = None,
) -> list[dict[str, Any]]:
    """
    Search verified labs offering the requested diagnostic test.

    A catalog row is descriptive only; it is not an offer and cannot supply a
    booking price.  Results require a provider-backed verified offer in the
    active connected-care data mode.
    """
    mode = _data_mode(data_mode)
    db = get_db()
    test_row = db.execute(
        "SELECT * FROM diagnostic_catalog WHERE id=? OR UPPER(code)=UPPER(?)",
        (test_code_or_id, str(test_code_or_id)),
    ).fetchone()
    if not test_row:
        return []

    test_id = test_row["id"]
    where_parts = [
        "do.test_id=?",
        "u.active=1",
        "LOWER(COALESCE(pp.verification_status, ''))='verified'",
        "COALESCE(do.verified, 0)=1",
        "UPPER(do.data_mode)=?",
    ]
    params: list[Any] = [test_id, mode]

    if city:
        where_parts.append("(LOWER(pp.city) LIKE ? OR LOWER(u.city) LIKE ?)")
        ct = f"%{city.strip().lower()}%"
        params.extend([ct, ct])

    where_sql = " AND ".join(where_parts)
    offers = db.execute(
        f"""
        SELECT do.*, u.name lab_name, u.phone lab_phone, pp.address, pp.city, pp.latitude, pp.longitude,
               pp.provider_type, pp.verification_status,
               dc.name test_name, dc.category, dc.fasting_required, dc.sample_type, dc.tat_hours
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
        try:
            price = float(item.get("price_inr"))
        except (TypeError, ValueError):
            # The catalog's standard_price_inr is intentionally not a
            # fallback for an offer with a missing or malformed price.
            continue
        if not math.isfinite(price) or price < 0:
            continue
        item["price_inr"] = price
        item["data_mode"] = mode
        item["is_demo"] = mode == "DEMO"
        item["provider_status"] = str(item.get("verification_status") or "UNVERIFIED").upper()
        dist = calculate_distance_km(user_lat, user_lon, item.get("latitude"), item.get("longitude"))
        item["distance_km"] = dist
        item["distance_text"] = f"{dist} km" if dist is not None else "Distance unavailable"
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
    slot_time: str | None = None,
    user_confirmed: bool = False,
    data_mode: str | None = None,
) -> dict[str, Any]:
    """Create a diagnostic request pending acknowledgement by a real lab.

    The diagnostic catalog is informational only.  A request requires an
    explicit user confirmation and a matching verified diagnostic offer.  The
    resulting status is ``requested``; this local service does not claim that
    a provider accepted, scheduled, or completed the test.
    """
    aid = _user_id(actor)
    if not aid:
        raise PermissionError("Authentication required to request diagnostic collection.")
    if not _explicit_confirmation(user_confirmed):
        raise ValueError("Explicit user confirmation is required before requesting a diagnostic test.")
    if not lab_id:
        raise ValueError("A verified lab offer is required; the diagnostic catalog alone cannot be booked.")
    try:
        lab_id = int(lab_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("lab_id must identify a verified diagnostic offer.") from exc
    if lab_id <= 0:
        raise ValueError("A verified lab offer is required; lab_id must be positive.")

    collection_type = str(collection_type or "").strip().lower()
    if collection_type not in VALID_COLLECTION_TYPES:
        raise ValueError("collection_type must be home_collection or lab_visit.")
    address = str(address or "").strip()
    if not address or address.lower() in {"patient address", "local address", "local area"}:
        raise ValueError("A collection address is required.")
    # A missing slot is an unconfirmed provider-side detail, not permission
    # to insert a plausible default time.
    slot_time = str(slot_time or "").strip() or None
    scheduled_date = _parse_future_date(scheduled_date)
    mode = _data_mode(data_mode)

    from .context_engine import verify_context_authorization

    verify_context_authorization(actor, patient_id, "diagnostic_booking")

    db = get_db()
    patient_row = db.execute(
        "SELECT id FROM users WHERE id=? AND active=1", (patient_id,)
    ).fetchone()
    if not patient_row:
        raise LookupError(f"Patient #{patient_id} not found.")
    test_row = db.execute("SELECT * FROM diagnostic_catalog WHERE id=?", (test_id,)).fetchone()
    if not test_row:
        raise LookupError(f"Diagnostic test #{test_id} not found.")

    offer = db.execute(
        """
        SELECT do.*, u.name lab_name, pp.verification_status, pp.provider_type,
               pp.address lab_address, pp.city lab_city
        FROM diagnostic_offers do
        JOIN users u ON u.id=do.lab_id AND u.active=1
        JOIN provider_profiles pp ON pp.user_id=u.id
        WHERE do.lab_id=? AND do.test_id=?
          AND COALESCE(do.verified, 0)=1
          AND LOWER(COALESCE(pp.verification_status, ''))='verified'
          AND UPPER(do.data_mode)=?
        """,
        (lab_id, test_id, mode),
    ).fetchone()
    if not offer:
        raise LookupError("The selected lab offer is not available as a verified offer in the current data mode.")
    if collection_type == "home_collection" and not bool(offer["home_collection_available"]):
        raise ValueError("The selected verified lab does not advertise home collection for this test.")
    try:
        price = float(offer["price_inr"])
    except (TypeError, ValueError) as exc:
        raise ValueError("The selected lab offer has no usable price.") from exc
    if not math.isfinite(price) or price < 0:
        raise ValueError("The selected lab offer has no usable price.")
    fee = offer["home_collection_fee_inr"] if collection_type == "home_collection" else 0
    try:
        fee = float(fee or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("The selected lab offer has no usable collection fee.") from exc
    if not math.isfinite(fee) or fee < 0:
        raise ValueError("The selected lab offer has no usable collection fee.")

    now = now_iso()
    uid = f"diag_{patient_id}_{test_id}_{uuid.uuid4().hex[:12]}"
    cursor = db.execute(
        """
        INSERT INTO diagnostic_bookings
        (booking_uid, patient_id, booked_by, lab_id, test_id, collection_type, scheduled_date,
         slot_time, address, status, price_inr, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'requested', ?, ?, ?)
        """,
        (uid, patient_id, aid, lab_id, test_id, collection_type, scheduled_date, slot_time, address, round(price + fee, 2), now, now),
    )
    booking_id = cursor.lastrowid

    from .care_graph import record_care_continuity_event

    record_care_continuity_event(
        patient_id=patient_id,
        event_type="DIAGNOSTIC_REQUESTED",
        title=f"Diagnostic request submitted: {test_row['name']}",
        summary=(
            f"Request sent to {offer['lab_name']} for {scheduled_date} "
            f"({collection_type.replace('_', ' ').title()}); provider acknowledgement is pending."
        ),
        source="USER_REPORTED",
        source_ref=f"diagnostic:{booking_id}",
        actor_id=aid,
        metadata={
            "booking_id": booking_id,
            "test_name": test_row["name"],
            "lab_id": lab_id,
            "lab_name": offer["lab_name"],
            "data_mode": mode,
        },
    )
    db.commit()

    return {
        "success": True,
        "booking_id": booking_id,
        "booking_uid": uid,
        "test_name": test_row["name"],
        "lab_id": lab_id,
        "lab_name": offer["lab_name"],
        "status": "requested",
        "price_inr": price,
        "collection_fee_inr": fee,
        "total_price_inr": round(price + fee, 2),
        "data_mode": mode,
        "is_demo": mode == "DEMO",
        "requires_provider_acknowledgement": True,
        "provider_acknowledgement_status": "pending",
    }


def complete_diagnostic_test(
    actor: Any,
    booking_id: int,
    results_summary: str | None = None,
) -> dict[str, Any]:
    """Record provider- or patient-reported completion without fake results.

    Only the assigned verified lab may create a provider-recorded completion.
    The booking owner may record a self-reported completion, but that event is
    intentionally not eligible for a verified provider review.
    """
    aid = _user_id(actor)
    if not aid:
        raise PermissionError("Authentication required to complete a diagnostic booking.")
    db = get_db()
    booking_row = db.execute("SELECT * FROM diagnostic_bookings WHERE id=?", (booking_id,)).fetchone()
    if not booking_row:
        raise LookupError(f"Diagnostic booking #{booking_id} not found.")

    status = str(booking_row["status"] or "").lower()
    if status == "completed":
        raise ValueError("Diagnostic booking is already completed.")
    if status not in {"requested", "accepted"}:
        raise ValueError(f"Diagnostic booking cannot be completed from status '{booking_row['status']}'.")

    lab_id = int(booking_row["lab_id"] or 0)
    if not lab_id:
        raise ValueError("Diagnostic booking has no assigned lab and cannot be completed as a verified interaction.")
    lab_row = db.execute(
        """
        SELECT u.id, u.active, pp.verification_status
        FROM users u
        LEFT JOIN provider_profiles pp ON pp.user_id=u.id
        WHERE u.id=?
        """,
        (lab_id,),
    ).fetchone()
    if not lab_row or not lab_row["active"]:
        raise PermissionError("The assigned lab is not active.")
    is_assigned_lab = aid == lab_id and str(lab_row["verification_status"] or "").lower() == "verified"
    is_owner = aid == int(booking_row["patient_id"])
    if not (is_assigned_lab or is_owner):
        raise PermissionError("Only the assigned verified lab or the booking owner may record completion.")

    summary = str(results_summary or "").strip() or "Completion recorded; report details were not supplied."
    summary = summary[:2000]
    completion_source = "PROVIDER_RECORDED" if is_assigned_lab else "USER_REPORTED"

    now = now_iso()
    update_cursor = db.execute(
        "UPDATE diagnostic_bookings SET status='completed', updated_at=? WHERE id=? AND status IN ('requested','accepted')",
        (now, booking_id),
    )
    if update_cursor.rowcount != 1:
        raise ValueError("Diagnostic booking could not be completed from its current state.")

    from .care_graph import record_care_continuity_event

    record_care_continuity_event(
        patient_id=booking_row["patient_id"],
        event_type="DIAGNOSTIC_COMPLETED",
        title=(
            "Diagnostic completion recorded"
            if completion_source == "PROVIDER_RECORDED"
            else "Diagnostic completion self-reported"
        ),
        summary=summary,
        source=completion_source,
        source_ref=f"diagnostic:{booking_id}",
        actor_id=aid,
        metadata={
            "booking_id": booking_id,
            "lab_id": lab_id,
            "completion_source": completion_source,
        },
    )
    db.commit()
    return {
        "success": True,
        "booking_id": booking_id,
        "status": "completed",
        "completion_source": completion_source,
        "review_eligible": completion_source == "PROVIDER_RECORDED",
        "report_available": False,
    }
