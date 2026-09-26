"""Controlled-beta feedback and cohort operations.

This module stores only minimum-necessary product/operational context. It must
not be used as a substitute for Health Memory or as a place to copy clinical
records, symptom narratives, prescriptions, or other unnecessary health data.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from .db import get_db, now_iso
from .security import assert_owner


FEEDBACK_CATEGORIES = {"bug", "usability", "data", "integration", "access", "other"}
FEEDBACK_SEVERITIES = {"low", "medium", "high", "critical"}
FEEDBACK_STATUSES = {"NEW", "INVESTIGATING", "PLANNED", "FIXED", "WONT_FIX"}
COHORT_ENTITY_TYPES = {"user", "provider", "organization"}


def ensure_pilot_operations_schema() -> None:
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS pilot_feedback_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            role TEXT,
            page_path TEXT NOT NULL,
            endpoint TEXT,
            feature TEXT NOT NULL,
            category TEXT NOT NULL,
            severity TEXT NOT NULL,
            message TEXT NOT NULL,
            application_version TEXT,
            release_channel TEXT,
            technical_context_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'NEW',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_pilot_feedback_status_time
            ON pilot_feedback_reports(status, created_at);
        CREATE INDEX IF NOT EXISTS idx_pilot_feedback_severity_time
            ON pilot_feedback_reports(severity, created_at);
        CREATE INDEX IF NOT EXISTS idx_pilot_feedback_feature_time
            ON pilot_feedback_reports(feature, created_at);
        CREATE INDEX IF NOT EXISTS idx_pilot_feedback_user_time
            ON pilot_feedback_reports(user_id, created_at);

        CREATE TABLE IF NOT EXISTS pilot_cohort_memberships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_id INTEGER NOT NULL,
            cohort_label TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(entity_type, entity_id, cohort_label)
        );
        CREATE INDEX IF NOT EXISTS idx_pilot_cohort_entity
            ON pilot_cohort_memberships(entity_type, entity_id, active);
        CREATE INDEX IF NOT EXISTS idx_pilot_cohort_label
            ON pilot_cohort_memberships(cohort_label, active);
        """
    )


def _value(actor: Any, key: str, default=None):
    if actor is None:
        return default
    if hasattr(actor, "keys") and key in actor.keys():
        return actor[key]
    if isinstance(actor, dict):
        return actor.get(key, default)
    return default


def _clean_text(value, *, maximum: int, required: bool = False, field: str = "Value") -> str:
    text = " ".join(str(value or "").strip().split())
    if required and not text:
        raise ValueError(f"{field} is required.")
    return text[:maximum]


def _clean_message(value) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("Feedback message is required.")
    if len(text) > 2000:
        raise ValueError("Feedback message must be 2000 characters or fewer.")
    return text


def _clean_page_path(value) -> str:
    value = str(value or "/").strip()
    if not value.startswith("/") or value.startswith("//"):
        return "/"
    # Store only the route path, never a query string that could contain
    # identifiers or user-entered health/search content.
    return value.split("?", 1)[0][:240]


def _clean_choice(value, allowed: set[str], *, default: str, upper: bool = False) -> str:
    clean = str(value or default).strip()
    clean = clean.upper() if upper else clean.lower()
    if clean not in allowed:
        raise ValueError("Unsupported feedback value.")
    return clean


def anonymized_technical_context(*, user_agent: str | None, method: str, endpoint: str | None) -> dict:
    ua_hash = None
    if user_agent:
        ua_hash = hashlib.sha256(user_agent.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return {
        "request_method": str(method or "GET").upper()[:12],
        "endpoint": str(endpoint or "")[:160] or None,
        "user_agent_hash": ua_hash,
    }


def create_feedback_report(
    actor: Any,
    data: dict,
    *,
    endpoint: str | None,
    technical_context: dict,
    application_version: str | None,
    release_channel: str | None,
) -> dict:
    ensure_pilot_operations_schema()
    user_id = int(_value(actor, "id", 0) or 0)
    if not user_id:
        raise PermissionError("Authentication is required to submit feedback.")

    role = _clean_text(_value(actor, "role"), maximum=40)
    page_path = _clean_page_path(data.get("page_path"))
    feature = _clean_text(data.get("feature"), maximum=120, required=True, field="Feature")
    category = _clean_choice(data.get("category"), FEEDBACK_CATEGORIES, default="other")
    severity = _clean_choice(data.get("severity"), FEEDBACK_SEVERITIES, default="medium")
    message = _clean_message(data.get("message"))
    now = now_iso()

    cursor = get_db().execute(
        """
        INSERT INTO pilot_feedback_reports
        (user_id,role,page_path,endpoint,feature,category,severity,message,
         application_version,release_channel,technical_context_json,status,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,'NEW',?,?)
        """,
        (
            user_id,
            role or None,
            page_path,
            _clean_text(endpoint, maximum=160) or None,
            feature,
            category,
            severity,
            message,
            _clean_text(application_version, maximum=120) or None,
            _clean_text(release_channel, maximum=40) or None,
            json.dumps(technical_context or {}, sort_keys=True, separators=(",", ":")),
            now,
            now,
        ),
    )
    feedback_id = int(cursor.lastrowid)
    get_db().execute(
        "INSERT INTO audit_logs (actor_id,action,entity_type,entity_id,created_at) VALUES (?,?,?,?,?)",
        (user_id, "pilot_feedback.create", "pilot_feedback_report", str(feedback_id), now),
    )
    get_db().commit()
    return dict(get_db().execute(
        "SELECT * FROM pilot_feedback_reports WHERE id=?", (feedback_id,)
    ).fetchone())


def list_feedback_reports(actor: Any, filters: dict | None = None) -> list[dict]:
    assert_owner(actor)
    ensure_pilot_operations_schema()
    filters = filters or {}
    clauses = []
    params: list[Any] = []

    role = _clean_text(filters.get("role"), maximum=40)
    feature = _clean_text(filters.get("feature"), maximum=120)
    severity = str(filters.get("severity") or "").strip().lower()
    status = str(filters.get("status") or "").strip().upper()
    date_from = _clean_text(filters.get("date_from"), maximum=32)
    date_to = _clean_text(filters.get("date_to"), maximum=32)

    if role:
        clauses.append("role=?")
        params.append(role)
    if feature:
        clauses.append("feature=?")
        params.append(feature)
    if severity:
        if severity not in FEEDBACK_SEVERITIES:
            raise ValueError("Invalid severity filter.")
        clauses.append("severity=?")
        params.append(severity)
    if status:
        if status not in FEEDBACK_STATUSES:
            raise ValueError("Invalid status filter.")
        clauses.append("status=?")
        params.append(status)
    if date_from:
        clauses.append("created_at>=?")
        params.append(f"{date_from}T00:00:00")
    if date_to:
        clauses.append("created_at<=?")
        params.append(f"{date_to}T23:59:59.999999")

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = get_db().execute(
        """
        SELECT f.*, u.name user_name, u.email user_email
        FROM pilot_feedback_reports f
        LEFT JOIN users u ON u.id=f.user_id
        """ + where + " ORDER BY f.created_at DESC, f.id DESC LIMIT 500",
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def update_feedback_status(actor: Any, feedback_id: int, status: str) -> dict:
    assert_owner(actor)
    ensure_pilot_operations_schema()
    clean_status = str(status or "").strip().upper()
    if clean_status not in FEEDBACK_STATUSES:
        raise ValueError("Invalid feedback status.")
    db = get_db()
    row = db.execute("SELECT id FROM pilot_feedback_reports WHERE id=?", (int(feedback_id),)).fetchone()
    if not row:
        raise LookupError("Feedback report not found.")
    now = now_iso()
    db.execute(
        "UPDATE pilot_feedback_reports SET status=?,updated_at=? WHERE id=?",
        (clean_status, now, int(feedback_id)),
    )
    db.execute(
        "INSERT INTO audit_logs (actor_id,action,entity_type,entity_id,created_at) VALUES (?,?,?,?,?)",
        (int(_value(actor, "id")), "pilot_feedback.status_update", "pilot_feedback_report", str(feedback_id), now),
    )
    db.commit()
    return dict(db.execute("SELECT * FROM pilot_feedback_reports WHERE id=?", (int(feedback_id),)).fetchone())


def _entity_exists(entity_type: str, entity_id: int) -> bool:
    db = get_db()
    queries = {
        "user": "SELECT 1 FROM users WHERE id=?",
        "provider": "SELECT 1 FROM provider_profiles WHERE id=?",
        "organization": "SELECT 1 FROM provider_organizations WHERE id=?",
    }
    return bool(db.execute(queries[entity_type], (int(entity_id),)).fetchone())


def assign_cohort(actor: Any, *, entity_type: str, entity_id: int, cohort_label: str) -> dict:
    assert_owner(actor)
    ensure_pilot_operations_schema()
    entity_type = str(entity_type or "").strip().lower()
    if entity_type not in COHORT_ENTITY_TYPES:
        raise ValueError("Invalid cohort entity type.")
    entity_id = int(entity_id)
    if not _entity_exists(entity_type, entity_id):
        raise LookupError("Cohort entity not found.")
    label = _clean_text(cohort_label, maximum=80, required=True, field="Cohort label")
    now = now_iso()
    db = get_db()
    existing = db.execute(
        "SELECT id FROM pilot_cohort_memberships WHERE entity_type=? AND entity_id=? AND cohort_label=?",
        (entity_type, entity_id, label),
    ).fetchone()
    if existing:
        db.execute(
            "UPDATE pilot_cohort_memberships SET active=1,updated_at=?,created_by=? WHERE id=?",
            (now, int(_value(actor, "id")), int(existing["id"])),
        )
        membership_id = int(existing["id"])
    else:
        cursor = db.execute(
            """
            INSERT INTO pilot_cohort_memberships
            (entity_type,entity_id,cohort_label,active,created_by,created_at,updated_at)
            VALUES (?,?,?,1,?,?,?)
            """,
            (entity_type, entity_id, label, int(_value(actor, "id")), now, now),
        )
        membership_id = int(cursor.lastrowid)
    db.execute(
        "INSERT INTO audit_logs (actor_id,action,entity_type,entity_id,created_at) VALUES (?,?,?,?,?)",
        (int(_value(actor, "id")), "pilot_cohort.assign", entity_type, str(entity_id), now),
    )
    db.commit()
    return dict(db.execute(
        "SELECT * FROM pilot_cohort_memberships WHERE id=?", (membership_id,)
    ).fetchone())


def deactivate_cohort_membership(actor: Any, membership_id: int) -> None:
    assert_owner(actor)
    ensure_pilot_operations_schema()
    db = get_db()
    row = db.execute("SELECT * FROM pilot_cohort_memberships WHERE id=?", (int(membership_id),)).fetchone()
    if not row:
        raise LookupError("Cohort membership not found.")
    now = now_iso()
    db.execute(
        "UPDATE pilot_cohort_memberships SET active=0,updated_at=? WHERE id=?",
        (now, int(membership_id)),
    )
    db.execute(
        "INSERT INTO audit_logs (actor_id,action,entity_type,entity_id,created_at) VALUES (?,?,?,?,?)",
        (int(_value(actor, "id")), "pilot_cohort.remove", str(row["entity_type"]), str(row["entity_id"]), now),
    )
    db.commit()


def _labels_by_entity() -> dict[tuple[str, int], list[dict]]:
    rows = get_db().execute(
        """
        SELECT id,entity_type,entity_id,cohort_label
        FROM pilot_cohort_memberships
        WHERE active=1
        ORDER BY cohort_label,id
        """
    ).fetchall()
    result: dict[tuple[str, int], list[dict]] = {}
    for row in rows:
        key = (str(row["entity_type"]), int(row["entity_id"]))
        result.setdefault(key, []).append(dict(row))
    return result


def cohort_admin_snapshot(actor: Any) -> dict:
    assert_owner(actor)
    ensure_pilot_operations_schema()
    db = get_db()
    labels = _labels_by_entity()

    users = []
    for row in db.execute(
        "SELECT id,name,email,role,active,created_at FROM users ORDER BY created_at DESC,id DESC"
    ).fetchall():
        item = dict(row)
        item["account_state"] = "active" if int(row["active"] or 0) == 1 else "suspended"
        item["cohorts"] = labels.get(("user", int(row["id"])), [])
        users.append(item)

    providers = []
    for row in db.execute(
        """
        SELECT p.id,p.user_id,p.provider_type,p.verification_status,p.updated_at,
               u.name,u.email,u.active
        FROM provider_profiles p
        JOIN users u ON u.id=p.user_id
        ORDER BY p.updated_at DESC,p.id DESC
        """
    ).fetchall():
        item = dict(row)
        item["cohorts"] = labels.get(("provider", int(row["id"])), [])
        providers.append(item)

    organizations = []
    for row in db.execute(
        """
        SELECT id,name,organization_type,verification_status,active,created_at
        FROM provider_organizations
        ORDER BY created_at DESC,id DESC
        """
    ).fetchall():
        item = dict(row)
        item["cohorts"] = labels.get(("organization", int(row["id"])), [])
        organizations.append(item)

    invitations = []
    try:
        invitation_rows = db.execute(
            """
            SELECT id,email,role,invited_name,expires_at,accepted_at,revoked_at,created_at
            FROM provider_invitations
            ORDER BY created_at DESC,id DESC
            LIMIT 200
            """
        ).fetchall()
        now = datetime.now(timezone.utc)
        for row in invitation_rows:
            item = dict(row)
            if row["revoked_at"]:
                state = "revoked"
            elif row["accepted_at"]:
                state = "registered"
            else:
                try:
                    expires = datetime.fromisoformat(str(row["expires_at"]))
                    if expires.tzinfo is None:
                        expires = expires.replace(tzinfo=timezone.utc)
                    state = "expired" if expires < now else "invited"
                except (TypeError, ValueError):
                    state = "invited"
            item["state"] = state
            invitations.append(item)
    except Exception:
        invitations = []

    return {
        "users": users,
        "providers": providers,
        "organizations": organizations,
        "provider_invitations": invitations,
    }
