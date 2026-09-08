"""Persistent, permission-aware event bus used by M8 workflows and polling."""
from __future__ import annotations

from flask import g, has_request_context

import json
import re
import uuid

from .db import get_db, now_iso
from .audit_privacy import redact_operational_text, safe_payload


EVENT_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+){1,5}$")

def _value(actor, key, default=None):
    if actor is None:
        return default
    if hasattr(actor, "keys") and key in actor.keys():
        return actor[key]
    return actor.get(key, default) if isinstance(actor, dict) else default


def publish_event(
    event_type: str,
    *,
    actor=None,
    entity_type: str = "platform",
    entity_id: str | None = None,
    status: str = "info",
    payload: dict | None = None,
    agent_name: str | None = None,
    error: str | None = None,
    approval_state: str = "not_required",
    duration_ms: int | None = None,
    correlation_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """Append an event. Duplicate idempotency keys return the original event."""
    event_type = str(event_type or "").strip().lower()
    if not EVENT_TYPE_RE.match(event_type):
        raise ValueError("event_type must use a namespaced value such as 'agent.task.created'.")
    db = get_db()
    idempotency_key = str(idempotency_key or "").strip()[:160] or None
    if idempotency_key:
        existing = db.execute("SELECT * FROM platform_events WHERE idempotency_key=?", (idempotency_key,)).fetchone()
        if existing:
            return _event_dict(existing)
    request_correlation = getattr(g, "correlation_id", None) if has_request_context() else None
    correlation_id = str(correlation_id or request_correlation or uuid.uuid4().hex)[:80]
    safe_payload_json = json.dumps(safe_payload(payload or {}), sort_keys=True, separators=(",", ":"))
    cursor = db.execute(
        """
        INSERT INTO platform_events
        (actor_id, agent_name, action, entity_type, entity_id, status, error,
         approval_state, duration_ms, event_type, payload_json, correlation_id,
         idempotency_key, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(_value(actor, "id", 0) or 0) or None,
            str(agent_name or "")[:100] or None,
            event_type,
            str(entity_type or "platform")[:80],
            str(entity_id)[:100] if entity_id is not None else None,
            str(status or "info")[:40],
            redact_operational_text(error, 300),
            str(approval_state or "not_required")[:40],
            int(duration_ms) if duration_ms is not None else None,
            event_type,
            safe_payload_json[:4000],
            correlation_id,
            idempotency_key,
            now_iso(),
        ),
    )
    db.commit()
    return get_event(cursor.lastrowid)


def get_event(event_id: int) -> dict:
    row = get_db().execute("SELECT * FROM platform_events WHERE id=?", (int(event_id),)).fetchone()
    if not row:
        raise LookupError("Platform event not found.")
    return _event_dict(row)


def list_events(actor, after_id: int = 0, limit: int = 100) -> list[dict]:
    """Poll events. The owner sees operations; other users see only their own events."""
    from .security import is_owner

    after_id = max(0, int(after_id or 0))
    limit = max(1, min(int(limit or 100), 200))
    if is_owner(actor):
        rows = get_db().execute(
            "SELECT * FROM platform_events WHERE id>? ORDER BY id ASC LIMIT ?",
            (after_id, limit),
        ).fetchall()
    else:
        rows = get_db().execute(
            "SELECT * FROM platform_events WHERE id>? AND actor_id=? ORDER BY id ASC LIMIT ?",
            (after_id, int(_value(actor, "id", 0) or 0), limit),
        ).fetchall()
    return [_event_dict(row) for row in rows]


def _event_dict(row) -> dict:
    item = dict(row)
    try:
        item["payload"] = json.loads(item.pop("payload_json", "{}") or "{}")
    except json.JSONDecodeError:
        item["payload"] = {}
    item["event_type"] = item.get("event_type") or item.get("action")
    return item
