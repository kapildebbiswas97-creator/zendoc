"""Bounded internal operations cycle for the ZENDOC AI-team model.

This worker automates reversible reliability work and aggregate reporting. It
does not deploy code, approve clinical/financial actions, change permissions,
or send patient marketing. Owner email is optional and uses the existing
verified transactional-email boundary.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from flask import current_app

from .agent_alerts import list_alerts
from .data_freshness import ingestion_freshness_report
from .database_reliability import readiness_report
from .db import get_db, now_iso
from .integration_readiness import integration_readiness_snapshot
from .notification_providers import deliver_notification
from .operations_automation import run_safe_operations_automation
from .security import assert_owner


DIGEST_TEMPLATE = "owner_operations_digest"


def _recent_digest_exists(hours: int = 20) -> bool:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max(1, int(hours)))).isoformat(timespec="seconds")
    row = get_db().execute(
        """
        SELECT id FROM notification_deliveries
        WHERE template_type=? AND created_at>=?
        ORDER BY id DESC LIMIT 1
        """,
        (DIGEST_TEMPLATE, cutoff),
    ).fetchone()
    return bool(row)


def _digest_text(snapshot: dict) -> str:
    automation = snapshot["automation"]
    integrations = snapshot["integrations"]
    freshness = snapshot["freshness"]
    database = snapshot["database"]
    active_alerts = snapshot["active_alerts"]

    urgent_sources = [
        source for source in freshness.get("sources", [])
        if source.get("refresh_priority") in {"P0", "P1"}
    ]
    alert_counts = {}
    for alert in active_alerts:
        severity = str(alert.get("severity") or "info")
        alert_counts[severity] = alert_counts.get(severity, 0) + 1

    lines = [
        "ZENDOC owner operations digest",
        f"Generated: {snapshot['generated_at']}",
        "",
        "Reliability",
        f"- Database: {database.get('status', 'unknown')}",
        f"- Active alerts: {len(active_alerts)} ({', '.join(f'{k}={v}' for k, v in sorted(alert_counts.items())) or 'none'})",
        f"- Safe task retries re-queued: {automation.get('requeued_count', 0)}",
        f"- Tasks waiting for human/approval: {automation.get('waiting_human_or_approval', 0)}",
        f"- Permanent/exhausted failures: {automation.get('permanent_or_exhausted_failures', 0)}",
        "",
        "Integrations",
        f"- Ready boundaries: {integrations.get('ready_count', 0)}/{integrations.get('total_count', 0)}",
        f"- External blockers requiring credentials/partners/runtime proof: {integrations.get('external_blocker_count', 0)}",
        "",
        "Official/public data",
        f"- Registered sources: {freshness.get('source_count', 0)}",
        f"- P0/P1 refresh sources: {len(urgent_sources)}",
    ]
    if urgent_sources:
        lines.append(
            "- Highest-priority sources: "
            + ", ".join(str(item.get("source_id")) for item in urgent_sources[:12])
        )
    lines.extend([
        "",
        "Safety boundary",
        "- No autonomous prescribing, emergency dispatch, payment execution, permission changes, or production code deployment occurred.",
        "- Review active alerts, failed tasks, integration blockers, and data-refresh evidence before consequential changes.",
    ])
    return "\n".join(lines)[:12000]


def run_owner_operations_cycle(
    actor: Any,
    *,
    email_owner: bool = True,
    force_digest: bool = False,
) -> dict:
    """Run one bounded operations cycle and emit a deduplicated owner digest."""
    assert_owner(actor)

    automation = run_safe_operations_automation(actor)
    integrations = integration_readiness_snapshot()
    freshness = ingestion_freshness_report(actor, recent_batch_limit=20)
    database = readiness_report()
    active_alerts = list_alerts("active", limit=100)

    snapshot = {
        "generated_at": now_iso(),
        "automation": automation,
        "integrations": integrations,
        "freshness": freshness,
        "database": database,
        "active_alerts": active_alerts,
    }

    digest_sent = False
    deliveries = []
    if force_digest or not _recent_digest_exists():
        body = _digest_text(snapshot)
        in_app = deliver_notification(
            int(actor["id"]),
            "ZENDOC daily operations digest",
            body,
            channel="in_app",
            template_type=DIGEST_TEMPLATE,
        )
        deliveries.append(in_app.to_dict())
        digest_sent = True

        if (
            email_owner
            and bool(current_app.config.get("EMAIL_VERIFIED"))
            and str(current_app.config.get("EMAIL_PROVIDER") or "").strip().lower() == "smtp"
        ):
            email = deliver_notification(
                int(actor["id"]),
                "ZENDOC daily operations digest",
                body,
                channel="email",
                template_type=DIGEST_TEMPLATE,
            )
            deliveries.append(email.to_dict())

    get_db().commit()
    return {
        "status": "completed",
        "generated_at": snapshot["generated_at"],
        "digest_created": digest_sent,
        "deliveries": deliveries,
        "database_status": database.get("status"),
        "active_alert_count": len(active_alerts),
        "integration_blocker_count": integrations.get("external_blocker_count", 0),
        "urgent_data_source_count": sum(
            1 for source in freshness.get("sources", [])
            if source.get("refresh_priority") in {"P0", "P1"}
        ),
        "automation": {
            "requeued_count": automation.get("requeued_count", 0),
            "waiting_human_or_approval": automation.get("waiting_human_or_approval", 0),
            "permanent_or_exhausted_failures": automation.get("permanent_or_exhausted_failures", 0),
        },
        "safety": automation.get("safety", {}),
    }
