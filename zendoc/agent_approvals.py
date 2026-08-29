"""
ZENDOC Agent Approvals — Milestone 8
Human-in-the-loop approval engine for owner-level and doctor-level actions.

Owner approvals appear in the Command Center.
Doctor approvals go to authorized doctor workflow only.
Patient consent remains separate (communication_permissions table).

Statuses: pending → approved / rejected / expired / cancelled
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .db import get_db, now_iso


APPROVAL_STATUSES = ("pending", "approved", "rejected", "expired", "cancelled")


def _value(actor, key, default=None):
    if actor is None:
        return default
    if hasattr(actor, "keys") and key in actor.keys():
        return actor[key]
    return actor.get(key, default) if isinstance(actor, dict) else default


def create_approval(
    requested_by_user_id: int,
    action_type: str,
    payload_summary: str,
    risk_level: str = "owner_approval",
    task_id: int | None = None,
    requested_by_agent: str = "ZENDOC Core Agent",
    expires_hours: int = 24,
    approver_user_id: int | None = None,
) -> dict:
    """Create a pending approval record. Never store secrets in payload."""
    if risk_level not in {"owner_approval", "doctor_approval", "critical_blocked"}:
        raise ValueError("Unsupported approval risk level.")
    if risk_level == "critical_blocked":
        raise PermissionError("CRITICAL_BLOCKED actions cannot be approved or executed.")
    if risk_level == "doctor_approval" and not approver_user_id:
        raise ValueError("Doctor approval requires a specific authorized approver.")
    expires_hours = max(1, min(int(expires_hours or 24), 168))
    now = now_iso()
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=expires_hours)).isoformat(timespec="seconds")
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO agent_approvals
        (run_id, actor_id, operation_type, status, requested_at,
         requested_by_agent, requested_by_user_id, action_type, task_id,
         payload_summary, risk_level, approver_user_id, expires_at, created_at)
        VALUES (NULL, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(requested_by_user_id),
            str(action_type or "agent_action")[:120],
            now,
            requested_by_agent,
            int(requested_by_user_id),
            str(action_type or "agent_action")[:120],
            int(task_id) if task_id else None,
            str(payload_summary or "")[:500],
            risk_level,
            int(approver_user_id) if approver_user_id else None,
            expires_at,
            now,
        ),
    )
    approval_id = cursor.lastrowid
    db.commit()
    return get_approval(approval_id)


def get_approval(approval_id: int) -> dict:
    row = get_db().execute("SELECT * FROM agent_approvals WHERE id=?", (int(approval_id),)).fetchone()
    if not row:
        raise LookupError(f"Approval #{approval_id} not found.")
    return dict(row)


def list_approvals(status: str | None = None, limit: int = 50) -> list[dict]:
    db = get_db()
    limit = max(1, min(int(limit or 50), 200))
    if status:
        rows = db.execute(
            "SELECT * FROM agent_approvals WHERE status=? ORDER BY created_at DESC LIMIT ?",
            (status, limit),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM agent_approvals ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_pending_approvals() -> list[dict]:
    """Expire stale pending approvals then return remaining pending."""
    _expire_old_approvals()
    return list_approvals("pending")


def list_approvals_for_actor(actor, status: str | None = None, limit: int = 50) -> list[dict]:
    """Scope approval visibility to the owner, designated approver, or requester."""
    from .security import is_owner
    if status and status not in APPROVAL_STATUSES:
        raise ValueError("Invalid approval status filter.")
    limit = max(1, min(int(limit or 50), 200))
    if is_owner(actor):
        return list_approvals(status, limit)
    actor_id = int(_value(actor, "id", 0) or 0)
    role = _value(actor, "role", "")
    clauses = []
    params = []
    if role in {"doctor", "hospital"}:
        clauses.append("approver_user_id=?")
        params.append(actor_id)
    clauses.append("requested_by_user_id=?")
    params.append(actor_id)
    where = f"({' OR '.join(clauses)})"
    if status:
        where += " AND status=?"
        params.append(status)
    params.append(limit)
    rows = get_db().execute(
        f"SELECT * FROM agent_approvals WHERE {where} ORDER BY created_at DESC LIMIT ?",
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def resolve_approval(approval_id: int, resolver: dict, decision: str, note: str = "") -> dict:
    """
    Resolve an approval. Only the owner/admin can resolve owner_approval items.
    decision: 'approved' or 'rejected'
    """
    if decision not in ("approved", "rejected"):
        raise ValueError("Decision must be 'approved' or 'rejected'.")
    approval = get_approval(approval_id)
    if approval["status"] != "pending":
        raise ValueError(f"Approval #{approval_id} is already '{approval['status']}' and cannot be resolved.")

    # Authorization check — owner approval requires admin role
    resolver_role = _value(resolver, "role", "")
    if approval["risk_level"] == "owner_approval":
        from .security import assert_owner
        assert_owner(resolver)
    elif approval["risk_level"] == "doctor_approval":
        if resolver_role not in {"doctor", "hospital"}:
            raise PermissionError("Only the designated doctor can resolve this approval.")
        if int(approval.get("approver_user_id") or 0) != int(_value(resolver, "id", 0) or 0):
            raise PermissionError("This approval is assigned to a different doctor.")
    else:
        raise PermissionError("This action cannot be approved.")

    now = now_iso()
    db = get_db()
    db.execute(
        """
        UPDATE agent_approvals
        SET status=?, decided_at=?, decision_note=?, resolved_at=?, resolved_by=?, resolution_note=?
        WHERE id=?
        """,
        (
            decision,
            now,
            str(note or "")[:500],
            now,
            int(_value(resolver, "id", 0) or 0),
            str(note or "")[:500],
            int(approval_id),
        ),
    )
    if approval.get("task_id"):
        task_status = "queued" if decision == "approved" else "cancelled"
        db.execute(
            "UPDATE agent_tasks SET status=?, updated_at=?, completed_at=CASE WHEN ?='cancelled' THEN ? ELSE completed_at END WHERE id=?",
            (task_status, now, task_status, now, int(approval["task_id"])),
        )
    db.commit()
    _publish_approval_event(approval_id, resolver, decision)
    return get_approval(approval_id)


def cancel_approval(approval_id: int, actor: dict) -> dict:
    """Cancel a pending approval (owner only)."""
    from .security import assert_owner
    assert_owner(actor)
    approval = get_approval(approval_id)
    if approval["status"] != "pending":
        raise ValueError(f"Approval #{approval_id} is not pending.")
    db = get_db()
    db.execute(
        "UPDATE agent_approvals SET status='cancelled', decided_at=?, resolved_at=?, resolved_by=? WHERE id=?",
        (now_iso(), now_iso(), int(_value(actor, "id", 0) or 0), int(approval_id)),
    )
    db.commit()
    return get_approval(approval_id)


def _expire_old_approvals():
    now = now_iso()
    get_db().execute(
        "UPDATE agent_approvals SET status='expired' WHERE status='pending' AND expires_at < ?",
        (now,),
    )
    get_db().commit()


def _publish_approval_event(approval_id: int, actor, decision: str):
    try:
        from .event_bus import publish_event
        publish_event(
            "agent.approval.resolved",
            actor=actor,
            entity_type="agent_approval",
            entity_id=str(approval_id),
            status=decision,
            payload={"decision": decision},
        )
    except Exception:
        # Approval state is authoritative; observability failure must not roll it back.
        pass
