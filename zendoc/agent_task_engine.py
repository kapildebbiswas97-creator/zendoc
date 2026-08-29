"""
ZENDOC Agent Task Engine — Milestone 8
Persistent agent tasks with status tracking, idempotency, retry logic.

Task statuses: queued → running → waiting_approval / waiting_human → completed / failed / cancelled
Retry only temporary failures. Permanent failures do not retry.
Never runs uncontrolled loops in Flask requests.
"""
from __future__ import annotations

import time

from .db import get_db, now_iso


# ── Failure categories ─────────────────────────────────────────────────────────
class FailureCategory:
    TEMPORARY          = "temporary"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    TIMEOUT            = "timeout"
    PERMISSION_DENIED  = "permission_denied"
    CONSENT_REQUIRED   = "consent_required"
    APPROVAL_REQUIRED  = "approval_required"
    INVALID_INPUT      = "invalid_input"
    PERMANENT          = "permanent"
    UNKNOWN            = "unknown"


RETRIABLE_FAILURES = {
    FailureCategory.TEMPORARY,
    FailureCategory.PROVIDER_UNAVAILABLE,
    FailureCategory.TIMEOUT,
}

# Task limits
MAX_STEPS = 20
MAX_RETRIES_DEFAULT = 3
EXECUTION_TIMEOUT_SECONDS = 30
TASK_STATUSES = {"queued", "running", "waiting_approval", "waiting_human", "completed", "failed", "cancelled"}
TASK_PRIORITIES = {"low", "normal", "high", "critical"}


def _value(actor, key, default=None):
    if actor is None:
        return default
    if hasattr(actor, "keys") and key in actor.keys():
        return actor[key]
    return actor.get(key, default) if isinstance(actor, dict) else default


def _can_access_task(actor, task: dict) -> bool:
    from .security import is_owner
    return bool(is_owner(actor) or int(_value(actor, "id", 0) or 0) == int(task["requested_by"] or 0))


def _make_idempotency_key(*parts: str) -> str:
    return ":".join(str(p) for p in parts if p)


def create_agent_task(
    task_type: str,
    requested_by: int,
    assigned_agent: str,
    priority: str = "normal",
    risk_level: str = "low_risk",
    max_attempts: int = MAX_RETRIES_DEFAULT,
    idempotency_key: str | None = None,
    metadata: dict | None = None,
    actor=None,
) -> dict:
    """Create a persistent agent task. Returns the created task dict."""
    from .agent_registry import get_agent
    if not str(task_type or "").strip():
        raise ValueError("task_type is required.")
    if not get_agent(assigned_agent):
        raise ValueError(f"Unknown specialized agent '{assigned_agent}'.")
    if priority not in TASK_PRIORITIES:
        raise ValueError("Invalid task priority.")
    max_attempts = max(1, min(int(max_attempts or MAX_RETRIES_DEFAULT), 5))
    if actor is not None:
        from .security import is_owner
        if not is_owner(actor) and int(_value(actor, "id", 0) or 0) != int(requested_by):
            raise PermissionError("Users may create agent tasks only for themselves.")
    db = get_db()
    idempotency_key = str(idempotency_key or "").strip()[:160] or None
    if idempotency_key:
        existing = db.execute(
            "SELECT * FROM agent_tasks WHERE idempotency_key=?",
            (idempotency_key,),
        ).fetchone()
        if existing:
            return dict(existing)

    import json
    now = now_iso()
    cursor = db.execute(
        """
        INSERT INTO agent_tasks
        (task_type, requested_by, assigned_agent, status, priority, risk_level,
         attempt_count, max_attempts, idempotency_key, metadata_json, created_at, updated_at)
        VALUES (?, ?, ?, 'queued', ?, ?, 0, ?, ?, ?, ?, ?)
        """,
        (
            task_type,
            requested_by,
            assigned_agent,
            priority,
            risk_level,
            max_attempts,
            idempotency_key,
            json.dumps(metadata or {}),
            now,
            now,
        ),
    )
    task_id = cursor.lastrowid
    db.commit()
    task = get_agent_task(task_id)
    _publish_task_event(task, actor, "created")
    return task


def get_agent_task(task_id: int, actor=None) -> dict:
    row = get_db().execute("SELECT * FROM agent_tasks WHERE id=?", (int(task_id),)).fetchone()
    if not row:
        raise LookupError(f"Agent task #{task_id} not found.")
    task = dict(row)
    if actor is not None and not _can_access_task(actor, task):
        raise PermissionError("You cannot access this agent task.")
    return task


def list_agent_tasks(status: str | None = None, limit: int = 50, actor=None) -> list[dict]:
    db = get_db()
    limit = max(1, min(int(limit or 50), 200))
    if status and status not in TASK_STATUSES:
        raise ValueError("Invalid task status filter.")
    from .security import is_owner
    owner_scope = actor is None or is_owner(actor)
    if status and owner_scope:
        rows = db.execute(
            "SELECT * FROM agent_tasks WHERE status=? ORDER BY created_at DESC LIMIT ?",
            (status, limit),
        ).fetchall()
    elif owner_scope:
        rows = db.execute(
            "SELECT * FROM agent_tasks ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    elif status:
        rows = db.execute(
            "SELECT * FROM agent_tasks WHERE status=? AND requested_by=? ORDER BY created_at DESC LIMIT ?",
            (status, int(_value(actor, "id", 0) or 0), limit),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM agent_tasks WHERE requested_by=? ORDER BY created_at DESC LIMIT ?",
            (int(_value(actor, "id", 0) or 0), limit),
        ).fetchall()
    return [dict(r) for r in rows]


def execute_safe_task(task_id: int, actor: dict, handler_fn=None) -> dict:
    """
    Execute a single agent task synchronously (safe for request context).
    Returns updated task dict.
    handler_fn: optional callable(task_dict) -> result_summary str
    """
    task = get_agent_task(task_id)
    if not _can_access_task(actor, task):
        raise PermissionError("You cannot execute this agent task.")
    if task["status"] not in ("queued", "failed"):
        raise ValueError(f"Task #{task_id} is in '{task['status']}' state and cannot be executed.")
    if task["attempt_count"] >= task["max_attempts"]:
        raise ValueError(f"Task #{task_id} has exhausted max attempts ({task['max_attempts']}).")

    if task["risk_level"] == "critical_blocked":
        raise PermissionError("CRITICAL_BLOCKED tasks cannot be executed.")
    if task["risk_level"] == "owner_approval":
        from .security import assert_owner
        assert_owner(actor)
    if handler_fn is None:
        raise LookupError(f"No bounded handler is registered for task type '{task['task_type']}'.")

    _update_task(task_id, "running", attempt_delta=1)
    started = time.perf_counter()
    try:
        result_summary = str(handler_fn(task) or "Task completed.")
        duration = int((time.perf_counter() - started) * 1000)
        _update_task(task_id, "completed", result_summary=result_summary[:500], duration_ms=duration)
        _record_attempt(task_id, "completed", result_summary[:300], duration_ms=duration)
        completed = get_agent_task(task_id)
        _publish_task_event(completed, actor, "completed")
        return completed
    except PermissionError as exc:
        _fail_task(task_id, started, str(exc), FailureCategory.PERMISSION_DENIED)
        raise
    except Exception as exc:
        category = _classify_error(exc)
        _fail_task(task_id, started, str(exc), category)
        return get_agent_task(task_id)


def retry_task(task_id: int, actor: dict) -> dict:
    """Retry a failed task if it has retriable failure category and attempts remaining."""
    task = get_agent_task(task_id)
    if not _can_access_task(actor, task):
        raise PermissionError("You cannot retry this agent task.")
    if task["status"] != "failed":
        raise ValueError(f"Task #{task_id} is not in 'failed' state.")
    if task["last_error_category"] not in RETRIABLE_FAILURES:
        raise ValueError(f"Task #{task_id} failed permanently ('{task['last_error_category']}') and cannot be retried.")
    if task["attempt_count"] >= task["max_attempts"]:
        raise ValueError(f"Task #{task_id} has exhausted its {task['max_attempts']} max attempts.")
    _update_task(task_id, "queued")
    retried = get_agent_task(task_id)
    _publish_task_event(retried, actor, "retry_queued")
    return retried


def request_approval_for_task(task_id: int, requested_by_user_id: int, action_type: str, payload_summary: str) -> dict:
    """Create an owner approval request linked to this task."""
    from .agent_approvals import create_approval
    task = get_agent_task(task_id)
    _update_task(task_id, "waiting_approval")
    return create_approval(
        requested_by_user_id=requested_by_user_id,
        action_type=action_type,
        task_id=task_id,
        payload_summary=payload_summary[:500],
        risk_level=task["risk_level"],
    )


def set_task_waiting(task_id: int, status: str, summary: str = "") -> dict:
    if status not in {"waiting_approval", "waiting_human"}:
        raise ValueError("Task may wait only for approval or human action.")
    _update_task(task_id, status, result_summary=str(summary or "")[:500])
    return get_agent_task(task_id)


# ── Internal helpers ───────────────────────────────────────────────────────────
def _update_task(
    task_id: int,
    status: str,
    result_summary: str | None = None,
    attempt_delta: int = 0,
    duration_ms: int | None = None,
    last_error_category: str | None = None,
):
    db = get_db()
    now = now_iso()
    # Build dynamic SQL safely
    sets = ["status=?"]
    params_ordered = [status]

    if status == "running":
        sets.append("started_at=?")
        params_ordered.append(now)
    if status in ("completed", "failed", "cancelled"):
        sets.append("completed_at=?")
        params_ordered.append(now)
    if result_summary is not None:
        sets.append("result_summary=?")
        params_ordered.append(result_summary)
    if last_error_category is not None:
        sets.append("last_error_category=?")
        params_ordered.append(last_error_category)
    if attempt_delta:
        sets.append("attempt_count=attempt_count+1")
    if duration_ms is not None:
        sets.append("duration_ms=?")
        params_ordered.append(max(0, int(duration_ms)))

    sets.append("updated_at=?")
    params_ordered.append(now)
    params_ordered.append(int(task_id))

    db.execute(
        f"UPDATE agent_tasks SET {', '.join(sets)} WHERE id=?",
        params_ordered,
    )
    db.commit()


def _fail_task(task_id: int, started: float, error_msg: str, category: str):
    duration = int((time.perf_counter() - started) * 1000)
    _update_task(task_id, "failed", result_summary=error_msg[:300], last_error_category=category, duration_ms=duration)
    _record_attempt(task_id, "failed", error_msg[:300], error_category=category, duration_ms=duration)


def _record_attempt(task_id: int, status: str, message: str = "", error_category: str | None = None, duration_ms: int | None = None):
    db = get_db()
    db.execute(
        "INSERT INTO agent_task_attempts (task_id, status, message, error_category, duration_ms, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (task_id, status, message[:500] if message else "", error_category, duration_ms, now_iso()),
    )
    db.commit()


def _classify_error(exc: Exception) -> str:
    msg = str(exc).lower()
    if "permission" in msg or "unauthorized" in msg or "forbidden" in msg:
        return FailureCategory.PERMISSION_DENIED
    if "consent" in msg:
        return FailureCategory.CONSENT_REQUIRED
    if "approval" in msg:
        return FailureCategory.APPROVAL_REQUIRED
    if "timeout" in msg or "timed out" in msg:
        return FailureCategory.TIMEOUT
    if "unavailable" in msg or "connection" in msg or "refused" in msg:
        return FailureCategory.PROVIDER_UNAVAILABLE
    if "invalid" in msg or "value" in msg:
        return FailureCategory.INVALID_INPUT
    return FailureCategory.UNKNOWN


def _publish_task_event(task: dict, actor, transition: str):
    try:
        from .event_bus import publish_event
        publish_event(
            f"agent.task.{transition}",
            actor=actor,
            entity_type="agent_task",
            entity_id=str(task["id"]),
            status=task["status"],
            agent_name=task["assigned_agent"],
            payload={"task_type": task["task_type"], "attempt_count": task["attempt_count"]},
        )
    except Exception:
        pass
