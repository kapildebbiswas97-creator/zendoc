"""Privacy-safe partner booking handoff workflow.

Partner handoffs are operational requests, not patient appointments.
They intentionally exclude symptoms, diagnoses, prescriptions, medical
history, clinical notes, and private patient records.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from .db import get_db, is_integrity_error, now_iso
from .provider_service import available_slots, get_public_provider_profile
from .partner_audit import record_partner_audit_event
from .security import assert_owner


HANDOFF_STATUSES = {"received", "pending", "accepted", "rejected", "cancelled"}
HOLD_MINUTES = 30


def create_partner_booking_handoff(
    identity: dict,
    *,
    provider_profile_id: int,
    partner_reference: str,
    requested_for: str,
    contact_reference: str | None = None,
) -> dict:
    provider = get_public_provider_profile(int(provider_profile_id))
    if not provider:
        raise LookupError("Verified public provider not found.")

    reference = str(partner_reference or "").strip()
    if not reference:
        raise ValueError("partner_reference is required.")
    if len(reference) > 200:
        raise ValueError("partner_reference is too long.")

    requested_for = str(requested_for or "").strip()
    if not requested_for:
        raise ValueError("requested_for is required.")
    try:
        requested_dt = datetime.fromisoformat(requested_for.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("requested_for must be a valid ISO date-time.") from exc
    if requested_dt.tzinfo is None:
        requested_dt = requested_dt.replace(tzinfo=timezone.utc)
    requested_dt = requested_dt.astimezone(timezone.utc)
    slot_key = requested_dt.strftime("%Y-%m-%dT%H:%M")

    db = get_db()
    existing = db.execute(
        """
        SELECT id FROM partner_booking_handoffs
        WHERE client_id=? AND partner_reference=?
        LIMIT 1
        """,
        (int(identity["client_id"]), reference),
    ).fetchone()
    if existing:
        return get_partner_booking_handoff(identity, int(existing["id"]))

    requested_date = requested_dt.date().isoformat()
    slots = available_slots(int(provider_profile_id), requested_date)
    normalized_slots = {str(item)[:16] for item in slots}
    if slot_key not in normalized_slots:
        raise ValueError("Requested provider slot is not currently available.")

    now = now_iso()
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=HOLD_MINUTES)).isoformat(timespec="seconds")
    try:
        db.execute(
            """
            DELETE FROM partner_slot_holds
            WHERE provider_profile_id=? AND slot_key=? AND expires_at<=?
            """,
            (int(provider_profile_id), slot_key, now),
        )
        cursor = db.execute(
            """
            INSERT INTO partner_booking_handoffs
            (handoff_uid,client_id,provider_profile_id,partner_reference,requested_for,
             contact_reference,status,status_note,created_at,updated_at)
            VALUES (?,?,?,?,?,?,'received',NULL,?,?)
            """,
            (
                f"handoff_{uuid.uuid4().hex[:20]}",
                int(identity["client_id"]),
                int(provider_profile_id),
                reference,
                requested_dt.isoformat(timespec="minutes"),
                _clean(contact_reference, 300),
                now,
                now,
            ),
        )
        handoff_id = int(cursor.lastrowid)
        db.execute(
            """
            INSERT INTO partner_slot_holds
            (client_id,provider_profile_id,slot_key,handoff_id,status,expires_at,created_at,updated_at)
            VALUES (?,?,?,?,'active',?,?,?)
            """,
            (
                int(identity["client_id"]),
                int(provider_profile_id),
                slot_key,
                handoff_id,
                expires_at,
                now,
                now,
            ),
        )
        db.commit()
        record_partner_audit_event(
            event_type="handoff_created",
            actor_type="partner",
            client_id=int(identity["client_id"]),
            key_id=int(identity["key_id"]) if identity.get("key_id") is not None else None,
            entity_type="partner_booking_handoff",
            entity_id=handoff_id,
            metadata={"provider_profile_id": int(provider_profile_id), "slot_key": slot_key, "status": "received"},
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        if is_integrity_error(exc):
            existing = db.execute(
                """
                SELECT id FROM partner_booking_handoffs
                WHERE client_id=? AND partner_reference=?
                """,
                (int(identity["client_id"]), reference),
            ).fetchone()
            if existing:
                return get_partner_booking_handoff(identity, int(existing["id"]))
            raise ValueError("Requested provider slot is temporarily held by another coordination request.") from exc
        raise

    return get_partner_booking_handoff(identity, handoff_id)


def get_partner_booking_handoff(identity: dict, handoff_id: int) -> dict:
    row = get_db().execute(
        """
        SELECT h.*,p.provider_type,p.specialty,p.organization,u.name provider_name
        FROM partner_booking_handoffs h
        JOIN provider_profiles p ON p.id=h.provider_profile_id
        JOIN users u ON u.id=p.user_id
        WHERE h.id=? AND h.client_id=?
        """,
        (int(handoff_id), int(identity["client_id"])),
    ).fetchone()
    if not row:
        raise LookupError("Partner booking handoff not found.")
    result = dict(row)
    result["handoff_accepted"] = result["status"] == "accepted"
    result["booking_confirmed"] = False
    result["truth_notice"] = (
        "An accepted partner handoff means the provider accepted the coordination request; it is not a "
        "patient appointment record and does not by itself confirm a booked appointment. No symptoms, "
        "diagnosis, prescriptions, medical history, or clinical notes are stored here."
    )
    return result


def list_partner_booking_handoffs(identity: dict, *, limit: int = 100) -> list[dict]:
    limit = max(1, min(int(limit or 100), 500))
    rows = get_db().execute(
        """
        SELECT id FROM partner_booking_handoffs
        WHERE client_id=?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (int(identity["client_id"]), limit),
    ).fetchall()
    return [get_partner_booking_handoff(identity, int(row["id"])) for row in rows]


def list_provider_booking_handoffs(user: Any, *, limit: int = 100) -> list[dict]:
    if not user or user["role"] not in {"doctor", "hospital", "pharmacy"}:
        raise PermissionError("Only provider accounts may view provider handoffs.")
    profile = get_db().execute(
        "SELECT id FROM provider_profiles WHERE user_id=?",
        (int(user["id"]),),
    ).fetchone()
    if not profile:
        return []
    limit = max(1, min(int(limit or 100), 500))
    rows = get_db().execute(
        """
        SELECT h.*,c.name client_name
        FROM partner_booking_handoffs h
        JOIN business_api_clients c ON c.id=h.client_id
        WHERE h.provider_profile_id=?
        ORDER BY h.created_at DESC
        LIMIT ?
        """,
        (int(profile["id"]), limit),
    ).fetchall()
    return [dict(row) for row in rows]


def provider_update_partner_booking_handoff(
    user: Any,
    handoff_id: int,
    *,
    status: str,
    status_note: str | None = None,
) -> dict:
    if not user or user["role"] not in {"doctor", "hospital", "pharmacy"}:
        raise PermissionError("Only provider accounts may review provider handoffs.")
    clean = str(status or "").strip().lower()
    if clean not in {"pending", "accepted", "rejected", "cancelled"}:
        raise ValueError("Unsupported handoff status.")

    db = get_db()
    row = db.execute(
        """
        SELECT h.*,p.user_id
        FROM partner_booking_handoffs h
        JOIN provider_profiles p ON p.id=h.provider_profile_id
        WHERE h.id=? AND p.user_id=?
        """,
        (int(handoff_id), int(user["id"])),
    ).fetchone()
    if not row:
        raise LookupError("Partner booking handoff not found for this provider.")

    db.execute(
        """
        UPDATE partner_booking_handoffs
        SET status=?,status_note=?,updated_at=?
        WHERE id=?
        """,
        (clean, _clean(status_note, 1000), now_iso(), int(handoff_id)),
    )
    _sync_slot_hold_after_status(int(handoff_id), clean)
    db.commit()
    record_partner_audit_event(
        event_type="handoff_status_updated",
        actor_type="provider",
        actor_user_id=int(user["id"]),
        client_id=int(row["client_id"]),
        entity_type="partner_booking_handoff",
        entity_id=int(handoff_id),
        metadata={"status": clean, "provider_profile_id": int(row["provider_profile_id"])},
    )
    db.commit()

    identity = {"client_id": int(row["client_id"])}
    return get_partner_booking_handoff(identity, int(handoff_id))


def list_all_partner_booking_handoffs(actor: Any, *, limit: int = 200) -> list[dict]:
    assert_owner(actor)
    limit = max(1, min(int(limit or 200), 500))
    rows = get_db().execute(
        """
        SELECT h.id,h.handoff_uid,h.client_id,c.name client_name,h.provider_profile_id,
               h.partner_reference,h.requested_for,h.contact_reference,h.status,h.status_note,
               h.created_at,h.updated_at,p.provider_type,p.specialty,p.organization,u.name provider_name
        FROM partner_booking_handoffs h
        JOIN business_api_clients c ON c.id=h.client_id
        JOIN provider_profiles p ON p.id=h.provider_profile_id
        JOIN users u ON u.id=p.user_id
        ORDER BY h.created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def owner_update_partner_booking_handoff(
    actor: Any,
    handoff_id: int,
    *,
    status: str,
    status_note: str | None = None,
) -> dict:
    assert_owner(actor)
    clean = str(status or "").strip().lower()
    if clean not in HANDOFF_STATUSES - {"received"}:
        raise ValueError("Unsupported handoff status.")

    db = get_db()
    row = db.execute("SELECT * FROM partner_booking_handoffs WHERE id=?", (int(handoff_id),)).fetchone()
    if not row:
        raise LookupError(f"Partner booking handoff #{handoff_id} not found.")

    db.execute(
        """
        UPDATE partner_booking_handoffs
        SET status=?,status_note=?,updated_at=?
        WHERE id=?
        """,
        (clean, _clean(status_note, 1000), now_iso(), int(handoff_id)),
    )
    _sync_slot_hold_after_status(int(handoff_id), clean)
    db.commit()
    record_partner_audit_event(
        event_type="handoff_status_updated",
        actor_type="owner",
        actor_user_id=int(actor["id"]),
        client_id=int(row["client_id"]),
        entity_type="partner_booking_handoff",
        entity_id=int(handoff_id),
        metadata={"status": clean, "provider_profile_id": int(row["provider_profile_id"])},
    )
    db.commit()

    identity = {"client_id": int(row["client_id"])}
    return get_partner_booking_handoff(identity, int(handoff_id))


def _sync_slot_hold_after_status(handoff_id: int, status: str) -> None:
    db = get_db()
    now = now_iso()
    if status in {"rejected", "cancelled"}:
        db.execute(
            "UPDATE partner_slot_holds SET status='released',updated_at=? WHERE handoff_id=? AND status='active'",
            (now, int(handoff_id)),
        )
    elif status == "accepted":
        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=HOLD_MINUTES)).isoformat(timespec="seconds")
        db.execute(
            """
            UPDATE partner_slot_holds
            SET expires_at=?,updated_at=?
            WHERE handoff_id=? AND status='active'
            """,
            (expires_at, now, int(handoff_id)),
        )


def _clean(value: Any, limit: int) -> str | None:
    text = str(value or "").strip()
    return text[:limit] or None
