"""Owner-controlled import of provider referrals from trusted contacts.

This path records leads in the existing provider-network table. It never
creates accounts, marks a provider verified, publishes schedules, or imports
patient and operational facts. Preview is the default and every applied row
requires a stable source reference for provenance and idempotency.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from .db import get_db, now_iso
from .provider_network import PROVIDER_TYPES, SOURCE_TYPES
from .security import assert_owner


CONTACT_SOURCE_TYPES = {"referral", "college_network", "institution_pilot"}
ALLOWED_FIELDS = {
    "provider_type",
    "source_type",
    "source_reference",
    "organization_name",
    "contact_name",
    "contact_email",
    "contact_phone",
    "state",
    "district",
    "city",
    "linked_pilot_id",
    "owner_note",
    "permission_to_share",
}
FORBIDDEN_FIELD_MARKERS = {
    "patient",
    "diagnosis",
    "prescription",
    "medical_record",
    "private_record",
    "password",
    "secret",
    "stock",
    "bed",
    "availability",
    "certification",
    "certificate",
}


def preview_trusted_provider_contacts(actor: Any, rows: list[dict[str, Any]]) -> dict:
    """Validate and classify trusted-contact rows without writing prospects."""
    assert_owner(actor)
    normalized, rejected = _normalize_rows(rows)
    accepted = []
    unchanged = []
    conflicts = []
    seen: dict[str, dict] = {}

    for item in normalized:
        reference = item["source_reference"]
        prior = seen.get(reference)
        if prior is not None:
            if _same_contact(prior, item):
                unchanged.append({"row_number": item["row_number"], "source_reference": reference, "reason": "duplicate in import"})
            else:
                conflicts.append({"row_number": item["row_number"], "source_reference": reference, "reason": "conflicting duplicate in import"})
            continue
        seen[reference] = item

        existing = get_db().execute(
            "SELECT * FROM provider_network_prospects WHERE source_reference=? ORDER BY id DESC LIMIT 1",
            (reference,),
        ).fetchone()
        if existing:
            existing = dict(existing)
            if _same_contact(existing, item):
                unchanged.append({"row_number": item["row_number"], "source_reference": reference, "reason": "already imported"})
            else:
                conflicts.append({"row_number": item["row_number"], "source_reference": reference, "reason": "source reference already represents different contact data"})
            continue
        accepted.append(item)

    return {
        "status": "previewed",
        "record_count": len(rows) if isinstance(rows, list) else 0,
        "accepted": accepted,
        "unchanged": unchanged,
        "conflicts": conflicts,
        "rejected": rejected,
        "can_apply": bool(accepted) and not conflicts and not rejected,
        "truth_notice": (
            "Trusted-contact referrals create discovered provider prospects only. "
            "They do not verify identity, certification, availability, stock, beds, or booking connectivity."
        ),
    }


def apply_trusted_provider_contacts(actor: Any, rows: list[dict[str, Any]]) -> dict:
    """Apply validated contacts atomically to the existing prospect pipeline."""
    assert_owner(actor)
    preview = preview_trusted_provider_contacts(actor, rows)
    if preview["conflicts"] or preview["rejected"]:
        raise ValueError("Resolve rejected or conflicting rows before applying this import.")

    db = get_db()
    now = now_iso()
    applied = []
    try:
        for item in preview["accepted"]:
            owner_note = _owner_note(item.get("owner_note"))
            cursor = db.execute(
                """
                INSERT INTO provider_network_prospects
                (prospect_uid,provider_type,organization_name,contact_name,contact_email,contact_phone,
                 state,district,city,source_type,source_reference,linked_pilot_id,status,owner_note,
                 created_by,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'discovered',?,?,?,?)
                """,
                (
                    f"trusted_{uuid.uuid4().hex[:20]}",
                    item["provider_type"],
                    item.get("organization_name"),
                    item.get("contact_name"),
                    item.get("contact_email"),
                    item.get("contact_phone"),
                    item.get("state"),
                    item.get("district"),
                    item.get("city"),
                    item["source_type"],
                    item["source_reference"],
                    item.get("linked_pilot_id"),
                    owner_note,
                    int(actor["id"]),
                    now,
                    now,
                ),
            )
            applied.append({"row_number": item["row_number"], "prospect_id": int(cursor.lastrowid), "source_reference": item["source_reference"]})
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        **preview,
        "status": "applied",
        "applied": applied,
        "applied_count": len(applied),
    }


def _normalize_rows(rows: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    if not isinstance(rows, list):
        raise ValueError("rows must be a list.")
    if len(rows) > 500:
        raise ValueError("A trusted-contact import may contain at most 500 rows.")

    accepted = []
    rejected = []
    for row_number, raw in enumerate(rows, start=1):
        if not isinstance(raw, dict):
            rejected.append({"row_number": row_number, "reason": "row must be an object"})
            continue
        keys = {str(key).strip() for key in raw}
        forbidden = sorted(
            key for key in keys
            if any(marker in key.casefold().replace("-", "_") for marker in FORBIDDEN_FIELD_MARKERS)
        )
        unknown = sorted(keys - ALLOWED_FIELDS)
        if forbidden:
            rejected.append({"row_number": row_number, "reason": "private or operational fields are not accepted", "fields": forbidden})
            continue
        if unknown:
            rejected.append({"row_number": row_number, "reason": "unsupported field(s): " + ", ".join(unknown)})
            continue

        item = {"row_number": row_number}
        for field in ALLOWED_FIELDS:
            value = raw.get(field)
            if field == "permission_to_share":
                if value is not True:
                    rejected.append({"row_number": row_number, "reason": "permission_to_share must be true"})
                    item = None
                    break
                continue
            if field == "linked_pilot_id":
                if value in (None, ""):
                    continue
                try:
                    value = int(value)
                    if value <= 0:
                        raise ValueError
                except (TypeError, ValueError):
                    rejected.append({"row_number": row_number, "reason": "linked_pilot_id must be a positive integer"})
                    item = None
                    break
            if value not in (None, ""):
                item[field] = str(value).strip()
        if item is None:
            continue

        provider_type = item.get("provider_type", "").lower()
        source_type = item.get("source_type", "").lower()
        reference = item.get("source_reference", "")
        if provider_type not in PROVIDER_TYPES:
            rejected.append({"row_number": row_number, "reason": "provider_type must be doctor, hospital, or pharmacy"})
            continue
        if source_type not in CONTACT_SOURCE_TYPES or source_type not in SOURCE_TYPES:
            rejected.append({"row_number": row_number, "reason": "source_type must be referral, college_network, or institution_pilot"})
            continue
        if not reference or len(reference) > 500:
            rejected.append({"row_number": row_number, "reason": "stable source_reference is required and must be at most 500 characters"})
            continue
        if source_type == "institution_pilot" and not item.get("linked_pilot_id"):
            rejected.append({"row_number": row_number, "reason": "institution_pilot requires linked_pilot_id"})
            continue
        if not any(item.get(field) for field in ("organization_name", "contact_name", "contact_email", "contact_phone")):
            rejected.append({"row_number": row_number, "reason": "a provider or contact identifier is required"})
            continue
        for field, limit in (("organization_name", 300), ("contact_name", 200), ("contact_email", 320), ("contact_phone", 80), ("state", 120), ("district", 120), ("city", 120), ("owner_note", 1600)):
            if field in item:
                item[field] = item[field][:limit]
        if item.get("linked_pilot_id"):
            pilot = get_db().execute("SELECT id FROM institution_pilots WHERE id=?", (item["linked_pilot_id"],)).fetchone()
            if not pilot:
                rejected.append({"row_number": row_number, "reason": "linked_pilot_id must reference an existing institution pilot"})
                continue
        accepted.append(item)
    return accepted, rejected


def _same_contact(existing: dict, item: dict) -> bool:
    fields = ("provider_type", "source_type", "organization_name", "contact_name", "contact_email", "contact_phone", "state", "district", "city", "linked_pilot_id")
    return all(str(existing.get(field) or "").strip().casefold() == str(item.get(field) or "").strip().casefold() for field in fields)


def _owner_note(note: Any) -> str:
    payload = {"permission_to_share": True, "import_kind": "trusted_contact_referral"}
    text = str(note or "").strip()
    if text:
        payload["contact_note"] = text[:1200]
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))

