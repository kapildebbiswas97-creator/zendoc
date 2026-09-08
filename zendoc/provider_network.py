"""Owner-managed provider network prospect and activation pipeline."""
from __future__ import annotations

import uuid
from typing import Any

from .db import get_db, now_iso
from .provider_onboarding import provider_onboarding_status
from .security import assert_owner


PROSPECT_STATUSES = {
    "discovered",
    "contacted",
    "interested",
    "registered",
    "profile_created",
    "evidence_submitted",
    "verified",
    "activated",
    "paused",
    "declined",
}
PROVIDER_TYPES = {"doctor", "hospital", "pharmacy"}
SOURCE_TYPES = {
    "public_directory",
    "referral",
    "college_network",
    "institution_pilot",
    "manual_outreach",
    "inbound",
    "other",
}


def create_provider_prospect(actor: Any, data: dict) -> dict:
    assert_owner(actor)
    provider_type = str(data.get("provider_type") or "").strip().lower()
    if provider_type not in PROVIDER_TYPES:
        raise ValueError("provider_type must be doctor, hospital, or pharmacy.")
    source_type = str(data.get("source_type") or "").strip().lower()
    if source_type not in SOURCE_TYPES:
        raise ValueError("Unsupported prospect source_type.")
    if not any(
        str(data.get(field) or "").strip()
        for field in ("organization_name", "contact_name", "contact_email", "contact_phone")
    ):
        raise ValueError("At least one provider/organization contact identifier is required.")

    status = str(data.get("status") or "discovered").strip().lower()
    if status not in PROSPECT_STATUSES:
        raise ValueError("Unsupported provider prospect status.")

    linked_user_id = _optional_positive_int(data.get("linked_user_id"))
    linked_profile_id = _optional_positive_int(data.get("linked_provider_profile_id"))
    linked_pilot_id = _optional_positive_int(data.get("linked_pilot_id"))
    _validate_pilot_link(source_type, linked_pilot_id)
    _validate_links(linked_user_id, linked_profile_id, provider_type)
    _validate_status_against_links(
        status=status,
        linked_user_id=linked_user_id,
        linked_profile_id=linked_profile_id,
        provider_type=provider_type,
    )

    now = now_iso()
    first_contact = _clean(data.get("first_contact_at"), 64)
    last_contact = _clean(data.get("last_contact_at"), 64)
    if status in {"contacted", "interested"} and not first_contact:
        first_contact = now
    if status in {"contacted", "interested"} and not last_contact:
        last_contact = now
    activated_at = now if status == "activated" else None

    cursor = get_db().execute(
        """
        INSERT INTO provider_network_prospects
        (prospect_uid,provider_type,organization_name,contact_name,contact_email,contact_phone,
         state,district,city,source_type,source_reference,linked_pilot_id,status,first_contact_at,last_contact_at,
         next_action,next_action_due,owner_note,linked_user_id,linked_provider_profile_id,
         activated_at,created_by,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            f"prospect_{uuid.uuid4().hex[:20]}",
            provider_type,
            _clean(data.get("organization_name"), 300),
            _clean(data.get("contact_name"), 200),
            _clean(data.get("contact_email"), 320),
            _clean(data.get("contact_phone"), 80),
            _clean(data.get("state"), 120),
            _clean(data.get("district"), 120),
            _clean(data.get("city"), 120),
            source_type,
            _clean(data.get("source_reference"), 500),
            linked_pilot_id,
            status,
            first_contact,
            last_contact,
            _clean(data.get("next_action"), 500),
            _clean(data.get("next_action_due"), 64),
            _clean(data.get("owner_note"), 1600),
            linked_user_id,
            linked_profile_id,
            activated_at,
            int(actor["id"]),
            now,
            now,
        ),
    )
    get_db().commit()
    return get_provider_prospect(int(cursor.lastrowid))


def update_provider_prospect(actor: Any, prospect_id: int, data: dict) -> dict:
    assert_owner(actor)
    existing = get_provider_prospect(prospect_id)
    status = str(data.get("status", existing["status"]) or "").strip().lower()
    if status not in PROSPECT_STATUSES:
        raise ValueError("Unsupported provider prospect status.")
    provider_type = str(data.get("provider_type", existing["provider_type"]) or "").strip().lower()
    if provider_type not in PROVIDER_TYPES:
        raise ValueError("Unsupported provider_type.")
    source_type = str(data.get("source_type", existing["source_type"]) or "").strip().lower()
    if source_type not in SOURCE_TYPES:
        raise ValueError("Unsupported prospect source_type.")

    linked_user_id = _optional_positive_int(data.get("linked_user_id", existing["linked_user_id"]))
    linked_profile_id = _optional_positive_int(
        data.get("linked_provider_profile_id", existing["linked_provider_profile_id"])
    )
    linked_pilot_id = _optional_positive_int(data.get("linked_pilot_id", existing.get("linked_pilot_id")))
    _validate_pilot_link(source_type, linked_pilot_id)
    _validate_links(linked_user_id, linked_profile_id, provider_type)
    _validate_status_against_links(
        status=status,
        linked_user_id=linked_user_id,
        linked_profile_id=linked_profile_id,
        provider_type=provider_type,
    )

    first_contact = _clean(data.get("first_contact_at", existing["first_contact_at"]), 64)
    last_contact = _clean(data.get("last_contact_at", existing["last_contact_at"]), 64)
    now = now_iso()
    if status in {"contacted", "interested"} and not first_contact:
        first_contact = now
    if status in {"contacted", "interested"}:
        last_contact = last_contact or now

    activated_at = existing["activated_at"]
    if status == "activated" and not activated_at:
        activated_at = now
    elif status != "activated" and data.get("clear_activation"):
        activated_at = None

    get_db().execute(
        """
        UPDATE provider_network_prospects
        SET provider_type=?,organization_name=?,contact_name=?,contact_email=?,contact_phone=?,
            state=?,district=?,city=?,source_type=?,source_reference=?,linked_pilot_id=?,status=?,
            first_contact_at=?,last_contact_at=?,next_action=?,next_action_due=?,owner_note=?,
            linked_user_id=?,linked_provider_profile_id=?,activated_at=?,updated_at=?
        WHERE id=?
        """,
        (
            provider_type,
            _clean(data.get("organization_name", existing["organization_name"]), 300),
            _clean(data.get("contact_name", existing["contact_name"]), 200),
            _clean(data.get("contact_email", existing["contact_email"]), 320),
            _clean(data.get("contact_phone", existing["contact_phone"]), 80),
            _clean(data.get("state", existing["state"]), 120),
            _clean(data.get("district", existing["district"]), 120),
            _clean(data.get("city", existing["city"]), 120),
            source_type,
            _clean(data.get("source_reference", existing["source_reference"]), 500),
            linked_pilot_id,
            status,
            first_contact,
            last_contact,
            _clean(data.get("next_action", existing["next_action"]), 500),
            _clean(data.get("next_action_due", existing["next_action_due"]), 64),
            _clean(data.get("owner_note", existing["owner_note"]), 1600),
            linked_user_id,
            linked_profile_id,
            activated_at,
            now,
            int(prospect_id),
        ),
    )
    get_db().commit()
    return get_provider_prospect(prospect_id)


def get_provider_prospect(prospect_id: int) -> dict:
    row = get_db().execute(
        """
        SELECT p.*,u.email linked_user_email,u.name linked_user_name,
               pp.verification_status linked_verification_status,
               ip.organization_name linked_pilot_name,ip.status linked_pilot_status
        FROM provider_network_prospects p
        LEFT JOIN users u ON u.id=p.linked_user_id
        LEFT JOIN provider_profiles pp ON pp.id=p.linked_provider_profile_id
        LEFT JOIN institution_pilots ip ON ip.id=p.linked_pilot_id
        WHERE p.id=?
        """,
        (int(prospect_id),),
    ).fetchone()
    if not row:
        raise LookupError(f"Provider prospect #{prospect_id} not found.")
    item = dict(row)
    item["observed_onboarding"] = _observed_onboarding(item.get("linked_provider_profile_id"))
    return item


def list_provider_prospects(
    actor: Any,
    *,
    status: str | None = None,
    provider_type: str | None = None,
    linked_pilot_id: int | None = None,
    limit: int = 200,
) -> list[dict]:
    assert_owner(actor)
    clauses = []
    params: list[Any] = []
    if status:
        clean = str(status).strip().lower()
        if clean not in PROSPECT_STATUSES:
            raise ValueError("Unsupported provider prospect status.")
        clauses.append("status=?")
        params.append(clean)
    if provider_type:
        clean_type = str(provider_type).strip().lower()
        if clean_type not in PROVIDER_TYPES:
            raise ValueError("Unsupported provider_type.")
        clauses.append("provider_type=?")
        params.append(clean_type)
    if linked_pilot_id not in (None, ""):
        clauses.append("linked_pilot_id=?")
        params.append(int(linked_pilot_id))
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    limit = max(1, min(int(limit or 200), 1000))
    params.append(limit)
    rows = get_db().execute(
        f"SELECT id FROM provider_network_prospects {where} ORDER BY updated_at DESC,id DESC LIMIT ?",
        params,
    ).fetchall()
    return [get_provider_prospect(int(row["id"])) for row in rows]


def provider_network_metrics(actor: Any) -> dict:
    assert_owner(actor)
    rows = get_db().execute("SELECT * FROM provider_network_prospects").fetchall()
    status_counts = {status: 0 for status in PROSPECT_STATUSES}
    type_counts = {provider_type: 0 for provider_type in PROVIDER_TYPES}
    linked_profiles = 0
    verified_profiles = 0
    activated = 0

    for row in rows:
        status_counts[str(row["status"])] = status_counts.get(str(row["status"]), 0) + 1
        type_counts[str(row["provider_type"])] = type_counts.get(str(row["provider_type"]), 0) + 1
        if row["linked_provider_profile_id"] is not None:
            linked_profiles += 1
            onboarding = _observed_onboarding(int(row["linked_provider_profile_id"]))
            if onboarding and onboarding["verification_status"] == "verified":
                verified_profiles += 1
        if row["status"] == "activated":
            activated += 1

    total = len(rows)
    return {
        "prospect_count": total,
        "status_counts": status_counts,
        "provider_type_counts": type_counts,
        "linked_profile_count": linked_profiles,
        "linked_verified_profile_count": verified_profiles,
        "activated_count": activated,
        "activation_rate": round(activated / total, 4) if total else None,
        "truth_notice": (
            "Prospect metrics count only owner-recorded provider outreach/prospect records. "
            "Linked verification state is read from real provider profiles; no invitation or activation count is inferred."
        ),
    }


def _observed_onboarding(profile_id: int | None) -> dict | None:
    if not profile_id:
        return None
    try:
        status = provider_onboarding_status(int(profile_id))
    except LookupError:
        return None
    return {
        "verification_status": status["verification_status"],
        "completeness_score": status["completeness_score"],
        "evidence_count": status["evidence_count"],
        "verified_evidence_count": status["verified_evidence_count"],
        "active_schedule_count": status["active_schedule_count"],
        "verification_ready": status["verification_ready"],
        "blockers": status["blockers"],
    }


def _validate_status_against_links(
    *,
    status: str,
    linked_user_id: int | None,
    linked_profile_id: int | None,
    provider_type: str,
) -> None:
    if status in {"registered", "profile_created", "evidence_submitted", "verified", "activated"} and linked_user_id is None:
        raise ValueError(f"status '{status}' requires a linked registered provider account.")

    if status in {"profile_created", "evidence_submitted", "verified", "activated"} and linked_profile_id is None:
        raise ValueError(f"status '{status}' requires a linked provider profile.")

    if linked_profile_id is None:
        return

    onboarding = _observed_onboarding(linked_profile_id)
    if onboarding is None:
        raise ValueError("Linked provider profile onboarding state is unavailable.")

    if status == "evidence_submitted" and onboarding["evidence_count"] < 1:
        raise ValueError("Cannot mark evidence_submitted before real verification evidence exists.")

    if status in {"verified", "activated"} and onboarding["verification_status"] != "verified":
        raise ValueError(f"Cannot mark {status} before the linked provider is actually verified.")

    if status == "activated":
        if provider_type in {"doctor", "hospital"} and onboarding["active_schedule_count"] < 1:
            raise ValueError("Doctor/hospital activation requires at least one active published schedule.")




def _validate_pilot_link(source_type: str, linked_pilot_id: int | None) -> None:
    if source_type == "institution_pilot" and linked_pilot_id is None:
        raise ValueError("institution_pilot prospects require linked_pilot_id.")
    if linked_pilot_id is None:
        return
    pilot = get_db().execute(
        "SELECT id FROM institution_pilots WHERE id=?",
        (int(linked_pilot_id),),
    ).fetchone()
    if not pilot:
        raise ValueError("linked_pilot_id must reference an existing institution pilot.")


def _validate_links(
    linked_user_id: int | None,
    linked_profile_id: int | None,
    provider_type: str,
) -> None:
    db = get_db()
    if linked_user_id is not None:
        user = db.execute(
            "SELECT id,role FROM users WHERE id=? AND active=1",
            (int(linked_user_id),),
        ).fetchone()
        if not user or user["role"] not in PROVIDER_TYPES:
            raise ValueError("linked_user_id must reference an active provider account.")
        if user["role"] != provider_type:
            raise ValueError("linked user role must match provider_type.")

    if linked_profile_id is not None:
        profile = db.execute(
            """
            SELECT p.id,p.user_id,p.provider_type,u.role
            FROM provider_profiles p
            JOIN users u ON u.id=p.user_id
            WHERE p.id=?
            """,
            (int(linked_profile_id),),
        ).fetchone()
        if not profile:
            raise ValueError("linked_provider_profile_id not found.")
        if profile["provider_type"] != provider_type or profile["role"] != provider_type:
            raise ValueError("linked provider profile type must match provider_type.")
        if linked_user_id is not None and int(profile["user_id"]) != int(linked_user_id):
            raise ValueError("linked user and provider profile must belong to the same provider.")


def _optional_positive_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    number = int(value)
    if number <= 0:
        raise ValueError("Linked IDs must be positive integers.")
    return number


def _clean(value: Any, limit: int) -> str | None:
    text = str(value or "").strip()
    return text[:limit] or None
