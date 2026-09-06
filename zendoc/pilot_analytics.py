"""Pilot-readiness analytics computed from real ZENDOC operational data."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .db import get_db


def pilot_scorecard() -> dict[str, Any]:
    db = get_db()

    providers = _provider_funnel(db)
    journeys = _care_journey_metrics(db)
    carefin = _carefin_metrics(db)
    fulfilment = _fulfilment_metrics(db)
    diagnostics = _diagnostic_metrics(db)
    data_coverage = _data_coverage_metrics(db)
    operations = _operations_metrics(db)

    return {
        "status": "OK",
        "providers": providers,
        "care_journeys": journeys,
        "carefin": carefin,
        "fulfilment": fulfilment,
        "diagnostics": diagnostics,
        "data_coverage": data_coverage,
        "operations": operations,
        "measurement_boundary": (
            "Metrics are computed from ZENDOC database events/records only. "
            "They do not estimate offline outcomes, partner-side actions, clinical efficacy, or unreported savings."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _provider_funnel(db) -> dict:
    total = _count(db, "SELECT COUNT(*) c FROM provider_profiles")
    pending = _count(db, "SELECT COUNT(*) c FROM provider_profiles WHERE verification_status='pending'")
    verified = _count(db, "SELECT COUNT(*) c FROM provider_profiles WHERE verification_status='verified'")
    rejected = _count(db, "SELECT COUNT(*) c FROM provider_profiles WHERE verification_status='rejected'")
    suspended = _count(db, "SELECT COUNT(*) c FROM provider_profiles WHERE verification_status='suspended'")
    with_evidence = _count(
        db,
        "SELECT COUNT(DISTINCT provider_profile_id) c FROM provider_verification_evidence",
    )
    with_verified_evidence = _count(
        db,
        "SELECT COUNT(DISTINCT provider_profile_id) c FROM provider_verification_evidence WHERE status='verified'",
    )
    with_schedule = _count(
        db,
        "SELECT COUNT(DISTINCT provider_profile_id) c FROM provider_schedules WHERE active=1",
    )
    return {
        "profiles_total": total,
        "pending": pending,
        "verified": verified,
        "rejected": rejected,
        "suspended": suspended,
        "with_submitted_evidence": with_evidence,
        "with_verified_evidence": with_verified_evidence,
        "with_active_schedule": with_schedule,
        "verified_rate_percent": _percent(verified, total),
        "evidence_submission_rate_percent": _percent(with_evidence, total),
    }


def _care_journey_metrics(db) -> dict:
    total = _count(db, "SELECT COUNT(*) c FROM care_journeys")
    active = _count(db, "SELECT COUNT(*) c FROM care_journeys WHERE status='active'")
    completed = _count(db, "SELECT COUNT(*) c FROM care_journeys WHERE status='completed'")
    blocked = _count(db, "SELECT COUNT(*) c FROM care_journeys WHERE status='blocked'")
    transitions = _count(db, "SELECT COUNT(*) c FROM care_journey_events")
    states = {
        row["state"]: row["count"]
        for row in db.execute(
            "SELECT state, COUNT(*) count FROM care_journeys GROUP BY state ORDER BY count DESC"
        ).fetchall()
    }
    return {
        "total": total,
        "active": active,
        "completed": completed,
        "blocked": blocked,
        "transition_events": transitions,
        "completion_rate_percent": _percent(completed, total),
        "states": states,
    }


def _carefin_metrics(db) -> dict:
    discoveries = _count(
        db,
        "SELECT COUNT(*) c FROM audit_logs WHERE action='carefin.discovery'",
    )
    unique_users = _count(
        db,
        "SELECT COUNT(DISTINCT actor_id) c FROM audit_logs WHERE action='carefin.discovery'",
    )
    return {
        "discovery_runs": discoveries,
        "unique_users_with_discovery": unique_users,
        "authoritative_confirmations": 0,
        "confirmed_savings_inr": None,
        "truth_notice": (
            "CareFin v1 records public discovery activity. Personal authoritative coverage/approval/payment "
            "is not persisted as a claimed metric until a partner-authoritative workflow exists."
        ),
    }


def _fulfilment_metrics(db) -> dict:
    staged = _count(db, "SELECT COUNT(*) c FROM fulfilment_plans")
    confirmed_plans = _count(
        db,
        "SELECT COUNT(*) c FROM fulfilment_plans WHERE confirmed_by_user=1",
    )
    orders = _count(db, "SELECT COUNT(*) c FROM medicine_orders")
    acknowledged = _count(
        db,
        "SELECT COUNT(*) c FROM medicine_orders WHERE LOWER(COALESCE(acknowledgement_status,'')) IN ('accepted','acknowledged')",
    )
    delivered = _count(
        db,
        "SELECT COUNT(*) c FROM medicine_orders WHERE UPPER(COALESCE(tracking_status,''))='DELIVERED'",
    )
    return {
        "fulfilment_plans": staged,
        "user_confirmed_plans": confirmed_plans,
        "orders_submitted": orders,
        "provider_acknowledged": acknowledged,
        "delivered": delivered,
        "plan_to_order_conversion_percent": _percent(orders, staged),
        "order_acknowledgement_rate_percent": _percent(acknowledged, orders),
        "delivery_completion_rate_percent": _percent(delivered, orders),
        "average_acknowledgement_minutes": _average_duration_minutes(
            db.execute(
                """
                SELECT created_at, acknowledged_at
                FROM medicine_orders
                WHERE acknowledged_at IS NOT NULL
                """
            ).fetchall(),
            "created_at",
            "acknowledged_at",
        ),
    }


def _diagnostic_metrics(db) -> dict:
    offers = _count(db, "SELECT COUNT(*) c FROM diagnostic_offers")
    bookings = _count(db, "SELECT COUNT(*) c FROM diagnostic_bookings")
    completed = _count(
        db,
        "SELECT COUNT(*) c FROM diagnostic_bookings WHERE LOWER(status)='completed'",
    )
    report_linked = _count(
        db,
        "SELECT COUNT(*) c FROM diagnostic_bookings WHERE report_record_id IS NOT NULL",
    )
    return {
        "provider_offers": offers,
        "bookings_requested": bookings,
        "completed": completed,
        "report_linked": report_linked,
        "completion_rate_percent": _percent(completed, bookings),
        "report_link_rate_percent": _percent(report_linked, completed),
    }


def _data_coverage_metrics(db) -> dict:
    geography_nodes = _count(db, "SELECT COUNT(*) c FROM geography_nodes")
    official_entities = _count(db, "SELECT COUNT(*) c FROM public_healthcare_entities WHERE active=1")
    ingestion_batches = _count(
        db,
        "SELECT COUNT(*) c FROM data_ingestion_batches WHERE dry_run=0 AND status='completed'",
    )
    sources = {
        row["source_id"]: row["count"]
        for row in db.execute(
            """
            SELECT source_id, COUNT(*) count
            FROM public_healthcare_entities
            WHERE active=1
            GROUP BY source_id
            ORDER BY count DESC
            """
        ).fetchall()
    }
    return {
        "geography_nodes": geography_nodes,
        "official_public_healthcare_entities": official_entities,
        "completed_ingestion_batches": ingestion_batches,
        "healthcare_entities_by_source": sources,
    }


def _operations_metrics(db) -> dict:
    agent_tasks = _count(db, "SELECT COUNT(*) c FROM agent_tasks")
    failed = _count(db, "SELECT COUNT(*) c FROM agent_tasks WHERE status='failed'")
    waiting = _count(
        db,
        "SELECT COUNT(*) c FROM agent_tasks WHERE status IN ('waiting_human','waiting_approval')",
    )
    active_alerts = _count(db, "SELECT COUNT(*) c FROM agent_alerts WHERE status='active'")
    consultations = _count(db, "SELECT COUNT(*) c FROM consultation_requests")
    consultation_accepted = _count(
        db,
        "SELECT COUNT(*) c FROM consultation_requests WHERE status IN ('accepted','confirmed','active','completed')",
    )
    return {
        "agent_tasks": agent_tasks,
        "failed_agent_tasks": failed,
        "waiting_human_or_approval": waiting,
        "active_alerts": active_alerts,
        "consultation_requests": consultations,
        "consultations_progressed": consultation_accepted,
        "consultation_progression_rate_percent": _percent(consultation_accepted, consultations),
    }


def _count(db, sql: str, params=()) -> int:
    row = db.execute(sql, params).fetchone()
    return int(row["c"] or 0)


def _percent(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round((numerator / denominator) * 100.0, 1)


def _average_duration_minutes(rows, start_key: str, end_key: str) -> float | None:
    values = []
    for row in rows:
        start = _parse_time(row[start_key])
        end = _parse_time(row[end_key])
        if start and end and end >= start:
            values.append((end - start).total_seconds() / 60.0)
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def _parse_time(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
