"""
ZENDOC Agent Alerts — Milestone 8
Proactive, deterministic/event-based operational alerts.

Does NOT pretend an AI is "continuously thinking."
Detects real operational states: overdue tasks, failed operations,
approval waiting too long, high error rates, etc.

Alert statuses: active → acknowledged → resolved
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .db import get_db, now_iso


ALERT_SEVERITIES = ("critical", "high", "medium", "low", "info")
ALERT_CATEGORIES = (
    "agent_failure",
    "approval_waiting",
    "consultation_overdue",
    "staff_task_overdue",
    "provider_unavailable",
    "platform_error_rate",
    "iot_alert",
    "inventory_stale",
    "diagnostic_stale",
    "provider_waiting",
    "security",
    "database",
    "emergency",
    "rate_limit",
    "integration",
    "operational",
)


def create_alert(
    severity: str,
    category: str,
    title: str,
    summary: str,
    source_type: str | None = None,
    source_id: str | None = None,
) -> dict:
    """Create a new operational alert."""
    if severity not in ALERT_SEVERITIES:
        severity = "info"
    if category not in ALERT_CATEGORIES:
        category = "operational"
    now = now_iso()
    db = get_db()
    dedupe_key = f"{category}:{source_type or 'platform'}:{source_id or title}"[:240]
    existing = db.execute(
        "SELECT * FROM agent_alerts WHERE dedupe_key=? AND status='active' LIMIT 1",
        (dedupe_key,),
    ).fetchone()
    if existing:
        return dict(existing)
    cursor = db.execute(
        """
        INSERT INTO agent_alerts
        (severity, category, title, summary, source_type, source_id, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'active', ?)
        """,
        (severity, category, title[:200], summary[:1000], source_type, source_id, now),
    )
    alert_id = cursor.lastrowid
    db.execute("UPDATE agent_alerts SET dedupe_key=? WHERE id=?", (dedupe_key, alert_id))
    db.commit()
    alert = get_alert(alert_id)
    _publish_alert_event(alert, "created")
    return alert


def get_alert(alert_id: int) -> dict:
    row = get_db().execute("SELECT * FROM agent_alerts WHERE id=?", (int(alert_id),)).fetchone()
    if not row:
        raise LookupError(f"Alert #{alert_id} not found.")
    return dict(row)


def list_alerts(status: str | None = "active", limit: int = 50) -> list[dict]:
    db = get_db()
    limit = max(1, min(int(limit or 50), 200))
    if status:
        rows = db.execute(
            "SELECT * FROM agent_alerts WHERE status=? ORDER BY created_at DESC LIMIT ?",
            (status, limit),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM agent_alerts ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def acknowledge_alert(alert_id: int, actor: dict) -> dict:
    """Mark alert as acknowledged (owner/admin only)."""
    from .security import assert_owner
    assert_owner(actor)
    alert = get_alert(alert_id)
    if alert["status"] != "active":
        raise ValueError(f"Alert #{alert_id} is already '{alert['status']}'.")
    db = get_db()
    db.execute(
        "UPDATE agent_alerts SET status='acknowledged', acknowledged_at=?, acknowledged_by=? WHERE id=?",
        (now_iso(), int(_value(actor, "id", 0) or 0), int(alert_id)),
    )
    db.commit()
    alert = get_alert(alert_id)
    _publish_alert_event(alert, "acknowledged", actor)
    return alert


def resolve_alert(alert_id: int, actor: dict) -> dict:
    """Resolve an alert (owner/admin only)."""
    from .security import assert_owner
    assert_owner(actor)
    alert = get_alert(alert_id)
    if alert["status"] == "resolved":
        raise ValueError(f"Alert #{alert_id} is already resolved.")
    db = get_db()
    db.execute(
        """
        UPDATE agent_alerts
        SET status='resolved', acknowledged_at=COALESCE(acknowledged_at, ?),
            acknowledged_by=COALESCE(acknowledged_by, ?), resolved_at=?, resolved_by=?
        WHERE id=?
        """,
        (now_iso(), int(_value(actor, "id", 0) or 0), now_iso(), int(_value(actor, "id", 0) or 0), int(alert_id)),
    )
    db.commit()
    alert = get_alert(alert_id)
    _publish_alert_event(alert, "resolved", actor)
    return alert


def run_proactive_alert_check() -> list[dict]:
    """
    Deterministic check for operational issues. Returns list of newly created alerts.
    Call this from owner command or scheduled task — NOT on every request.
    """
    created = []
    db = get_db()
    try:
        from .observability import prune_observability
        prune_observability()
    except Exception:
        pass
    now_dt = datetime.now(timezone.utc)

    # 1. Pending owner approvals waiting > 6 hours
    cutoff_6h = (now_dt - timedelta(hours=6)).isoformat(timespec="seconds")
    old_approvals = db.execute(
        """
        SELECT COUNT(*) c FROM agent_approvals
        WHERE status='pending'
        AND created_at < ?
        """,
        (cutoff_6h,),
    ).fetchone()["c"]
    if old_approvals > 0:
        created.append(_maybe_create_alert(
            "high", "approval_waiting",
            f"{old_approvals} Approval(s) Waiting > 6 Hours",
            f"{old_approvals} owner-level approval(s) have been pending for more than 6 hours.",
        ))

    # 2. Failed agent tasks with retries exhausted
    cutoff_24h = (now_dt - timedelta(hours=24)).isoformat(timespec="seconds")
    perm_failed = db.execute(
        """
        SELECT COUNT(*) c FROM agent_tasks
        WHERE status='failed' AND attempt_count >= max_attempts
        AND created_at > ?
        """,
        (cutoff_24h,),
    ).fetchone()["c"]
    if perm_failed > 0:
        created.append(_maybe_create_alert(
            "medium", "agent_failure",
            f"{perm_failed} Agent Task(s) Permanently Failed",
            f"{perm_failed} agent task(s) exhausted all retry attempts in the last 24 hours.",
        ))

    # 3. High platform error event rate
    cutoff_1h = (now_dt - timedelta(hours=1)).isoformat(timespec="seconds")
    error_count = db.execute(
        """
        SELECT COUNT(*) c FROM platform_events
        WHERE status IN ('failed','error')
        AND created_at > ?
        """,
        (cutoff_1h,),
    ).fetchone()["c"]
    if error_count >= 10:
        created.append(_maybe_create_alert(
            "high", "platform_error_rate",
            f"High Error Rate: {error_count} Errors in Last Hour",
            f"Platform recorded {error_count} failed/error events in the last hour.",
        ))


    # 4. Confirmed pharmacy inventory observations that are now stale (> 2 hours)
    cutoff_inventory = (now_dt - timedelta(hours=2)).isoformat(timespec="seconds")
    stale_inventory = db.execute(
        """
        SELECT COUNT(*) c FROM inventory_observations
        WHERE UPPER(COALESCE(data_mode, 'LIVE'))='LIVE'
          AND UPPER(COALESCE(stock_status, 'UNKNOWN'))='CONFIRMED'
          AND observed_at < ?
        """,
        (cutoff_inventory,),
    ).fetchone()["c"]
    if stale_inventory > 0:
        created.append(_maybe_create_alert(
            "medium", "inventory_stale",
            "Stale Pharmacy Inventory Requires Refresh",
            f"{stale_inventory} confirmed pharmacy inventory observation(s) are older than 2 hours and must not be treated as current.",
        ))

    # 5. Verified diagnostic offers whose observation is stale (> configured 24h default)
    cutoff_diagnostic = (now_dt - timedelta(hours=24)).isoformat(timespec="seconds")
    stale_diagnostics = db.execute(
        """
        SELECT COUNT(*) c FROM diagnostic_offers
        WHERE UPPER(COALESCE(data_mode, 'LIVE'))='LIVE'
          AND COALESCE(verified, 0)=1
          AND COALESCE(observed_at, created_at) < ?
        """,
        (cutoff_diagnostic,),
    ).fetchone()["c"]
    if stale_diagnostics > 0:
        created.append(_maybe_create_alert(
            "medium", "diagnostic_stale",
            "Stale Diagnostic Offers Require Verification",
            f"{stale_diagnostics} verified diagnostic offer(s) are older than 24 hours and should be refreshed before booking.",
        ))

    # 6. Provider acknowledgements waiting > 2 hours
    cutoff_provider = (now_dt - timedelta(hours=2)).isoformat(timespec="seconds")
    pending_orders = db.execute(
        """
        SELECT COUNT(*) c FROM medicine_orders
        WHERE LOWER(COALESCE(acknowledgement_status, 'pending'))='pending'
          AND created_at < ?
        """,
        (cutoff_provider,),
    ).fetchone()["c"]
    pending_consults = db.execute(
        """
        SELECT COUNT(*) c FROM consultation_requests
        WHERE LOWER(COALESCE(status, 'requested'))='requested'
          AND created_at < ?
        """,
        (cutoff_provider,),
    ).fetchone()["c"]
    if pending_orders or pending_consults:
        created.append(_maybe_create_alert(
            "medium", "provider_waiting",
            "Provider Responses Waiting Too Long",
            f"{pending_orders} medicine order(s) and {pending_consults} consultation request(s) have waited more than 2 hours for provider action.",
        ))

    # 7. Database readiness failure is a platform-critical incident.
    try:
        from .database_reliability import readiness_report
        readiness = readiness_report()
        if readiness.get("status") != "ready":
            created.append(_maybe_create_alert(
                "critical", "database",
                "Database Readiness Failed",
                "Database readiness is not healthy. Traffic should remain gated until connectivity, schema, migrations, and integrity checks recover.",
            ))
        elif int(readiness.get("database_latency_ms") or 0) >= 1000:
            created.append(_maybe_create_alert(
                "medium", "database",
                "Database Probe Latency Is High",
                f"Database readiness probe latency is {int(readiness.get('database_latency_ms') or 0)} ms.",
            ))
    except Exception:
        created.append(_maybe_create_alert(
            "critical", "database",
            "Database Readiness Check Failed",
            "ZENDOC could not complete its database readiness assessment.",
        ))

    # 8. Emergency-path errors must never be buried in general error totals.
    emergency_failures = db.execute(
        """
        SELECT COUNT(*) c FROM platform_events
        WHERE created_at > ?
          AND status IN ('failed','error')
          AND (event_type LIKE '%.emergency%' OR action LIKE '%emergency%')
        """,
        (cutoff_1h,),
    ).fetchone()["c"]
    if emergency_failures > 0:
        created.append(_maybe_create_alert(
            "critical", "emergency",
            "Emergency Flow Failure Detected",
            f"{emergency_failures} failed/error emergency-path event(s) were recorded in the last hour.",
        ))

    # 9. HTTP server-error and abuse/rate-limit signals from privacy-safe metadata.
    http_errors = db.execute(
        """
        SELECT COUNT(*) c FROM request_observations
        WHERE created_at > ? AND status_code >= 500
        """,
        (cutoff_1h,),
    ).fetchone()["c"]
    if http_errors >= 5:
        created.append(_maybe_create_alert(
            "high", "platform_error_rate",
            "Sustained HTTP Server Errors",
            f"{http_errors} HTTP 5xx response(s) were recorded in the last hour.",
        ))

    rate_limited = db.execute(
        """
        SELECT COUNT(*) c FROM request_observations
        WHERE created_at > ? AND status_code = 429
        """,
        (cutoff_1h,),
    ).fetchone()["c"]
    if rate_limited >= 20:
        created.append(_maybe_create_alert(
            "medium", "rate_limit",
            "High Rate-Limit Activity",
            f"{rate_limited} HTTP 429 response(s) were recorded in the last hour; review abuse/load patterns without inspecting request bodies.",
        ))

    return [a for a in created if a is not None]


def _maybe_create_alert(severity: str, category: str, title: str, summary: str) -> dict | None:
    """Only create alert if one with same title is not already active."""
    existing = get_db().execute(
        "SELECT id FROM agent_alerts WHERE title=? AND status='active' LIMIT 1",
        (title,),
    ).fetchone()
    if existing:
        return None
    return create_alert(severity, category, title, summary)


def _value(actor, key, default=None):
    if actor is None:
        return default
    if hasattr(actor, "keys") and key in actor.keys():
        return actor[key]
    return actor.get(key, default) if isinstance(actor, dict) else default


def _publish_alert_event(alert: dict, transition: str, actor=None):
    try:
        from .event_bus import publish_event
        publish_event(
            f"agent.alert.{transition}",
            actor=actor,
            entity_type="agent_alert",
            entity_id=str(alert["id"]),
            status=alert["status"],
            payload={"severity": alert["severity"], "category": alert["category"]},
        )
    except Exception:
        pass
