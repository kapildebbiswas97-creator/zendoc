"""Privacy-safe audit trail for ZENDOC partner/B2B operations."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from .db import get_db, now_iso
from .security import assert_owner


FORBIDDEN_METADATA_KEYS = {
    "symptoms",
    "diagnosis",
    "prescription",
    "prescriptions",
    "medical_history",
    "clinical_notes",
    "reason",
    "record_body",
    "request_body",
    "patient_name",
    "patient_email",
    "patient_phone",
}


def record_partner_audit_event(
    *,
    event_type: str,
    actor_type: str,
    outcome: str = "success",
    client_id: int | None = None,
    key_id: int | None = None,
    actor_user_id: int | None = None,
    entity_type: str | None = None,
    entity_id: str | int | None = None,
    endpoint: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    safe_metadata = _sanitize_metadata(metadata or {})
    cursor = get_db().execute(
        """
        INSERT INTO partner_api_audit_events
        (client_id,key_id,actor_user_id,actor_type,event_type,entity_type,entity_id,endpoint,outcome,metadata_json,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            client_id,
            key_id,
            actor_user_id,
            str(actor_type or "system")[:80],
            str(event_type or "unknown")[:160],
            str(entity_type)[:120] if entity_type else None,
            str(entity_id)[:200] if entity_id is not None else None,
            str(endpoint)[:300] if endpoint else None,
            str(outcome or "success")[:80],
            json.dumps(safe_metadata, separators=(",", ":"), sort_keys=True),
            now_iso(),
        ),
    )
    return int(cursor.lastrowid)


def list_partner_audit_events(actor: Any, *, limit: int = 200) -> list[dict]:
    assert_owner(actor)
    limit = max(1, min(int(limit or 200), 1000))
    rows = get_db().execute(
        """
        SELECT a.*,c.name client_name
        FROM partner_api_audit_events a
        LEFT JOIN business_api_clients c ON c.id=a.client_id
        ORDER BY a.created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        except Exception:
            item["metadata"] = {}
        result.append(item)
    return result


def partner_audit_metrics(actor: Any, *, days: int = 30) -> dict:
    assert_owner(actor)
    days = max(1, min(int(days or 30), 365))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    rows = get_db().execute(
        """
        SELECT event_type,outcome,COUNT(*) c
        FROM partner_api_audit_events
        WHERE created_at>=?
        GROUP BY event_type,outcome
        """,
        (cutoff,),
    ).fetchall()
    counts = {}
    total = 0
    for row in rows:
        key = f"{row['event_type']}:{row['outcome']}"
        counts[key] = int(row["c"] or 0)
        total += int(row["c"] or 0)
    return {
        "window_days": days,
        "event_count": total,
        "event_outcomes": counts,
        "truth_notice": (
            "Audit metadata excludes clinical payloads and patient medical information. "
            "It records operational identifiers, scopes, entities and outcomes only."
        ),
    }


def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        normalized = str(key).strip().lower()
        if normalized in FORBIDDEN_METADATA_KEYS:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            clean[str(key)[:120]] = value if not isinstance(value, str) else value[:500]
        elif isinstance(value, (list, tuple, set)):
            clean[str(key)[:120]] = [str(item)[:120] for item in list(value)[:50]]
    return clean
