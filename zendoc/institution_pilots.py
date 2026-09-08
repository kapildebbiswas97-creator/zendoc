"""Owner-managed institution pilot pipeline for ZENDOC startup operations."""
from __future__ import annotations

import json
import uuid
from typing import Any

from .db import get_db, now_iso
from .security import assert_owner


PILOT_STATUSES = {"lead", "proposed", "active", "paused", "completed", "converted", "declined"}
COMMERCIAL_STATUSES = {"none", "loi", "contract", "paid"}
MILESTONE_STATUSES = {"planned", "in_progress", "completed", "blocked", "cancelled"}
USAGE_SOURCE_TYPES = {"owner_entered_observed", "system_derived"}


def create_institution_pilot(actor: Any, data: dict) -> dict:
    assert_owner(actor)
    organization_name = str(data.get("organization_name") or "").strip()
    organization_type = str(data.get("organization_type") or "").strip().lower()
    if not organization_name:
        raise ValueError("organization_name is required.")
    if not organization_type:
        raise ValueError("organization_type is required.")

    status = str(data.get("status") or "lead").strip().lower()
    commercial = str(data.get("commercial_status") or "none").strip().lower()
    if status not in PILOT_STATUSES:
        raise ValueError("Unsupported pilot status.")
    if commercial not in COMMERCIAL_STATUSES:
        raise ValueError("Unsupported commercial status.")

    target_users = _optional_nonnegative_int(data.get("target_users"))
    target_provider_seats = _optional_nonnegative_int(data.get("target_provider_seats"))
    monthly_value = _optional_nonnegative_float(data.get("monthly_value_inr"))
    now = now_iso()
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO institution_pilots
        (pilot_uid,organization_name,organization_type,contact_name,contact_email,contact_phone,
         state,district,status,commercial_status,start_date,end_date,target_users,target_provider_seats,
         agreed_features_json,success_metrics_json,next_action,next_action_due,monthly_value_inr,notes,
         created_by,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            f"pilot_{uuid.uuid4().hex[:20]}",
            organization_name,
            organization_type,
            _clean(data.get("contact_name"), 200),
            _clean(data.get("contact_email"), 320),
            _clean(data.get("contact_phone"), 80),
            _clean(data.get("state"), 120),
            _clean(data.get("district"), 120),
            status,
            commercial,
            _clean(data.get("start_date"), 40),
            _clean(data.get("end_date"), 40),
            target_users,
            target_provider_seats,
            json.dumps(_list_value(data.get("agreed_features")), ensure_ascii=False, sort_keys=True),
            json.dumps(_list_value(data.get("success_metrics")), ensure_ascii=False, sort_keys=True),
            _clean(data.get("next_action"), 500),
            _clean(data.get("next_action_due"), 40),
            monthly_value,
            _clean(data.get("notes"), 2000),
            int(actor["id"]),
            now,
            now,
        ),
    )
    pilot_id = int(cursor.lastrowid)
    _event(pilot_id, "pilot_created", status, "Institution pilot created.", int(actor["id"]))
    db.commit()
    return get_institution_pilot(pilot_id)


def update_institution_pilot(actor: Any, pilot_id: int, data: dict) -> dict:
    assert_owner(actor)
    pilot = get_institution_pilot(pilot_id)
    status = str(data.get("status", pilot["status"]) or "").strip().lower()
    commercial = str(data.get("commercial_status", pilot["commercial_status"]) or "").strip().lower()
    if status not in PILOT_STATUSES:
        raise ValueError("Unsupported pilot status.")
    if commercial not in COMMERCIAL_STATUSES:
        raise ValueError("Unsupported commercial status.")

    merged = {
        "organization_name": _clean(data.get("organization_name", pilot["organization_name"]), 300),
        "organization_type": _clean(data.get("organization_type", pilot["organization_type"]), 120),
        "contact_name": _clean(data.get("contact_name", pilot["contact_name"]), 200),
        "contact_email": _clean(data.get("contact_email", pilot["contact_email"]), 320),
        "contact_phone": _clean(data.get("contact_phone", pilot["contact_phone"]), 80),
        "state": _clean(data.get("state", pilot["state"]), 120),
        "district": _clean(data.get("district", pilot["district"]), 120),
        "start_date": _clean(data.get("start_date", pilot["start_date"]), 40),
        "end_date": _clean(data.get("end_date", pilot["end_date"]), 40),
        "target_users": _optional_nonnegative_int(data.get("target_users", pilot["target_users"])),
        "target_provider_seats": _optional_nonnegative_int(data.get("target_provider_seats", pilot["target_provider_seats"])),
        "next_action": _clean(data.get("next_action", pilot["next_action"]), 500),
        "next_action_due": _clean(data.get("next_action_due", pilot["next_action_due"]), 40),
        "monthly_value_inr": _optional_nonnegative_float(data.get("monthly_value_inr", pilot["monthly_value_inr"])),
        "notes": _clean(data.get("notes", pilot["notes"]), 2000),
        "agreed_features": _list_value(data.get("agreed_features", pilot["agreed_features"])),
        "success_metrics": _list_value(data.get("success_metrics", pilot["success_metrics"])),
    }
    if not merged["organization_name"] or not merged["organization_type"]:
        raise ValueError("organization_name and organization_type are required.")

    db = get_db()
    now = now_iso()
    db.execute(
        """
        UPDATE institution_pilots
        SET organization_name=?,organization_type=?,contact_name=?,contact_email=?,contact_phone=?,
            state=?,district=?,status=?,commercial_status=?,start_date=?,end_date=?,target_users=?,
            target_provider_seats=?,agreed_features_json=?,success_metrics_json=?,next_action=?,
            next_action_due=?,monthly_value_inr=?,notes=?,updated_at=?
        WHERE id=?
        """,
        (
            merged["organization_name"], merged["organization_type"], merged["contact_name"],
            merged["contact_email"], merged["contact_phone"], merged["state"], merged["district"],
            status, commercial, merged["start_date"], merged["end_date"], merged["target_users"],
            merged["target_provider_seats"], json.dumps(merged["agreed_features"], ensure_ascii=False, sort_keys=True),
            json.dumps(merged["success_metrics"], ensure_ascii=False, sort_keys=True),
            merged["next_action"], merged["next_action_due"], merged["monthly_value_inr"], merged["notes"],
            now, int(pilot_id),
        ),
    )
    if status != pilot["status"] or commercial != pilot["commercial_status"]:
        _event(
            int(pilot_id),
            "status_updated",
            status,
            f"Pilot status={status}, commercial_status={commercial}.",
            int(actor["id"]),
        )
    db.commit()
    return get_institution_pilot(pilot_id)


def create_pilot_milestone(actor: Any, pilot_id: int, data: dict) -> dict:
    assert_owner(actor)
    get_institution_pilot(pilot_id)
    title = str(data.get("title") or "").strip()
    if not title:
        raise ValueError("Milestone title is required.")
    status = str(data.get("status") or "planned").strip().lower()
    if status not in MILESTONE_STATUSES:
        raise ValueError("Unsupported milestone status.")
    now = now_iso()
    completed_at = now if status == "completed" else None
    cursor = get_db().execute(
        """
        INSERT INTO institution_pilot_milestones
        (pilot_id,title,status,due_date,completed_at,notes,created_by,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (
            int(pilot_id),
            title[:300],
            status,
            _clean(data.get("due_date"), 40),
            completed_at,
            _clean(data.get("notes"), 1200),
            int(actor["id"]),
            now,
            now,
        ),
    )
    _event(int(pilot_id), "milestone_created", status, f"Milestone created: {title[:200]}", int(actor["id"]))
    get_db().commit()
    return get_db().execute(
        "SELECT * FROM institution_pilot_milestones WHERE id=?",
        (int(cursor.lastrowid),),
    ).fetchone()


def update_pilot_milestone(actor: Any, milestone_id: int, data: dict) -> dict:
    assert_owner(actor)
    db = get_db()
    row = db.execute("SELECT * FROM institution_pilot_milestones WHERE id=?", (int(milestone_id),)).fetchone()
    if not row:
        raise LookupError(f"Pilot milestone #{milestone_id} not found.")
    status = str(data.get("status", row["status"]) or "").strip().lower()
    if status not in MILESTONE_STATUSES:
        raise ValueError("Unsupported milestone status.")
    title = str(data.get("title", row["title"]) or "").strip()
    if not title:
        raise ValueError("Milestone title is required.")
    completed_at = row["completed_at"]
    if status == "completed" and not completed_at:
        completed_at = now_iso()
    if status != "completed":
        completed_at = None
    now = now_iso()
    db.execute(
        """
        UPDATE institution_pilot_milestones
        SET title=?,status=?,due_date=?,completed_at=?,notes=?,updated_at=?
        WHERE id=?
        """,
        (
            title[:300],
            status,
            _clean(data.get("due_date", row["due_date"]), 40),
            completed_at,
            _clean(data.get("notes", row["notes"]), 1200),
            now,
            int(milestone_id),
        ),
    )
    _event(int(row["pilot_id"]), "milestone_updated", status, f"Milestone updated: {title[:200]}", int(actor["id"]))
    db.commit()
    return dict(db.execute("SELECT * FROM institution_pilot_milestones WHERE id=?", (int(milestone_id),)).fetchone())


def record_pilot_usage_snapshot(actor: Any, pilot_id: int, data: dict) -> dict:
    assert_owner(actor)
    get_institution_pilot(pilot_id)
    source_type = str(data.get("source_type") or "owner_entered_observed").strip().lower()
    if source_type not in USAGE_SOURCE_TYPES:
        raise ValueError("Unsupported pilot usage source type.")
    if source_type == "system_derived":
        raise ValueError("system_derived snapshots may not be entered manually.")
    observed_at = str(data.get("observed_at") or now_iso()).strip()
    metrics = {
        "active_users": _optional_nonnegative_int(data.get("active_users")),
        "active_providers": _optional_nonnegative_int(data.get("active_providers")),
        "healthcare_searches": _optional_nonnegative_int(data.get("healthcare_searches")),
        "completed_handoffs": _optional_nonnegative_int(data.get("completed_handoffs")),
        "api_requests": _optional_nonnegative_int(data.get("api_requests")),
    }
    if all(value is None for value in metrics.values()):
        raise ValueError("At least one observed usage metric is required.")
    cursor = get_db().execute(
        """
        INSERT INTO institution_pilot_usage_snapshots
        (pilot_id,observed_at,active_users,active_providers,healthcare_searches,completed_handoffs,
         api_requests,source_type,notes,created_by,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            int(pilot_id),
            observed_at,
            metrics["active_users"],
            metrics["active_providers"],
            metrics["healthcare_searches"],
            metrics["completed_handoffs"],
            metrics["api_requests"],
            source_type,
            _clean(data.get("notes"), 1200),
            int(actor["id"]),
            now_iso(),
        ),
    )
    _event(int(pilot_id), "usage_snapshot_recorded", "observed", "Pilot usage snapshot recorded.", int(actor["id"]))
    get_db().commit()
    return dict(get_db().execute(
        "SELECT * FROM institution_pilot_usage_snapshots WHERE id=?",
        (int(cursor.lastrowid),),
    ).fetchone())


def pilot_execution_summary(actor: Any, pilot_id: int) -> dict:
    assert_owner(actor)
    pilot = get_institution_pilot(pilot_id)
    db = get_db()
    milestone_rows = db.execute(
        "SELECT * FROM institution_pilot_milestones WHERE pilot_id=? ORDER BY due_date,id",
        (int(pilot_id),),
    ).fetchall()
    milestones = [dict(row) for row in milestone_rows]
    usage_rows = db.execute(
        """
        SELECT * FROM institution_pilot_usage_snapshots
        WHERE pilot_id=?
        ORDER BY observed_at DESC,id DESC
        """,
        (int(pilot_id),),
    ).fetchall()
    usage = [dict(row) for row in usage_rows]
    latest = usage[0] if usage else None

    milestone_counts = {status: 0 for status in MILESTONE_STATUSES}
    for item in milestones:
        milestone_counts[item["status"]] = milestone_counts.get(item["status"], 0) + 1
    total_milestones = len(milestones)
    completed = milestone_counts.get("completed", 0)

    def _progress(actual_key: str, target_key: str):
        target = pilot.get(target_key)
        actual = latest.get(actual_key) if latest else None
        if target in (None, 0) or actual is None:
            return {"actual": actual, "target": target, "progress_rate": None}
        return {
            "actual": actual,
            "target": target,
            "progress_rate": round(float(actual) / float(target), 4),
        }

    return {
        "pilot": pilot,
        "milestones": milestones,
        "milestone_counts": milestone_counts,
        "milestone_completion_rate": round(completed / total_milestones, 4) if total_milestones else None,
        "usage_snapshots": usage,
        "latest_usage": latest,
        "user_progress": _progress("active_users", "target_users"),
        "provider_progress": _progress("active_providers", "target_provider_seats"),
        "truth_notice": (
            "Targets are plans; usage snapshots are observed values. Owner-entered observed snapshots are not "
            "system-verified analytics and must not be presented as automated telemetry."
        ),
    }


def get_institution_pilot(pilot_id: int) -> dict:
    row = get_db().execute("SELECT * FROM institution_pilots WHERE id=?", (int(pilot_id),)).fetchone()
    if not row:
        raise LookupError(f"Institution pilot #{pilot_id} not found.")
    item = dict(row)
    item["agreed_features"] = _json_list(item.pop("agreed_features_json"))
    item["success_metrics"] = _json_list(item.pop("success_metrics_json"))
    return item


def list_institution_pilots(actor: Any, *, status: str | None = None, limit: int = 100) -> list[dict]:
    assert_owner(actor)
    limit = max(1, min(int(limit or 100), 500))
    params: list[Any] = []
    clause = ""
    if status:
        clean = str(status).strip().lower()
        if clean not in PILOT_STATUSES:
            raise ValueError("Unsupported pilot status.")
        clause = "WHERE status=?"
        params.append(clean)
    params.append(limit)
    rows = get_db().execute(
        f"SELECT id FROM institution_pilots {clause} ORDER BY updated_at DESC LIMIT ?",
        params,
    ).fetchall()
    return [get_institution_pilot(int(row["id"])) for row in rows]


def institution_pilot_metrics(actor: Any) -> dict:
    assert_owner(actor)
    rows = get_db().execute("SELECT status,commercial_status,monthly_value_inr FROM institution_pilots").fetchall()
    total = len(rows)
    active = sum(1 for row in rows if row["status"] == "active")
    completed = sum(1 for row in rows if row["status"] == "completed")
    converted = sum(1 for row in rows if row["status"] == "converted")
    paid = sum(1 for row in rows if row["commercial_status"] == "paid")
    pipeline_value = sum(float(row["monthly_value_inr"] or 0) for row in rows if row["commercial_status"] in {"contract", "paid"})
    return {
        "pilot_count": total,
        "active_pilots": active,
        "completed_pilots": completed,
        "converted_pilots": converted,
        "paid_pilots": paid,
        "conversion_rate": round(converted / total, 4) if total else None,
        "entered_monthly_value_inr": round(pipeline_value, 2),
        "truth_notice": (
            "Pilot counts and monetary values reflect only owner-entered records. A proposal or LOI is not revenue; "
            "paid status must be entered only after a real commercial arrangement exists."
        ),
    }


def _event(pilot_id: int, event_type: str, status: str, message: str, actor_id: int | None):
    get_db().execute(
        """
        INSERT INTO institution_pilot_events
        (pilot_id,event_type,status,message,actor_id,created_at)
        VALUES (?,?,?,?,?,?)
        """,
        (int(pilot_id), event_type, status, str(message)[:1000], actor_id, now_iso()),
    )


def _list_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip()[:200] for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip()[:200] for item in value.split(",") if item.strip()]
    return []


def _json_list(value: str | None) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


def _clean(value: Any, limit: int) -> str | None:
    text = str(value or "").strip()
    return text[:limit] or None


def _optional_nonnegative_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    number = int(value)
    if number < 0:
        raise ValueError("Numeric pilot targets must be non-negative.")
    return number


def _optional_nonnegative_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    number = float(value)
    if number < 0:
        raise ValueError("monthly_value_inr must be non-negative.")
    return number
