"""Bounded owner-only OperationsAgent automation.

This pass performs only reversible operational maintenance:
- re-queue failed tasks whose failure category is explicitly retriable;
- run deterministic alert checks;
- summarize what still needs human attention.

It deliberately does not execute arbitrary queued tasks, change permissions,
move money, approve coverage, prescribe, dispatch emergencies, or delete data.
"""
from __future__ import annotations

from typing import Any

from .agent_alerts import run_proactive_alert_check
from .ai_workforce import intake_failed_events
from .global_source_research import enqueue_source_research_batch
from .agent_task_engine import RETRIABLE_FAILURES, retry_task
from .db import get_db
from .security import assert_owner


def run_safe_operations_automation(actor: Any, *, retry_limit: int = 10) -> dict:
    assert_owner(actor)
    retry_limit = max(1, min(int(retry_limit or 10), 25))
    db = get_db()

    placeholders = ",".join("?" for _ in RETRIABLE_FAILURES)
    rows = db.execute(
        f"""
        SELECT * FROM agent_tasks
        WHERE status='failed'
          AND last_error_category IN ({placeholders})
          AND attempt_count < max_attempts
        ORDER BY updated_at ASC, id ASC
        LIMIT ?
        """,
        (*sorted(RETRIABLE_FAILURES), retry_limit),
    ).fetchall()

    requeued = []
    retry_errors = []
    for row in rows:
        try:
            task = retry_task(int(row["id"]), actor)
            requeued.append({
                "task_id": task["id"],
                "assigned_agent": task["assigned_agent"],
                "task_type": task["task_type"],
                "status": task["status"],
                "previous_error_category": row["last_error_category"],
            })
        except (PermissionError, ValueError, LookupError) as exc:
            retry_errors.append({
                "task_id": row["id"],
                "error": str(exc)[:300],
            })

    workforce = intake_failed_events(actor, limit=retry_limit)
    source_research = enqueue_source_research_batch(actor)
    alerts = run_proactive_alert_check()

    waiting_human = db.execute(
        "SELECT COUNT(*) c FROM agent_tasks WHERE status IN ('waiting_human','waiting_approval')"
    ).fetchone()["c"]
    permanent_failed = db.execute(
        """
        SELECT COUNT(*) c FROM agent_tasks
        WHERE status='failed'
          AND (attempt_count >= max_attempts OR last_error_category NOT IN (?, ?, ?))
        """,
        tuple(sorted(RETRIABLE_FAILURES)),
    ).fetchone()["c"]

    return {
        "status": "completed",
        "requeued_count": len(requeued),
        "requeued_tasks": requeued,
        "retry_errors": retry_errors,
        "new_alerts": alerts,
        "waiting_human_or_approval": waiting_human,
        "permanent_or_exhausted_failures": permanent_failed,
        "executed_tasks": 0,
        "workforce_cases_created": workforce.get("created_count", 0),
        "workforce_cases_existing": workforce.get("existing_count", 0),
        "global_source_gap_count": source_research.get("source_gap_count", 0),
        "source_research_task_id": (source_research.get("task") or {}).get("id"),
        "source_research_batch_created": bool(source_research.get("created")),
        "safety": {
            "moves_money": False,
            "changes_permissions": False,
            "approves_coverage": False,
            "prescribes": False,
            "dispatches_emergency": False,
            "deletes_critical_data": False,
            "arbitrary_execution": False,
        },
    }
