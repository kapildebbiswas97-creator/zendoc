"""Pilot-readiness analytics computed from real ZENDOC operational data."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .db import get_db
from .diagnostic_service import (
    AVAILABILITY_CONFIRMED,
    AVAILABILITY_OBSERVED,
    AVAILABILITY_STALE,
    AVAILABILITY_UNKNOWN,
    diagnostic_availability_state,
)
from .inventory_service import evaluate_freshness
from .observability import agent_metrics, request_metrics


def pilot_scorecard() -> dict[str, Any]:
    db = get_db()

    providers = _provider_funnel(db)
    journeys = _care_journey_metrics(db)
    carefin = _carefin_metrics(db)
    fulfilment = _fulfilment_metrics(db)
    diagnostics = _diagnostic_metrics(db)
    data_coverage = _data_coverage_metrics(db)
    operations = _operations_metrics(db)
    provider_responsiveness = _provider_response_metrics(db)
    data_freshness = _data_freshness_metrics(db)
    engagement = _engagement_metrics(db)
    reliability = _reliability_metrics()
    signals = _pilot_signals(
        provider_responsiveness=provider_responsiveness,
        data_freshness=data_freshness,
        engagement=engagement,
        reliability=reliability,
    )

    return {
        "status": "OK",
        "providers": providers,
        "care_journeys": journeys,
        "carefin": carefin,
        "fulfilment": fulfilment,
        "diagnostics": diagnostics,
        "data_coverage": data_coverage,
        "operations": operations,
        "provider_responsiveness": provider_responsiveness,
        "data_freshness": data_freshness,
        "engagement": engagement,
        "reliability": reliability,
        "signals": signals,
        "measurement_boundary": (
            "Metrics are computed from ZENDOC database events/records only. "
            "They do not estimate offline outcomes, partner-side actions, clinical efficacy, or unreported savings. "
            "Repeat activity is an observed product-usage proxy, not a cohort-retention claim."
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


def _provider_response_metrics(db) -> dict:
    order_rows = db.execute(
        """
        SELECT created_at, acknowledged_at
        FROM medicine_orders
        WHERE acknowledged_at IS NOT NULL
        """
    ).fetchall()
    order_minutes = _duration_values(order_rows, "created_at", "acknowledged_at", unit="minutes")
    order_total = _count(db, "SELECT COUNT(*) c FROM medicine_orders")
    order_responded = len(order_minutes)

    consultation_rows = db.execute(
        """
        SELECT cr.created_at, cr.updated_at, cr.status, room.created_at room_created_at
        FROM consultation_requests cr
        LEFT JOIN consultation_rooms room ON room.consultation_id=cr.id
        """
    ).fetchall()
    consultation_minutes = []
    responded_consultations = 0
    pending_consultations = 0
    for row in consultation_rows:
        status = str(row["status"] or "").strip().lower()
        response_at = row["room_created_at"]
        if not response_at and status == "rejected":
            response_at = row["updated_at"]
        if response_at:
            start = _parse_time(row["created_at"])
            end = _parse_time(response_at)
            if start and end and end >= start:
                consultation_minutes.append((end - start).total_seconds() / 60.0)
                responded_consultations += 1
        elif status == "requested":
            pending_consultations += 1

    consultation_total = len(consultation_rows)
    return {
        "medicine_orders": {
            "submitted": order_total,
            "provider_responded": order_responded,
            "response_rate_percent": _percent(order_responded, order_total),
            "average_response_minutes": _rounded_mean(order_minutes),
            "median_response_minutes": _median(order_minutes),
        },
        "consultations": {
            "requested": consultation_total,
            "provider_responded": responded_consultations,
            "pending": pending_consultations,
            "response_rate_percent": _percent(responded_consultations, consultation_total),
            "average_response_minutes": _rounded_mean(consultation_minutes),
            "median_response_minutes": _median(consultation_minutes),
        },
        "measurement_note": (
            "Medicine response uses acknowledged_at. Consultation response uses the first room-creation timestamp "
            "for accepted/scheduled requests and the terminal update timestamp for rejected requests."
        ),
    }


def _data_freshness_metrics(db) -> dict:
    inventory_counts = {"CONFIRMED": 0, "STALE": 0, "UNKNOWN": 0, "UNAVAILABLE": 0}
    stale_pharmacies = set()
    inventory_rows = db.execute(
        "SELECT pharmacy_id, observed_at, stock_status, quantity_available FROM inventory_observations"
    ).fetchall()
    for row in inventory_rows:
        state, _ = evaluate_freshness(row["observed_at"], row["stock_status"])
        if int(row["quantity_available"] or 0) <= 0 and state == "CONFIRMED":
            state = "UNAVAILABLE"
        inventory_counts[state] = inventory_counts.get(state, 0) + 1
        if state in {"STALE", "UNKNOWN"}:
            stale_pharmacies.add(int(row["pharmacy_id"]))

    diagnostic_counts = {
        AVAILABILITY_CONFIRMED: 0,
        AVAILABILITY_STALE: 0,
        AVAILABILITY_UNKNOWN: 0,
        AVAILABILITY_OBSERVED: 0,
    }
    stale_labs = set()
    diagnostic_rows = db.execute(
        "SELECT lab_id, verified, observed_at, created_at FROM diagnostic_offers"
    ).fetchall()
    for row in diagnostic_rows:
        state = diagnostic_availability_state(dict(row))
        diagnostic_counts[state] = diagnostic_counts.get(state, 0) + 1
        if state in {AVAILABILITY_STALE, AVAILABILITY_UNKNOWN, AVAILABILITY_OBSERVED}:
            stale_labs.add(int(row["lab_id"]))

    inventory_total = len(inventory_rows)
    diagnostic_total = len(diagnostic_rows)
    return {
        "pharmacy_inventory": {
            "total_observations": inventory_total,
            "states": inventory_counts,
            "needs_refresh": inventory_counts.get("STALE", 0) + inventory_counts.get("UNKNOWN", 0),
            "providers_needing_refresh": len(stale_pharmacies),
            "confirmed_rate_percent": _percent(inventory_counts.get("CONFIRMED", 0), inventory_total),
        },
        "diagnostic_offers": {
            "total_offers": diagnostic_total,
            "states": diagnostic_counts,
            "needs_refresh": (
                diagnostic_counts.get(AVAILABILITY_STALE, 0)
                + diagnostic_counts.get(AVAILABILITY_UNKNOWN, 0)
                + diagnostic_counts.get(AVAILABILITY_OBSERVED, 0)
            ),
            "providers_needing_refresh": len(stale_labs),
            "confirmed_rate_percent": _percent(diagnostic_counts.get(AVAILABILITY_CONFIRMED, 0), diagnostic_total),
        },
        "truth_notice": "Only fresh provider observations count as confirmed; stale/unknown data remains explicitly non-confirmed.",
    }


def _engagement_metrics(db) -> dict:
    now = datetime.now(timezone.utc)
    cutoff_30 = now - timedelta(days=30)
    cutoff_7 = now - timedelta(days=7)
    rows = db.execute(
        """
        SELECT actor_id, created_at
        FROM request_observations
        WHERE actor_id IS NOT NULL
        ORDER BY created_at DESC
        """
    ).fetchall()

    active_7 = set()
    active_30 = set()
    days_by_actor: dict[int, set[str]] = {}
    for row in rows:
        created = _parse_time(row["created_at"])
        if not created or created < cutoff_30:
            continue
        actor_id = int(row["actor_id"])
        active_30.add(actor_id)
        days_by_actor.setdefault(actor_id, set()).add(created.date().isoformat())
        if created >= cutoff_7:
            active_7.add(actor_id)

    returning_30 = {actor_id for actor_id, days in days_by_actor.items() if len(days) >= 2}
    return {
        "authenticated_active_users_7d": len(active_7),
        "authenticated_active_users_30d": len(active_30),
        "repeat_activity_users_30d": len(returning_30),
        "repeat_activity_rate_percent": _percent(len(returning_30), len(active_30)),
        "measurement_note": (
            "Repeat activity means an authenticated actor generated requests on at least two distinct UTC dates "
            "within 30 days. It is a product-usage proxy, not formal cohort retention."
        ),
    }


def _reliability_metrics() -> dict:
    requests = request_metrics(60)
    agents = agent_metrics(60)
    total_requests = int(requests["total"] or 0)
    server_errors = int(requests["server_errors"] or 0)
    return {
        "window_minutes": 60,
        "requests": {
            "total": total_requests,
            "server_errors": server_errors,
            "server_error_rate_percent": _percent(server_errors, total_requests),
            "rate_limited": int(requests["rate_limited"] or 0),
            "authorization_denied": int(requests["authorization_denied"] or 0),
            "average_duration_ms": requests["avg_duration_ms"],
            "max_duration_ms": requests["max_duration_ms"],
        },
        "agents": {
            "runs": int(agents["total"] or 0),
            "failed": int(agents["failed"] or 0),
            "failure_rate_percent": round(float(agents["failure_rate"] or 0) * 100.0, 1),
            "emergency_runs": int(agents["emergency_runs"] or 0),
            "average_duration_ms": agents["avg_duration_ms"],
        },
    }


def _pilot_signals(*, provider_responsiveness: dict, data_freshness: dict, engagement: dict, reliability: dict) -> list[dict]:
    signals: list[dict] = []

    request_total = int(reliability["requests"]["total"] or 0)
    request_error_rate = reliability["requests"]["server_error_rate_percent"]
    if request_total < 20:
        signals.append({
            "key": "request_reliability",
            "status": "NO_DATA",
            "severity": "info",
            "message": "Fewer than 20 requests are available in the 60-minute reliability window.",
        })
    elif request_error_rate is not None and request_error_rate >= 5:
        signals.append({
            "key": "request_reliability",
            "status": "ATTENTION",
            "severity": "high",
            "message": f"Server error rate is {request_error_rate}% in the current 60-minute window.",
        })
    else:
        signals.append({
            "key": "request_reliability",
            "status": "OK",
            "severity": "info",
            "message": "Recent request reliability is within the current pilot guardrail.",
        })

    inventory = data_freshness["pharmacy_inventory"]
    inventory_total = int(inventory["total_observations"] or 0)
    if inventory_total == 0:
        signals.append({
            "key": "pharmacy_freshness",
            "status": "NO_DATA",
            "severity": "info",
            "message": "No pharmacy inventory observations are available yet.",
        })
    else:
        refresh_rate = _percent(int(inventory["needs_refresh"] or 0), inventory_total)
        signals.append({
            "key": "pharmacy_freshness",
            "status": "ATTENTION" if refresh_rate is not None and refresh_rate >= 25 else "OK",
            "severity": "medium" if refresh_rate is not None and refresh_rate >= 25 else "info",
            "message": (
                f"{inventory['needs_refresh']} of {inventory_total} pharmacy observations need refresh "
                f"({refresh_rate}% of observed inventory)."
            ),
        })

    diagnostics = data_freshness["diagnostic_offers"]
    diagnostic_total = int(diagnostics["total_offers"] or 0)
    if diagnostic_total == 0:
        signals.append({
            "key": "diagnostic_freshness",
            "status": "NO_DATA",
            "severity": "info",
            "message": "No diagnostic provider offers are available yet.",
        })
    else:
        refresh_rate = _percent(int(diagnostics["needs_refresh"] or 0), diagnostic_total)
        signals.append({
            "key": "diagnostic_freshness",
            "status": "ATTENTION" if refresh_rate is not None and refresh_rate >= 25 else "OK",
            "severity": "medium" if refresh_rate is not None and refresh_rate >= 25 else "info",
            "message": (
                f"{diagnostics['needs_refresh']} of {diagnostic_total} diagnostic offers need refresh "
                f"({refresh_rate}% of observed offers)."
            ),
        })

    medicine = provider_responsiveness["medicine_orders"]
    order_count = int(medicine["submitted"] or 0)
    if order_count == 0:
        signals.append({
            "key": "pharmacy_response",
            "status": "NO_DATA",
            "severity": "info",
            "message": "No medicine orders are available for provider-response measurement.",
        })
    else:
        response_rate = medicine["response_rate_percent"]
        signals.append({
            "key": "pharmacy_response",
            "status": "ATTENTION" if response_rate is not None and response_rate < 80 else "OK",
            "severity": "medium" if response_rate is not None and response_rate < 80 else "info",
            "message": (
                f"Pharmacy response rate is {response_rate}% across {order_count} submitted order(s)."
            ),
        })

    consultations = provider_responsiveness["consultations"]
    consultation_count = int(consultations["requested"] or 0)
    if consultation_count == 0:
        signals.append({
            "key": "consultation_response",
            "status": "NO_DATA",
            "severity": "info",
            "message": "No consultation requests are available for response measurement.",
        })
    else:
        response_rate = consultations["response_rate_percent"]
        signals.append({
            "key": "consultation_response",
            "status": "ATTENTION" if response_rate is not None and response_rate < 80 else "OK",
            "severity": "medium" if response_rate is not None and response_rate < 80 else "info",
            "message": (
                f"Consultation response rate is {response_rate}% across {consultation_count} request(s)."
            ),
        })

    active_30 = int(engagement["authenticated_active_users_30d"] or 0)
    if active_30 < 5:
        signals.append({
            "key": "repeat_activity",
            "status": "NO_DATA",
            "severity": "info",
            "message": "Too few authenticated active users are available for a meaningful repeat-activity signal.",
        })
    else:
        repeat_rate = engagement["repeat_activity_rate_percent"]
        signals.append({
            "key": "repeat_activity",
            "status": "ATTENTION" if repeat_rate is not None and repeat_rate < 30 else "OK",
            "severity": "low" if repeat_rate is not None and repeat_rate < 30 else "info",
            "message": f"Observed 30-day repeat-activity rate is {repeat_rate}%.",
        })

    return signals


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


def _duration_values(rows, start_key: str, end_key: str, *, unit: str = "minutes") -> list[float]:
    values = []
    divisor = 60.0 if unit == "minutes" else 3600.0
    for row in rows:
        start = _parse_time(row[start_key])
        end = _parse_time(row[end_key])
        if start and end and end >= start:
            values.append((end - start).total_seconds() / divisor)
    return values


def _rounded_mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return round(float(ordered[middle]), 1)
    return round((ordered[middle - 1] + ordered[middle]) / 2.0, 1)


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
