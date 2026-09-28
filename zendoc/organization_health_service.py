"""Organization health programs, benefits and privacy-preserving aggregate analytics."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .db import get_db, now_iso
from .organization_service import (
    active_membership,
    approve_membership,
    get_organization,
    request_membership,
)
from .security import is_owner


BENEFIT_TYPES = {
    "preventive_care",
    "doctor_consultation",
    "diagnostics",
    "mental_wellness",
    "pharmacy_support",
    "emergency_support",
    "home_health",
    "custom",
}
PRIVACY_MINIMUM_GROUP_SIZE = 5


def ensure_organization_health_schema():
    get_db().executescript(
        """
        CREATE TABLE IF NOT EXISTS organization_benefit_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL REFERENCES provider_organizations(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            benefit_type TEXT NOT NULL,
            description TEXT,
            coverage_note TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_org_benefit_plans_org
            ON organization_benefit_plans(organization_id,active,benefit_type);
        """
    )


def _value(actor: Any, key: str, default=None):
    if actor is None:
        return default
    if hasattr(actor, "keys") and key in actor.keys():
        return actor[key]
    return actor.get(key, default) if isinstance(actor, dict) else default


def _user_id(actor: Any) -> int:
    return int(_value(actor, "id", 0) or 0)


def _clean(value: Any, limit: int) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def _is_manager(actor: Any, organization_id: int) -> bool:
    if is_owner(actor):
        return True
    membership = active_membership(_user_id(actor), int(organization_id))
    return bool(
        membership
        and str(membership.get("status") or "") == "active"
        and str(membership.get("membership_role") or "") in {"owner", "admin"}
    )


def require_organization_manager(actor: Any, organization_id: int) -> dict:
    organization = get_organization(int(organization_id))
    if not _is_manager(actor, int(organization_id)):
        raise PermissionError("Organization owner or admin access is required.")
    return organization


def require_organization_member(actor: Any, organization_id: int) -> dict:
    organization = get_organization(int(organization_id))
    if is_owner(actor):
        return organization
    membership = active_membership(_user_id(actor), int(organization_id))
    if not membership:
        raise PermissionError("An active organization membership is required.")
    return organization


def list_my_health_organizations(actor: Any) -> list[dict]:
    uid = _user_id(actor)
    if not uid:
        raise PermissionError("Authentication required.")
    db = get_db()
    if is_owner(actor):
        rows = db.execute(
            """
            SELECT po.*, 'owner' AS membership_role, 'active' AS membership_status
            FROM provider_organizations po
            WHERE po.active=1
            ORDER BY po.updated_at DESC,po.id DESC
            LIMIT 200
            """
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT po.*,om.membership_role,om.status AS membership_status
            FROM organization_memberships om
            JOIN provider_organizations po ON po.id=om.organization_id
            WHERE om.user_id=? AND po.active=1
            ORDER BY
              CASE om.status WHEN 'active' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END,
              po.updated_at DESC,po.id DESC
            """,
            (uid,),
        ).fetchall()
    return [dict(row) for row in rows]


def request_health_organization_membership(actor: Any, organization_uid: str) -> dict:
    clean_uid = _clean(organization_uid, 80)
    if not clean_uid:
        raise ValueError("Organization code is required.")
    row = get_db().execute(
        """
        SELECT * FROM provider_organizations
        WHERE organization_uid=? AND active=1
        """,
        (clean_uid,),
    ).fetchone()
    if not row:
        raise LookupError("Organization not found.")
    if str(row["verification_status"] or "").lower() != "verified":
        raise PermissionError("This organization is not verified for member enrollment.")
    return request_membership(actor, int(row["id"]), "member")


def list_organization_memberships(actor: Any, organization_id: int) -> list[dict]:
    require_organization_manager(actor, organization_id)
    rows = get_db().execute(
        """
        SELECT om.id,om.user_id,om.membership_role,om.status,om.created_at,om.updated_at,
               u.name,u.email,u.role AS account_role,u.active AS account_active
        FROM organization_memberships om
        JOIN users u ON u.id=om.user_id
        WHERE om.organization_id=?
        ORDER BY
          CASE om.status WHEN 'pending' THEN 0 WHEN 'active' THEN 1 ELSE 2 END,
          om.updated_at DESC,om.id DESC
        """,
        (int(organization_id),),
    ).fetchall()
    return [dict(row) for row in rows]


def review_organization_membership(actor: Any, membership_id: int, status: str) -> dict:
    return approve_membership(actor, int(membership_id), status)


def create_benefit_plan(actor: Any, organization_id: int, data: dict) -> dict:
    ensure_organization_health_schema()
    require_organization_manager(actor, organization_id)
    name = _clean(data.get("name"), 160)
    if not name:
        raise ValueError("Benefit name is required.")
    benefit_type = _clean(data.get("benefit_type") or "custom", 80).lower().replace(" ", "_")
    if benefit_type not in BENEFIT_TYPES:
        raise ValueError("Unsupported benefit type.")
    description = _clean(data.get("description"), 1200) or None
    coverage_note = _clean(data.get("coverage_note"), 1200) or None
    now = now_iso()
    cursor = get_db().execute(
        """
        INSERT INTO organization_benefit_plans
        (organization_id,name,benefit_type,description,coverage_note,active,created_by,created_at,updated_at)
        VALUES (?,?,?,?,?,1,?,?,?)
        """,
        (
            int(organization_id),
            name,
            benefit_type,
            description,
            coverage_note,
            _user_id(actor),
            now,
            now,
        ),
    )
    get_db().commit()
    return dict(get_db().execute(
        "SELECT * FROM organization_benefit_plans WHERE id=?",
        (int(cursor.lastrowid),),
    ).fetchone())


def list_benefit_plans(actor: Any, organization_id: int, *, include_inactive: bool = False) -> list[dict]:
    ensure_organization_health_schema()
    require_organization_member(actor, organization_id)
    clause = "" if include_inactive and _is_manager(actor, organization_id) else "AND active=1"
    rows = get_db().execute(
        f"""
        SELECT id,organization_id,name,benefit_type,description,coverage_note,active,created_at,updated_at
        FROM organization_benefit_plans
        WHERE organization_id=? {clause}
        ORDER BY active DESC,updated_at DESC,id DESC
        """,
        (int(organization_id),),
    ).fetchall()
    return [dict(row) for row in rows]


def set_benefit_plan_active(actor: Any, organization_id: int, benefit_id: int, active: bool) -> dict:
    ensure_organization_health_schema()
    require_organization_manager(actor, organization_id)
    cursor = get_db().execute(
        """
        UPDATE organization_benefit_plans
        SET active=?,updated_at=?
        WHERE id=? AND organization_id=?
        """,
        (1 if active else 0, now_iso(), int(benefit_id), int(organization_id)),
    )
    if int(cursor.rowcount or 0) != 1:
        get_db().rollback()
        raise LookupError("Organization benefit not found.")
    get_db().commit()
    return dict(get_db().execute(
        "SELECT * FROM organization_benefit_plans WHERE id=?",
        (int(benefit_id),),
    ).fetchone())


def organization_health_snapshot(actor: Any, organization_id: int, *, days: int = 30) -> dict:
    """Return manager-safe aggregate operational analytics only.

    No diagnoses, symptoms, records, messages, journal content, report text,
    medications, specialty choices or person-level healthcare activity are returned.
    Usage metrics are suppressed entirely for small groups to reduce re-identification risk.
    """
    ensure_organization_health_schema()
    organization = require_organization_manager(actor, organization_id)
    days = max(1, min(int(days or 30), 365))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    db = get_db()

    membership_rows = db.execute(
        """
        SELECT status,membership_role,user_id
        FROM organization_memberships
        WHERE organization_id=?
        """,
        (int(organization_id),),
    ).fetchall()
    status_counts: dict[str, int] = {}
    active_member_ids = []
    for row in membership_rows:
        status = str(row["status"] or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        if status == "active":
            active_member_ids.append(int(row["user_id"]))

    benefit_count = int(db.execute(
        "SELECT COUNT(*) c FROM organization_benefit_plans WHERE organization_id=? AND active=1",
        (int(organization_id),),
    ).fetchone()["c"] or 0)
    location_count = int(db.execute(
        "SELECT COUNT(*) c FROM organization_locations WHERE organization_id=? AND active=1",
        (int(organization_id),),
    ).fetchone()["c"] or 0)

    privacy_suppressed = len(active_member_ids) < PRIVACY_MINIMUM_GROUP_SIZE
    usage = None
    if not privacy_suppressed:
        placeholders = ",".join("?" for _ in active_member_ids)
        search_row = db.execute(
            f"""
            SELECT COUNT(*) total,
                   SUM(CASE WHEN useful_result=1 THEN 1 ELSE 0 END) useful,
                   COUNT(DISTINCT user_id) active_users
            FROM product_analytics_events
            WHERE event_type='healthcare_search'
              AND user_id IN ({placeholders})
              AND created_at>=?
            """,
            [*active_member_ids, cutoff],
        ).fetchone()
        appointment_rows = db.execute(
            f"""
            SELECT status,COUNT(*) c
            FROM appointments
            WHERE patient_id IN ({placeholders})
              AND created_at>=?
            GROUP BY status
            """,
            [*active_member_ids, cutoff],
        ).fetchall()
        appointment_status_counts = {
            str(row["status"]): int(row["c"] or 0)
            for row in appointment_rows
        }
        total_searches = int(search_row["total"] or 0)
        useful_searches = int(search_row["useful"] or 0)
        usage = {
            "active_members_with_search_activity": int(search_row["active_users"] or 0),
            "healthcare_searches": total_searches,
            "searches_with_results": useful_searches,
            "search_result_rate": round(useful_searches / total_searches, 4) if total_searches else None,
            "appointment_requests": sum(appointment_status_counts.values()),
            "completed_appointments": int(appointment_status_counts.get("completed", 0)),
        }

    return {
        "organization": {
            "id": int(organization["id"]),
            "organization_uid": organization["organization_uid"],
            "name": organization["name"],
            "organization_type": organization["organization_type"],
            "verification_status": organization["verification_status"],
        },
        "window_days": days,
        "membership": {
            "total": len(membership_rows),
            "active": len(active_member_ids),
            "status_counts": status_counts,
        },
        "active_benefit_plans": benefit_count,
        "active_locations": location_count,
        "privacy": {
            "minimum_group_size": PRIVACY_MINIMUM_GROUP_SIZE,
            "suppressed": privacy_suppressed,
            "reason": (
                f"Usage analytics require at least {PRIVACY_MINIMUM_GROUP_SIZE} active members."
                if privacy_suppressed
                else None
            ),
        },
        "usage": usage,
        "truth_notice": (
            "Organization analytics contain aggregate ZENDOC product activity only. "
            "They do not expose individual clinical records, diagnoses, symptoms, messages, journals or report content, "
            "and they must not be presented as employee health outcomes, productivity gains, insurer eligibility or clinical efficacy."
        ),
    }
