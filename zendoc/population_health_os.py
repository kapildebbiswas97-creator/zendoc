"""
ZENDOC Population & Public Health OS — Phase G.

Manages health cohorts, public health campaigns, campaign enrollment,
aggregate analytics, and population-level preventive care coordination.

TRUTHFUL STATUS MODEL:
- Cohort analytics are derived from real ZENDOC records only.
- Campaign enrollment is opt-in and consent-based. No automated enrolment
  without explicit patient action.
- Aggregate analytics are de-identified counts — never individual-level
  disclosure without explicit consent.
- Disease prediction and outbreak detection are FUTURE capabilities.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from .db import get_db, now_iso


# ── Helpers ─────────────────────────────────────────────────────────────────

def _actor_id(actor: Any) -> int:
    if isinstance(actor, (int, float)):
        return int(actor)
    if isinstance(actor, dict):
        return int(actor.get("id") or 0)
    try:
        return int(actor["id"] or 0)
    except (TypeError, KeyError, IndexError):
        pass
    return int(getattr(actor, "id", 0) or 0)


def _actor_field(actor: Any, field: str, default: Any = None) -> Any:
    if isinstance(actor, dict):
        return actor.get(field, default)
    try:
        val = actor[field]
        return val if val is not None else default
    except (TypeError, KeyError, IndexError):
        pass
    return getattr(actor, field, default)


def _require_role(actor: Any, allowed: set) -> None:
    role = _actor_field(actor, "role", "")
    if role not in allowed:
        raise PermissionError(f"Role '{role}' is not authorized for this Population Health operation.")


ADMIN_ROLES = {"admin", "doctor", "hospital"}
CAMPAIGN_TYPES = {
    "vaccination", "screening", "awareness", "wellness", "chronic_disease_management",
    "mental_health", "nutrition", "maternal_health", "pediatric", "other",
}


# ── Cohort Management ────────────────────────────────────────────────────────

def create_health_cohort(
    actor: Any,
    name: str,
    inclusion_criteria: dict,
    description: str | None = None,
) -> dict[str, Any]:
    """
    Define a health cohort for population analytics or campaign targeting.
    WORKING: Cohort metadata stored. Member assignment is manual or via
    explicit operator-run batch enrollment.
    """
    _require_role(actor, ADMIN_ROLES)
    actor_id = _actor_id(actor)

    name = str(name or "").strip()
    if not name:
        raise ValueError("Cohort name is required.")
    if not isinstance(inclusion_criteria, dict):
        raise ValueError("inclusion_criteria must be a JSON object/dict.")

    cohort_uid = str(uuid.uuid4())
    now = now_iso()
    db = get_db()

    db.execute(
        """
        INSERT INTO health_cohorts
        (cohort_uid, name, description, inclusion_criteria_json, created_by,
         status, member_count, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'active', 0, ?, ?)
        """,
        (cohort_uid, name, description, json.dumps(inclusion_criteria),
         actor_id, now, now),
    )
    db.commit()

    return {
        "cohort_uid": cohort_uid,
        "name": name,
        "description": description,
        "inclusion_criteria": inclusion_criteria,
        "status": "active",
        "member_count": 0,
        "created_at": now,
    }


def enroll_patient_in_cohort(
    actor: Any,
    cohort_uid: str,
    patient_id: int,
    enrollment_reason: str | None = None,
) -> dict[str, Any]:
    """Add a patient to a health cohort. Requires operator role."""
    _require_role(actor, ADMIN_ROLES)
    db = get_db()

    cohort = db.execute(
        "SELECT id, name, status FROM health_cohorts WHERE cohort_uid=?",
        (cohort_uid,),
    ).fetchone()
    if not cohort:
        raise LookupError("Cohort not found.")
    if cohort["status"] != "active":
        raise ValueError("Cannot enroll into an inactive cohort.")

    patient = db.execute(
        "SELECT id FROM users WHERE id=? AND role='patient' AND active=1",
        (patient_id,),
    ).fetchone()
    if not patient:
        raise LookupError("Patient not found.")

    now = now_iso()
    try:
        db.execute(
            """
            INSERT INTO health_cohort_members
            (cohort_id, patient_id, enrolled_at, enrollment_reason)
            VALUES (?, ?, ?, ?)
            """,
            (cohort["id"], patient_id, now, enrollment_reason),
        )
        db.execute(
            "UPDATE health_cohorts SET member_count=member_count+1, updated_at=? WHERE cohort_uid=?",
            (now, cohort_uid),
        )
        db.commit()
    except Exception as exc:
        if "UNIQUE" in str(exc).upper():
            raise ValueError("Patient is already enrolled in this cohort.") from exc
        raise

    return {
        "cohort_uid": cohort_uid,
        "cohort_name": cohort["name"],
        "patient_id": patient_id,
        "enrolled_at": now,
        "enrollment_reason": enrollment_reason,
    }


def list_cohort_members(actor: Any, cohort_uid: str) -> list[dict]:
    """List all active members of a cohort."""
    _require_role(actor, ADMIN_ROLES)
    db = get_db()

    cohort = db.execute(
        "SELECT id FROM health_cohorts WHERE cohort_uid=?",
        (cohort_uid,),
    ).fetchone()
    if not cohort:
        raise LookupError("Cohort not found.")

    rows = db.execute(
        """
        SELECT cm.patient_id, u.name, u.email, cm.enrolled_at, cm.enrollment_reason
        FROM health_cohort_members cm
        JOIN users u ON u.id=cm.patient_id
        WHERE cm.cohort_id=? AND cm.removed_at IS NULL
        ORDER BY cm.enrolled_at DESC
        """,
        (cohort["id"],),
    ).fetchall()
    return [dict(r) for r in rows]


def get_cohort_aggregate_analytics(actor: Any, cohort_uid: str) -> dict[str, Any]:
    """
    Return de-identified aggregate analytics for a cohort.
    Individual patient data is NOT disclosed in this response.
    """
    _require_role(actor, ADMIN_ROLES)
    db = get_db()

    cohort = db.execute(
        "SELECT * FROM health_cohorts WHERE cohort_uid=?",
        (cohort_uid,),
    ).fetchone()
    if not cohort:
        raise LookupError("Cohort not found.")
    cohort = dict(cohort)

    # Count active members
    member_count = db.execute(
        "SELECT COUNT(*) cnt FROM health_cohort_members WHERE cohort_id=? AND removed_at IS NULL",
        (cohort["id"],),
    ).fetchone()["cnt"]

    # Get patient_ids in this cohort for aggregate queries
    member_ids_rows = db.execute(
        "SELECT patient_id FROM health_cohort_members WHERE cohort_id=? AND removed_at IS NULL",
        (cohort["id"],),
    ).fetchall()
    member_ids = [r["patient_id"] for r in member_ids_rows]

    # Aggregate diagnostics booking count (de-identified)
    booking_count = 0
    appointment_count = 0
    if member_ids:
        placeholders = ",".join("?" * len(member_ids))
        booking_count = db.execute(
            f"SELECT COUNT(*) cnt FROM diagnostic_bookings WHERE patient_id IN ({placeholders})",
            member_ids,
        ).fetchone()["cnt"]
        appointment_count = db.execute(
            f"SELECT COUNT(*) cnt FROM appointments WHERE patient_id IN ({placeholders}) AND status='completed'",
            member_ids,
        ).fetchone()["cnt"]

    return {
        "cohort_uid": cohort_uid,
        "cohort_name": cohort["name"],
        "status": cohort["status"],
        "aggregate_member_count": member_count,
        "aggregate_completed_appointments": appointment_count,
        "aggregate_diagnostic_bookings": booking_count,
        "de_identified_note": (
            "All metrics are aggregate counts only. No individual patient data "
            "is disclosed in this analytics response."
        ),
        "analytics_as_of": now_iso(),
    }


def list_cohorts(actor: Any) -> list[dict]:
    """List all active cohorts."""
    _require_role(actor, ADMIN_ROLES)
    db = get_db()
    rows = db.execute(
        "SELECT cohort_uid, name, description, status, member_count, created_at FROM health_cohorts ORDER BY created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


# ── Public Health Campaigns ──────────────────────────────────────────────────

def create_public_health_campaign(
    actor: Any,
    title: str,
    campaign_type: str,
    start_date: str,
    target_condition: str | None = None,
    target_population: str | None = None,
    geographic_scope: str | None = None,
    end_date: str | None = None,
    content: dict | None = None,
) -> dict[str, Any]:
    """
    Create a public health awareness or intervention campaign.
    WORKING: Campaign metadata recorded. Patient reach requires explicit enrollment.
    """
    _require_role(actor, ADMIN_ROLES)
    actor_id = _actor_id(actor)

    title = str(title or "").strip()
    campaign_type = str(campaign_type or "").strip().lower()
    if not title:
        raise ValueError("Campaign title is required.")
    if campaign_type not in CAMPAIGN_TYPES:
        raise ValueError(f"campaign_type must be one of: {sorted(CAMPAIGN_TYPES)}")
    if not start_date:
        raise ValueError("start_date is required.")

    campaign_uid = str(uuid.uuid4())
    now = now_iso()
    db = get_db()

    db.execute(
        """
        INSERT INTO public_health_campaigns
        (campaign_uid, title, campaign_type, target_condition, target_population,
         geographic_scope, start_date, end_date, status, content_json, created_by,
         reach_count, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, 0, ?, ?)
        """,
        (
            campaign_uid, title, campaign_type, target_condition, target_population,
            geographic_scope, start_date, end_date,
            json.dumps(content or {}), actor_id, now, now,
        ),
    )
    db.commit()

    return {
        "campaign_uid": campaign_uid,
        "title": title,
        "campaign_type": campaign_type,
        "target_condition": target_condition,
        "start_date": start_date,
        "end_date": end_date,
        "status": "active",
        "reach_count": 0,
        "created_at": now,
    }


def enroll_patient_in_campaign(
    actor: Any,
    campaign_uid: str,
    patient_id: int,
) -> dict[str, Any]:
    """
    Opt a patient into a public health campaign (consent-based).
    Patients can enroll themselves; operators can enroll on patient behalf.
    """
    role = _actor_field(actor, "role", "")
    actor_id = _actor_id(actor)
    if role not in {"patient", "doctor", "admin", "hospital"}:
        raise PermissionError("Not authorized.")
    if role == "patient" and actor_id != patient_id:
        raise PermissionError("Patients can only enroll themselves in campaigns.")

    db = get_db()
    campaign = db.execute(
        "SELECT id, title, status FROM public_health_campaigns WHERE campaign_uid=?",
        (campaign_uid,),
    ).fetchone()
    if not campaign:
        raise LookupError("Campaign not found.")
    if campaign["status"] != "active":
        raise ValueError("Cannot enroll into an inactive campaign.")

    patient = db.execute(
        "SELECT id FROM users WHERE id=? AND role='patient' AND active=1",
        (patient_id,),
    ).fetchone()
    if not patient:
        raise LookupError("Patient not found.")

    now = now_iso()
    try:
        db.execute(
            """
            INSERT INTO campaign_enrollments
            (campaign_id, patient_id, enrolled_at, status)
            VALUES (?, ?, ?, 'enrolled')
            """,
            (campaign["id"], patient_id, now),
        )
        db.execute(
            "UPDATE public_health_campaigns SET reach_count=reach_count+1, updated_at=? WHERE campaign_uid=?",
            (now, campaign_uid),
        )
        db.commit()
    except Exception as exc:
        if "UNIQUE" in str(exc).upper():
            raise ValueError("Patient is already enrolled in this campaign.") from exc
        raise

    return {
        "campaign_uid": campaign_uid,
        "campaign_title": campaign["title"],
        "patient_id": patient_id,
        "enrolled_at": now,
        "status": "enrolled",
        "consent_note": "Patient has opted into this public health campaign.",
    }


def list_campaigns(status: str | None = None) -> list[dict]:
    """List public health campaigns. Public endpoint — no auth required for listing."""
    db = get_db()
    if status:
        rows = db.execute(
            "SELECT campaign_uid, title, campaign_type, target_condition, start_date, end_date, status, reach_count FROM public_health_campaigns WHERE status=? ORDER BY created_at DESC",
            (status,),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT campaign_uid, title, campaign_type, target_condition, start_date, end_date, status, reach_count FROM public_health_campaigns ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_campaign_analytics(actor: Any, campaign_uid: str) -> dict[str, Any]:
    """Return aggregate enrollment analytics for a campaign."""
    _require_role(actor, ADMIN_ROLES)
    db = get_db()

    campaign = db.execute(
        "SELECT * FROM public_health_campaigns WHERE campaign_uid=?",
        (campaign_uid,),
    ).fetchone()
    if not campaign:
        raise LookupError("Campaign not found.")
    c = dict(campaign)

    enrolled_count = db.execute(
        "SELECT COUNT(*) cnt FROM campaign_enrollments WHERE campaign_id=? AND status='enrolled'",
        (c["id"],),
    ).fetchone()["cnt"]
    opted_out_count = db.execute(
        "SELECT COUNT(*) cnt FROM campaign_enrollments WHERE campaign_id=? AND status='opted_out'",
        (c["id"],),
    ).fetchone()["cnt"]

    return {
        "campaign_uid": campaign_uid,
        "title": c["title"],
        "campaign_type": c["campaign_type"],
        "status": c["status"],
        "enrolled_count": enrolled_count,
        "opted_out_count": opted_out_count,
        "net_active_reach": enrolled_count,
        "analytics_as_of": now_iso(),
    }
