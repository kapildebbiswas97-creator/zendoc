"""Owner-managed P0/P1 public-data refresh operations."""
from __future__ import annotations

from typing import Any

from .data_freshness import ingestion_freshness_report
from .db import get_db, now_iso
from .public_source_registry import list_public_ingestion_sources
from .security import assert_owner


REFRESH_STATUSES = {"queued", "in_progress", "blocked", "completed", "cancelled"}
ACTIVE_REFRESH_STATUSES = {"queued", "in_progress"}
REFRESH_TRANSITIONS = {
    "queued": {"in_progress", "blocked", "completed", "cancelled"},
    "in_progress": {"blocked", "completed", "cancelled"},
    "blocked": {"queued", "in_progress", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


def create_data_refresh_task(
    actor: Any,
    *,
    source_id: str,
    ingestion_type: str | None = None,
    owner_note: str | None = None,
) -> dict:
    assert_owner(actor)
    source_id = str(source_id or "").strip()
    if not source_id:
        raise ValueError("source_id is required.")

    source = _freshness_source(actor, source_id)
    if source["refresh_priority"] not in {"P0", "P1"}:
        raise ValueError("Only current P0/P1 sources may be added to the urgent refresh queue.")
    supported_types = list(source.get("ingestion_types") or [])
    if not supported_types:
        raise ValueError("This source is reference-only or requires an authorized integration; it cannot be queued for bulk refresh.")

    selected_type = str(ingestion_type or supported_types[0]).strip()
    if selected_type not in supported_types:
        raise ValueError("Unsupported ingestion_type for this source.")

    db = get_db()
    existing = db.execute(
        """
        SELECT id FROM data_refresh_tasks
        WHERE source_id=? AND ingestion_type=? AND status IN ('queued','in_progress')
        ORDER BY id DESC LIMIT 1
        """,
        (source_id, selected_type),
    ).fetchone()
    if existing:
        return get_data_refresh_task(actor, int(existing["id"]))

    reason_code = _reason_code(source)
    now = now_iso()
    cursor = db.execute(
        """
        INSERT INTO data_refresh_tasks
        (source_id,priority,reason_code,ingestion_type,status,linked_batch_id,owner_note,
         blocked_reason,requested_at,started_at,completed_at,created_by,created_at,updated_at)
        VALUES (?,?,?,?, 'queued',NULL,?,NULL,?,NULL,NULL,?,?,?)
        """,
        (
            source_id,
            source["refresh_priority"],
            reason_code,
            selected_type,
            _clean(owner_note, 1200),
            now,
            int(actor["id"]),
            now,
            now,
        ),
    )
    db.commit()
    return get_data_refresh_task(actor, int(cursor.lastrowid))


def update_data_refresh_task(
    actor: Any,
    task_id: int,
    *,
    status: str,
    linked_batch_id: int | None = None,
    owner_note: str | None = None,
    blocked_reason: str | None = None,
) -> dict:
    assert_owner(actor)
    task = get_data_refresh_task(actor, int(task_id))
    target = str(status or "").strip().lower()
    if target not in REFRESH_STATUSES:
        raise ValueError("Unsupported data refresh task status.")

    current = str(task["status"])
    if target == current:
        return task
    if target not in REFRESH_TRANSITIONS.get(current, set()):
        raise ValueError(f"Invalid refresh task transition: {current} -> {target}.")

    db = get_db()
    now = now_iso()
    started_at = task.get("started_at")
    completed_at = task.get("completed_at")
    batch_id = int(linked_batch_id) if linked_batch_id not in (None, "") else task.get("linked_batch_id")
    clean_blocked = _clean(blocked_reason, 1200)

    if target == "in_progress":
        started_at = started_at or now
        completed_at = None
    elif target == "blocked":
        if not clean_blocked:
            raise ValueError("blocked_reason is required when blocking a refresh task.")
    elif target == "completed":
        if batch_id is None:
            raise ValueError("A real completed ingestion batch is required before a refresh task can be completed.")
        batch = db.execute(
            """
            SELECT id,source_id,ingestion_type,dry_run,status,completed_at
            FROM data_ingestion_batches
            WHERE id=?
            """,
            (int(batch_id),),
        ).fetchone()
        if not batch:
            raise LookupError("Linked ingestion batch not found.")
        if str(batch["source_id"]) != str(task["source_id"]):
            raise ValueError("Linked ingestion batch belongs to a different source.")
        if str(batch["ingestion_type"]) != str(task["ingestion_type"]):
            raise ValueError("Linked ingestion batch uses a different ingestion type.")
        if bool(batch["dry_run"]) or str(batch["status"]) != "completed":
            raise ValueError("Only a completed non-dry-run ingestion batch can complete a refresh task.")
        started_at = started_at or task["requested_at"]
        completed_at = batch["completed_at"] or now
    elif target == "queued":
        completed_at = None

    db.execute(
        """
        UPDATE data_refresh_tasks
        SET status=?,linked_batch_id=?,owner_note=?,blocked_reason=?,
            started_at=?,completed_at=?,updated_at=?
        WHERE id=?
        """,
        (
            target,
            batch_id,
            _clean(owner_note, 1200) if owner_note is not None else task.get("owner_note"),
            clean_blocked if target == "blocked" else None,
            started_at,
            completed_at,
            now,
            int(task_id),
        ),
    )
    db.commit()
    return get_data_refresh_task(actor, int(task_id))


def get_data_refresh_task(actor: Any, task_id: int) -> dict:
    assert_owner(actor)
    row = get_db().execute(
        """
        SELECT t.*,b.batch_uid,b.status batch_status,b.completed_at batch_completed_at,
               b.record_count batch_record_count,b.accepted_count batch_accepted_count,
               b.rejected_count batch_rejected_count
        FROM data_refresh_tasks t
        LEFT JOIN data_ingestion_batches b ON b.id=t.linked_batch_id
        WHERE t.id=?
        """,
        (int(task_id),),
    ).fetchone()
    if not row:
        raise LookupError(f"Data refresh task #{task_id} not found.")
    item = dict(row)
    source = _source_registry_entry(item["source_id"])
    item["source_name"] = source.get("name") if source else item["source_id"]
    item["source_geography"] = source.get("geography") if source else None
    item["source_live_fetch_status"] = source.get("live_fetch_status") if source else None
    return item


def list_data_refresh_tasks(
    actor: Any,
    *,
    status: str | None = None,
    limit: int = 200,
) -> list[dict]:
    assert_owner(actor)
    params: list[Any] = []
    where = ""
    if status:
        clean = str(status).strip().lower()
        if clean not in REFRESH_STATUSES:
            raise ValueError("Unsupported data refresh task status.")
        where = "WHERE status=?"
        params.append(clean)
    limit = max(1, min(int(limit or 200), 1000))
    params.append(limit)
    rows = get_db().execute(
        f"SELECT id FROM data_refresh_tasks {where} ORDER BY CASE priority WHEN 'P0' THEN 0 ELSE 1 END, requested_at DESC LIMIT ?",
        params,
    ).fetchall()
    return [get_data_refresh_task(actor, int(row["id"])) for row in rows]


def data_refresh_operations(actor: Any) -> dict:
    assert_owner(actor)
    freshness = ingestion_freshness_report(actor, recent_batch_limit=50)
    tasks = list_data_refresh_tasks(actor, limit=300)
    active_by_source = {
        str(task["source_id"]): task
        for task in tasks
        if task["status"] in ACTIVE_REFRESH_STATUSES
    }
    urgent_sources = []
    for source in freshness["sources"]:
        if source["refresh_priority"] not in {"P0", "P1"}:
            continue
        item = dict(source)
        item["active_refresh_task"] = active_by_source.get(str(source["source_id"]))
        urgent_sources.append(item)

    counts = {status: 0 for status in REFRESH_STATUSES}
    for task in tasks:
        counts[str(task["status"])] = counts.get(str(task["status"]), 0) + 1

    return {
        "urgent_source_count": len(urgent_sources),
        "urgent_sources": urgent_sources,
        "tasks": tasks,
        "task_status_counts": counts,
        "truth_notice": (
            "Urgency is derived from observed ingestion freshness/quality. A refresh task is not considered completed "
            "unless it links to a real completed non-dry-run ingestion batch for the same source and ingestion type."
        ),
    }


def _freshness_source(actor: Any, source_id: str) -> dict:
    report = ingestion_freshness_report(actor, recent_batch_limit=1)
    for source in report["sources"]:
        if str(source["source_id"]) == str(source_id):
            return source
    raise LookupError(f"Public ingestion source '{source_id}' not found.")


def _source_registry_entry(source_id: str) -> dict | None:
    for source in list_public_ingestion_sources():
        if str(source["source_id"]) == str(source_id):
            return source
    return None


def _reason_code(source: dict) -> str:
    status = str(source.get("freshness_status") or "")
    if status in {"never_ingested", "stale", "aging"}:
        return status
    if any(
        int(source.get(key, 0) or 0) > 0
        for key in (
            "latest_geography_unresolved_count",
            "latest_geography_ambiguous_count",
            "last_rejected_count",
        )
    ):
        return "quality_issue"
    return "refresh_required"


def _clean(value: Any, limit: int) -> str | None:
    text = str(value or "").strip()
    return text[:limit] or None
