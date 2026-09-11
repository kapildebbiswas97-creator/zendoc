"""Deterministic preventive-care planning with explicit provenance.

ZENDOC does not invent clinical screening or vaccination intervals here. Every
preventive item must come from an explicit patient/provider due date or from an
approved, immutable medical-knowledge document.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from .db import get_db, now_iso
from .health_access import authorize_patient


PREVENTIVE_CATEGORIES = (
    "screening",
    "vaccination",
    "routine_checkup",
    "dental",
    "vision",
    "lifestyle",
    "other",
)
ACTIVE = "ACTIVE"
COMPLETED = "COMPLETED"
DISMISSED = "DISMISSED"


def _value(actor, key, default=None):
    if actor is None:
        return default
    if hasattr(actor, "keys") and key in actor.keys():
        return actor[key]
    return actor.get(key, default) if isinstance(actor, dict) else default


def ensure_preventive_care_schema():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS preventive_care_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_uid TEXT NOT NULL UNIQUE,
            patient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            due_at TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_ref TEXT,
            guideline_document_uid TEXT,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            completed_at TEXT,
            dismissed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_preventive_patient_due
            ON preventive_care_plans(patient_id, status, due_at);
        CREATE INDEX IF NOT EXISTS idx_preventive_guideline
            ON preventive_care_plans(guideline_document_uid, patient_id);
        """
    )


def _clean_title(value):
    title = " ".join(str(value or "").split())
    if not title:
        raise ValueError("title is required.")
    if len(title) > 200:
        raise ValueError("title must be at most 200 characters.")
    return title


def _category(value):
    category = str(value or "other").strip().lower().replace(" ", "_").replace("-", "_")
    if category not in PREVENTIVE_CATEGORIES:
        raise ValueError("Unsupported preventive-care category.")
    return category


def _aware_iso(value, label="due_at"):
    if not value:
        raise ValueError(f"{label} is required.")
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} must be a valid ISO date or date-time.") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def _resolve_source(actor, data):
    role = str(_value(actor, "role", "") or "")
    requested = str(data.get("source_type") or "").strip().lower()
    if requested == "guideline_grounded":
        document_uid = str(data.get("guideline_document_uid") or "").strip()
        if not document_uid:
            raise ValueError("guideline_document_uid is required for guideline-grounded preventive plans.")
        from .medical_knowledge_documents import get_approved_medical_knowledge_document

        document = get_approved_medical_knowledge_document(document_uid)
        return "guideline_grounded", document_uid, document
    if role == "patient":
        if requested and requested != "patient_entered":
            raise PermissionError("Patients may create only patient-entered preventive plans.")
        return "patient_entered", None, None
    if role in {"doctor", "hospital"}:
        if requested and requested != "provider_entered":
            raise PermissionError("Providers may create only provider-entered preventive plans unless an approved guideline document is supplied.")
        return "provider_entered", None, None
    if role == "admin":
        if requested and requested != "owner_entered":
            raise PermissionError("Owner-entered preventive plans must use source_type=owner_entered unless an approved guideline document is supplied.")
        return "owner_entered", None, None
    raise PermissionError("This role cannot create preventive-care plans.")


def create_preventive_plan(actor, data, patient_id=None):
    ensure_preventive_care_schema()
    target_id = authorize_patient(actor, patient_id, "timeline")
    title = _clean_title(data.get("title"))
    category = _category(data.get("category"))
    due_at = _aware_iso(data.get("due_at"))
    source_type, guideline_document_uid, guideline_document = _resolve_source(actor, data)
    source_ref = " ".join(str(data.get("source_ref") or "").split())[:500] or None
    if source_type == "guideline_grounded":
        source_ref = source_ref or guideline_document.get("document_url")
    now = now_iso()
    plan_uid = f"preventive_{uuid.uuid4().hex}"
    cursor = get_db().execute(
        """
        INSERT INTO preventive_care_plans
        (plan_uid,patient_id,title,category,due_at,source_type,source_ref,guideline_document_uid,status,created_by,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            plan_uid,
            target_id,
            title,
            category,
            due_at,
            source_type,
            source_ref,
            guideline_document_uid,
            ACTIVE,
            int(_value(actor, "id", 0) or 0),
            now,
            now,
        ),
    )
    get_db().commit()
    return get_preventive_plan(actor, int(cursor.lastrowid), patient_id=target_id)


def _due_state(item, now=None):
    if item["status"] == COMPLETED:
        return "COMPLETED"
    if item["status"] == DISMISSED:
        return "DISMISSED"
    now = now or datetime.now(timezone.utc)
    due = datetime.fromisoformat(str(item["due_at"]).replace("Z", "+00:00"))
    if due < now:
        return "OVERDUE"
    if due <= now + timedelta(days=30):
        return "DUE_SOON"
    return "UPCOMING"


def _serialize(row):
    item = dict(row)
    item["due_state"] = _due_state(item)
    item["medical_recommendation"] = False
    item["notice"] = (
        "This due date is recorded provenance, not an automatically generated clinical recommendation."
        if item["source_type"] != "guideline_grounded"
        else "This due date references an explicitly approved medical-knowledge document; clinical applicability still depends on the recorded plan context."
    )
    return item


def get_preventive_plan(actor, plan_id, patient_id=None):
    ensure_preventive_care_schema()
    row = get_db().execute("SELECT * FROM preventive_care_plans WHERE id=?", (int(plan_id),)).fetchone()
    if not row:
        raise LookupError("Preventive-care plan not found.")
    target_id = authorize_patient(actor, patient_id or int(row["patient_id"]), "timeline")
    if int(row["patient_id"]) != int(target_id):
        raise PermissionError("Preventive-care plan does not belong to the authorized patient.")
    return _serialize(row)


def list_preventive_plans(actor, patient_id=None, status=None, limit=100):
    ensure_preventive_care_schema()
    target_id = authorize_patient(actor, patient_id, "timeline")
    limit = max(1, min(int(limit or 100), 250))
    params = [target_id]
    where = "patient_id=?"
    if status:
        normalized = str(status).strip().upper()
        if normalized not in {ACTIVE, COMPLETED, DISMISSED}:
            raise ValueError("status must be ACTIVE, COMPLETED, or DISMISSED.")
        where += " AND status=?"
        params.append(normalized)
    params.append(limit)
    rows = get_db().execute(
        f"SELECT * FROM preventive_care_plans WHERE {where} ORDER BY due_at ASC, id ASC LIMIT ?",
        tuple(params),
    ).fetchall()
    return [_serialize(row) for row in rows]


def update_preventive_plan_status(actor, plan_id, action, patient_id=None):
    ensure_preventive_care_schema()
    row = get_db().execute("SELECT * FROM preventive_care_plans WHERE id=?", (int(plan_id),)).fetchone()
    if not row:
        raise LookupError("Preventive-care plan not found.")
    target_id = authorize_patient(actor, patient_id or int(row["patient_id"]), "timeline")
    if int(row["patient_id"]) != int(target_id):
        raise PermissionError("Preventive-care plan does not belong to the authorized patient.")
    normalized = str(action or "").strip().lower()
    if normalized not in {"complete", "dismiss"}:
        raise ValueError("action must be complete or dismiss.")
    if row["status"] != ACTIVE:
        raise ValueError("Only active preventive-care plans can be completed or dismissed.")
    now = now_iso()
    if normalized == "complete":
        get_db().execute(
            "UPDATE preventive_care_plans SET status=?, completed_at=?, updated_at=? WHERE id=?",
            (COMPLETED, now, now, int(plan_id)),
        )
    else:
        get_db().execute(
            "UPDATE preventive_care_plans SET status=?, dismissed_at=?, updated_at=? WHERE id=?",
            (DISMISSED, now, now, int(plan_id)),
        )
    get_db().commit()
    return get_preventive_plan(actor, int(plan_id), patient_id=target_id)
