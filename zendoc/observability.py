"""Production observability and incident recovery helpers."""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone

from flask import current_app, g, request

from .audit_privacy import redact_operational_text
from .capability_registry import get_capability_registry
from .database_reliability import readiness_report
from .db import get_db, now_iso
from .infrastructure import infrastructure_status


def _observability_connection():
    """Open an isolated connection so telemetry never commits business work."""
    if current_app.config.get("DATABASE_ENGINE") == "postgresql":
        from .postgres_backend import connect_postgresql
        return connect_postgresql(current_app.config["DATABASE_URL"])

    import sqlite3
    connection = sqlite3.connect(current_app.config["DATABASE"], timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 3000")
    return connection


def _value(actor, key, default=None):
    if actor is None:
        return default
    if hasattr(actor, "keys") and key in actor.keys():
        return actor[key]
    return actor.get(key, default) if isinstance(actor, dict) else default


def start_request_observation():
    incoming = str(request.headers.get("X-Request-ID") or request.headers.get("X-Correlation-ID") or "").strip()
    safe = "".join(ch for ch in incoming if ch.isalnum() or ch in "-_.")[:80]
    g.correlation_id = safe or uuid.uuid4().hex
    g.request_started_at = time.perf_counter()


def finish_request_observation(response):
    correlation_id = str(getattr(g, "correlation_id", "") or uuid.uuid4().hex)[:80]
    started = getattr(g, "request_started_at", None)
    duration_ms = int((time.perf_counter() - started) * 1000) if started is not None else 0
    actor = getattr(g, "observability_actor", None) or getattr(g, "user", None)
    route_pattern = request.url_rule.rule if request.url_rule is not None else "unmatched"
    error_class = None
    if response.status_code >= 500:
        error_class = "server_error"
    elif response.status_code == 429:
        error_class = "rate_limited"
    elif response.status_code in {401, 403}:
        error_class = "authorization_denied"

    # Do not record request body, query string, headers, raw path parameters,
    # symptoms, medical text, addresses, credentials, or tokens.
    telemetry_db = None
    try:
        telemetry_db = _observability_connection()
        telemetry_db.execute(
            """
            INSERT INTO request_observations
            (correlation_id,actor_id,actor_role,method,route_pattern,status_code,duration_ms,error_class,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                correlation_id,
                int(_value(actor, "id", 0) or 0) or None,
                str(_value(actor, "role", "") or "")[:40] or None,
                request.method[:10],
                str(route_pattern)[:200],
                int(response.status_code),
                max(0, duration_ms),
                error_class,
                now_iso(),
            ),
        )
        telemetry_db.commit()
    except Exception:
        if telemetry_db is not None:
            try:
                telemetry_db.rollback()
            except Exception:
                pass
        current_app.logger.exception("Failed to persist request observation.")
    finally:
        if telemetry_db is not None:
            try:
                telemetry_db.close()
            except Exception:
                pass

    response.headers["X-Request-ID"] = correlation_id
    return response


def request_metrics(window_minutes=60):
    db = get_db()
    window_minutes = max(1, min(int(window_minutes or 60), 24 * 60))
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=window_minutes)).isoformat(timespec="seconds")
    totals = db.execute(
        """
        SELECT
          COUNT(*) total,
          SUM(CASE WHEN status_code>=500 THEN 1 ELSE 0 END) server_errors,
          SUM(CASE WHEN status_code=429 THEN 1 ELSE 0 END) rate_limited,
          SUM(CASE WHEN status_code IN (401,403) THEN 1 ELSE 0 END) authorization_denied,
          AVG(duration_ms) avg_duration_ms,
          MAX(duration_ms) max_duration_ms
        FROM request_observations
        WHERE created_at>=?
        """,
        (cutoff,),
    ).fetchone()
    slow = db.execute(
        """
        SELECT route_pattern, COUNT(*) count, ROUND(AVG(duration_ms),1) avg_duration_ms, MAX(duration_ms) max_duration_ms
        FROM request_observations
        WHERE created_at>=?
        GROUP BY route_pattern
        ORDER BY avg_duration_ms DESC
        LIMIT 10
        """,
        (cutoff,),
    ).fetchall()
    errors = db.execute(
        """
        SELECT route_pattern, status_code, COUNT(*) count
        FROM request_observations
        WHERE created_at>=? AND status_code>=400
        GROUP BY route_pattern,status_code
        ORDER BY count DESC
        LIMIT 20
        """,
        (cutoff,),
    ).fetchall()
    return {
        "window_minutes": window_minutes,
        "total": int(totals["total"] or 0),
        "server_errors": int(totals["server_errors"] or 0),
        "rate_limited": int(totals["rate_limited"] or 0),
        "authorization_denied": int(totals["authorization_denied"] or 0),
        "avg_duration_ms": round(float(totals["avg_duration_ms"] or 0), 1),
        "max_duration_ms": int(totals["max_duration_ms"] or 0),
        "slow_routes": [dict(row) for row in slow],
        "error_routes": [dict(row) for row in errors],
    }


def agent_metrics(window_minutes=60):
    db = get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=max(1, int(window_minutes)))).isoformat(timespec="seconds")
    row = db.execute(
        """
        SELECT
          COUNT(*) total,
          SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) failed,
          SUM(CASE WHEN urgency='emergency' THEN 1 ELSE 0 END) emergency,
          AVG(duration_ms) avg_duration_ms
        FROM agent_runs
        WHERE created_at>=?
        """,
        (cutoff,),
    ).fetchone()
    total = int(row["total"] or 0)
    failed = int(row["failed"] or 0)
    return {
        "window_minutes": max(1, int(window_minutes)),
        "total": total,
        "failed": failed,
        "failure_rate": round(failed / total, 4) if total else 0.0,
        "emergency_runs": int(row["emergency"] or 0),
        "avg_duration_ms": round(float(row["avg_duration_ms"] or 0), 1),
    }


def emergency_metrics(window_minutes=60):
    db = get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=max(1, int(window_minutes)))).isoformat(timespec="seconds")
    row = db.execute(
        """
        SELECT COUNT(*) c,
               SUM(CASE WHEN status IN ('failed','error') THEN 1 ELSE 0 END) failed
        FROM platform_events
        WHERE created_at>=?
          AND (event_type LIKE '%.emergency%' OR action LIKE '%emergency%')
        """,
        (cutoff,),
    ).fetchone()
    return {
        "window_minutes": max(1, int(window_minutes)),
        "events": int(row["c"] or 0),
        "failed": int(row["failed"] or 0),
    }


def integration_truth_status():
    infra = infrastructure_status()
    capabilities = get_capability_registry()
    keys = (
        "cloud_llm",
        "healthcare_finder",
        "telehealth",
        "external_notifications",
        "postgresql",
        "official_live_connectors",
    )
    return {
        "infrastructure": infra,
        "capabilities": {
            key: capabilities.get(key)
            for key in keys
            if capabilities.get(key) is not None
        },
    }


def record_integration_health(integration_key, status, latency_ms=None, detail=None):
    status = str(status or "unknown").strip().upper()
    if status not in {"HEALTHY", "DEGRADED", "DOWN", "INTEGRATION_REQUIRED", "UNKNOWN"}:
        status = "UNKNOWN"
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO integration_health_checks
        (integration_key,status,latency_ms,detail,checked_at)
        VALUES (?,?,?,?,?)
        """,
        (
            str(integration_key or "unknown")[:100],
            status,
            int(latency_ms) if latency_ms is not None else None,
            redact_operational_text(detail, 240),
            now_iso(),
        ),
    )
    db.commit()
    return int(cursor.lastrowid)


def recent_integration_health(limit=50):
    rows = get_db().execute(
        """
        SELECT * FROM integration_health_checks
        ORDER BY checked_at DESC
        LIMIT ?
        """,
        (max(1, min(int(limit or 50), 200)),),
    ).fetchall()
    return [dict(row) for row in rows]


def incident_summary(window_minutes=60):
    req = request_metrics(window_minutes)
    agents = agent_metrics(window_minutes)
    emergency = emergency_metrics(window_minutes)
    readiness = readiness_report()
    active_alerts = get_db().execute(
        """
        SELECT severity,category,title,created_at
        FROM agent_alerts
        WHERE status='active'
        ORDER BY
          CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
          created_at DESC
        LIMIT 50
        """
    ).fetchall()
    status = "normal"
    if readiness.get("status") != "ready" or req["server_errors"] >= 10 or emergency["failed"] > 0:
        status = "incident"
    elif req["server_errors"] > 0 or agents["failure_rate"] >= 0.1:
        status = "degraded"
    return {
        "status": status,
        "readiness": readiness,
        "requests": req,
        "agents": agents,
        "emergency": emergency,
        "active_alerts": [dict(row) for row in active_alerts],
        "integrations": integration_truth_status(),
        "recent_integration_checks": recent_integration_health(20),
    }


RUNBOOKS = {
    "database_outage": {
        "severity": "critical",
        "trigger": "Readiness reports database unreachable/not ready or sustained database 5xx failures.",
        "containment": [
            "Stop accepting write traffic by relying on readiness/503 and deployment health checks.",
            "Do not run destructive migration or manual SQL against an unknown database state.",
            "Confirm database provider status and connection configuration without exposing DATABASE_URL.",
        ],
        "recovery": [
            "Restore connectivity or managed database service.",
            "Run readiness and required migration/schema checks.",
            "For SQLite only, use a verified backup snapshot if the database integrity check fails.",
            "Resume traffic only after readiness returns ready.",
        ],
    },
    "ai_provider_outage": {
        "severity": "high",
        "trigger": "Cloud/local AI provider unavailable or repeated model execution failures.",
        "containment": [
            "Keep deterministic safety/emergency logic active.",
            "Fall back to deterministic/local capabilities where supported.",
            "Mark AI-dependent features degraded/integration required instead of inventing answers.",
        ],
        "recovery": [
            "Verify provider health/configuration and bounded model test.",
            "Confirm safety gates remain functional before re-enabling normal routing.",
        ],
    },
    "provider_integration_outage": {
        "severity": "high",
        "trigger": "Maps, pharmacy, lab, telehealth, payment, notification, or ambulance partner failure.",
        "containment": [
            "Preserve intake/discovery where safe but label external action INTEGRATION_REQUIRED or degraded.",
            "Never claim dispatch, booking, payment, stock, message delivery, or provider acknowledgement succeeded without confirmation.",
        ],
        "recovery": [
            "Recheck external integration health and credentials.",
            "Replay only explicitly idempotent operations.",
            "Verify no duplicate orders/bookings/actions were created before resuming.",
        ],
    },
    "emergency_flow_failure": {
        "severity": "critical",
        "trigger": "Any failed/error event in the deterministic emergency escalation path.",
        "containment": [
            "Keep deterministic SafetyEngine guidance available even if AI or provider integrations are down.",
            "Do not route emergency messages into nutrition, finance, booking, or general AI convenience flows.",
        ],
        "recovery": [
            "Verify emergency-precedence tests and SafetyAgent path.",
            "Review only privacy-minimized operational metadata and correlation IDs.",
            "Resume normal routing only after safety-first behavior is confirmed.",
        ],
    },
    "deployment_rollback": {
        "severity": "high",
        "trigger": "New release fails startup/readiness or introduces severe regression.",
        "containment": [
            "Do not push additional schema-destructive changes.",
            "Rollback application release to the last known-good code while preserving database data.",
        ],
        "recovery": [
            "Run migration/schema/readiness checks against the preserved database.",
            "Reapply only additive/repeatable migrations after the faulty release is corrected.",
        ],
    },
}


def list_runbooks():
    return RUNBOOKS
