"""Provider onboarding and verification-evidence workflow."""
from __future__ import annotations

import json
import urllib.parse
from typing import Any

from .db import get_db, now_iso
from .provider_service import get_provider_profile_for_user
from .security import assert_owner


EVIDENCE_TYPES = {
    "professional_registration",
    "facility_registration",
    "pharmacy_license",
    "organization_registration",
    "government_registry_reference",
    "other_official_evidence",
}
EVIDENCE_STATUSES = {"pending", "verified", "rejected"}


def provider_onboarding_status(profile_id: int) -> dict:
    db = get_db()
    profile = db.execute(
        """
        SELECT p.*, u.name provider_name, u.email provider_email, u.role
        FROM provider_profiles p
        JOIN users u ON u.id=p.user_id
        WHERE p.id=?
        """,
        (int(profile_id),),
    ).fetchone()
    if not profile:
        raise LookupError(f"Provider profile #{profile_id} not found.")
    profile = dict(profile)

    required = _required_fields(profile["role"])
    completed_fields = [field for field in required if str(profile.get(field) or "").strip()]
    missing_fields = [field for field in required if field not in completed_fields]

    schedule_count = db.execute(
        "SELECT COUNT(*) c FROM provider_schedules WHERE provider_profile_id=? AND active=1",
        (int(profile_id),),
    ).fetchone()["c"]
    evidence_rows = db.execute(
        "SELECT * FROM provider_verification_evidence WHERE provider_profile_id=? ORDER BY created_at DESC",
        (int(profile_id),),
    ).fetchall()
    evidence = [dict(row) for row in evidence_rows]
    verified_evidence = [row for row in evidence if row["status"] == "verified"]

    field_score = int(round((len(completed_fields) / len(required)) * 70)) if required else 70
    schedule_score = 10 if schedule_count else 0
    evidence_score = 20 if verified_evidence else (5 if evidence else 0)
    score = min(100, field_score + schedule_score + evidence_score)

    blockers = []
    if missing_fields:
        blockers.append("Complete required public profile fields.")
    if not schedule_count and profile["provider_type"] in {"doctor", "hospital"}:
        blockers.append("Publish at least one active booking schedule.")
    if not verified_evidence:
        blockers.append("At least one official verification evidence item must be owner-reviewed as verified.")

    return {
        "profile_id": int(profile_id),
        "user_id": profile["user_id"],
        "role": profile["role"],
        "provider_type": profile["provider_type"],
        "verification_status": profile["verification_status"],
        "completeness_score": score,
        "required_fields": required,
        "completed_fields": completed_fields,
        "missing_fields": missing_fields,
        "active_schedule_count": int(schedule_count),
        "evidence_count": len(evidence),
        "verified_evidence_count": len(verified_evidence),
        "verification_ready": not blockers,
        "blockers": blockers,
        "connection_state": _connection_state(profile),
        "truth_notice": (
            "Profile completeness and evidence readiness do not automatically verify the provider. "
            "Owner/admin review remains required, and verification does not imply external booking or payment connectivity."
        ),
    }


def submit_provider_evidence(
    actor: Any,
    *,
    evidence_type: str,
    identifier: str | None,
    source_name: str,
    source_url: str | None = None,
    notes: str | None = None,
) -> dict:
    profile = get_provider_profile_for_user(_user_id(actor))
    if not profile:
        raise LookupError("Create a provider profile before submitting verification evidence.")
    evidence_type = str(evidence_type or "").strip().lower()
    if evidence_type not in EVIDENCE_TYPES:
        raise ValueError("Unsupported provider evidence_type.")
    source_name = str(source_name or "").strip()
    if not source_name:
        raise ValueError("source_name is required.")
    identifier = str(identifier or "").strip()[:240] or None
    source_url = str(source_url or "").strip()[:1000] or None
    if source_url:
        parsed_url = urllib.parse.urlparse(source_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("source_url must be an absolute http(s) URL.")
    notes = str(notes or "").strip()[:1000] or None

    db = get_db()
    now = now_iso()
    cursor = db.execute(
        """
        INSERT INTO provider_verification_evidence
        (provider_profile_id,evidence_type,identifier,source_name,source_url,status,notes,submitted_by,created_at)
        VALUES (?,?,?,?,?,'pending',?,?,?)
        """,
        (
            profile["id"], evidence_type, identifier, source_name, source_url,
            notes, _user_id(actor), now,
        ),
    )
    _record_event(
        int(profile["id"]),
        "evidence_submitted",
        "pending",
        f"Verification evidence submitted: {evidence_type}.",
        actor_id=_user_id(actor),
        metadata={"evidence_id": cursor.lastrowid, "source_name": source_name},
    )
    db.commit()
    return get_provider_evidence(cursor.lastrowid)


def get_provider_evidence(evidence_id: int) -> dict:
    row = get_db().execute(
        """
        SELECT e.*, p.user_id, p.organization, p.provider_type
        FROM provider_verification_evidence e
        JOIN provider_profiles p ON p.id=e.provider_profile_id
        WHERE e.id=?
        """,
        (int(evidence_id),),
    ).fetchone()
    if not row:
        raise LookupError(f"Provider evidence #{evidence_id} not found.")
    return dict(row)


def list_provider_evidence(profile_id: int) -> list[dict]:
    rows = get_db().execute(
        "SELECT * FROM provider_verification_evidence WHERE provider_profile_id=? ORDER BY created_at DESC",
        (int(profile_id),),
    ).fetchall()
    return [dict(row) for row in rows]


def review_provider_evidence(
    actor: Any,
    evidence_id: int,
    *,
    status: str,
    notes: str | None = None,
) -> dict:
    assert_owner(actor)
    evidence = get_provider_evidence(evidence_id)
    status = str(status or "").strip().lower()
    if status not in {"verified", "rejected"}:
        raise ValueError("Evidence review status must be verified or rejected.")
    db = get_db()
    now = now_iso()
    db.execute(
        """
        UPDATE provider_verification_evidence
        SET status=?,notes=COALESCE(?,notes),reviewed_by=?,reviewed_at=?
        WHERE id=?
        """,
        (status, str(notes or "").strip()[:1000] or None, _user_id(actor), now, int(evidence_id)),
    )
    _record_event(
        int(evidence["provider_profile_id"]),
        "evidence_reviewed",
        status,
        f"Verification evidence #{evidence_id} marked {status}.",
        actor_id=_user_id(actor),
        metadata={"evidence_id": evidence_id},
    )
    db.commit()
    return get_provider_evidence(evidence_id)


def list_provider_onboarding_events(profile_id: int, limit: int = 50) -> list[dict]:
    limit = max(1, min(int(limit or 50), 200))
    rows = get_db().execute(
        "SELECT * FROM provider_onboarding_events WHERE provider_profile_id=? ORDER BY created_at DESC LIMIT ?",
        (int(profile_id), limit),
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        except json.JSONDecodeError:
            item["metadata"] = {}
        result.append(item)
    return result


def _required_fields(role: str) -> list[str]:
    if role == "doctor":
        return ["specialty", "qualifications", "license_identifier", "address", "city", "state", "public_phone"]
    if role == "hospital":
        return ["organization", "license_identifier", "address", "city", "state", "public_phone"]
    if role == "pharmacy":
        return ["organization", "license_identifier", "address", "city", "state", "public_phone"]
    return ["address", "city", "state", "public_phone"]


def _connection_state(profile: dict) -> dict:
    return {
        "zendoc_profile": "connected",
        "zendoc_booking": "connected" if profile["provider_type"] in {"doctor", "hospital"} else "not_applicable_or_separate_workflow",
        "external_hospital_system": "integration_required",
        "payments": "integration_required",
        "government_registry_live_check": "integration_required",
    }


def _record_event(
    profile_id: int,
    event_type: str,
    status: str,
    message: str,
    *,
    actor_id: int | None,
    metadata: dict | None = None,
):
    get_db().execute(
        """
        INSERT INTO provider_onboarding_events
        (provider_profile_id,event_type,status,message,actor_id,metadata_json,created_at)
        VALUES (?,?,?,?,?,?,?)
        """,
        (
            int(profile_id), event_type, status, str(message)[:1000], actor_id,
            json.dumps(metadata or {}, sort_keys=True, separators=(",", ":")),
            now_iso(),
        ),
    )


def _user_id(actor: Any) -> int:
    try:
        return int(actor["id"])
    except Exception:
        return 0

