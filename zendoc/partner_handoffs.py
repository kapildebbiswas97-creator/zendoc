"""Privacy-safe partner booking handoff workflow.

Partner handoffs are operational requests, not patient appointments.
They intentionally exclude symptoms, diagnoses, prescriptions, medical
history, clinical notes, and private patient records.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from .db import get_db, is_integrity_error, now_iso
from .provider_service import available_slots, get_public_provider_profile
from .security import assert_owner


HANDOFF_STATUSES = {"received", "pending", "accepted", "rejected", "cancelled"}


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

    requested_date = requested_dt.date().isoformat()
    slot_text = requested_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    slots = available_slots(int(provider_profile_id), requested_date)
    normalized_slots = {str(item)[:16] for item in slots}
    if slot_text[:16] not in normalized_slots:
        raise ValueError("Requested provider slot is not currently available.")

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

    now = now_iso()
    try:
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
                requested_dt.astimezone(timezone.utc).isoformat(timespec="minutes"),
                _clean(contact_reference, 300),
                now,
                now,
            ),
        )
        handoff_id = int(cursor.lastrowid)
        db.commit()
    except Exception as exc:
        if not is_integrity_error(exc):
            raise
        db.rollback()
        row = db.execute(
            "SELECT id FROM partner_booking_handoffs WHERE client_id=? AND partner_reference=?",
            (int(identity["client_id"]), reference),
        ).fetchone()
        if not row:
            raise
        handoff_id = int(row["id"])

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
    result["booking_confirmed"] = result["status"] == "accepted"
    result["truth_notice"] = (
        "A partner handoff is not a confirmed appointment unless status is accepted. "
        "No symptoms, diagnosis, prescriptions, medical history, or clinical notes are stored here."
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
    db.commit()

    identity = {"client_id": int(row["client_id"])}
    return get_partner_booking_handoff(identity, int(handoff_id))


def _clean(value: Any, limit: int) -> str | None:
    text = str(value or "").strip()
    return text[:limit] or None
