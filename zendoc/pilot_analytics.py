"""Pilot-readiness analytics computed from real ZENDOC operational data."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .db import get_db
from .demo_truth import synthetic_demo_provider_profile_ids, synthetic_demo_user_ids
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
    demo_user_ids = synthetic_demo_user_ids(db)
    demo_profile_ids = synthetic_demo_provider_profile_ids(db)

    providers = _provider_funnel(db, demo_profile_ids)
    journeys = _care_journey_metrics(db, demo_user_ids)
    carefin = _carefin_metrics(db, demo_user_ids)
    fulfilment = _fulfilment_metrics(db, demo_user_ids)
    diagnostics = _diagnostic_metrics(db, demo_user_ids)
    data_coverage = _data_coverage_metrics(db)
    operations = _operations_metrics(db, demo_user_ids)
    provider_responsiveness = _provider_response_metrics(db, demo_user_ids)
    data_freshness = _data_freshness_metrics(db, demo_user_ids)
    engagement = _engagement_metrics(db, demo_user_ids)
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
            "Metrics are computed from ZENDOC database events/records only and exclude synthetic competition fixture users/providers. "
            "They do not estimate offline outcomes, partner-side actions, clinical efficacy, or unreported savings. "
            "Repeat activity is an observed product-usage proxy, not a cohort-retention claim."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _provider_funnel(db, demo_profile_ids: set[int]) -> dict:
    rows = db.execute(
        "SELECT id,verification_status FROM provider_profiles"
    ).fetchall()
    profiles = [row for row in rows if int(row["id"]) not in demo_profile_ids]
    profile_ids = {int(row["id"]) for row in profiles}
    total = len(profiles)
    pending = sum(1 for row in profiles if row["verification_status"] == "pending")
    verified = sum(1 for row in profiles if row["verification_status"] == "verified")
    rejected = sum(1 for row in profiles if row["verification_status"] == "rejected")
    suspended = sum(1 for row in profiles if row["verification_status"] == "suspended")

    evidence_rows = db.execute(
        "SELECT provider_profile_id,status FROM provider_verification_evidence"
    ).fetchall()
    with_evidence_ids = {
        int(row["provider_profile_id"])
        for row in evidence_rows
        if int(row["provider_profile_id"]) in profile_ids
    }
    with_verified_evidence_ids = {
        int(row["provider_profile_id"])
        for row in evidence_rows
        if int(row["provider_profile_id"]) in profile_ids and row["status"] == "verified"
    }
    schedule_rows = db.execute(
        "SELECT DISTINCT provider_profile_id FROM provider_schedules WHERE active=1"
    ).fetchall()
    schedule_ids = {
        int(row["provider_profile_id"])
        for row in schedule_rows
        if int(row["provider_profile_id"]) in profile_ids
    }
    return {
        "profiles_total": total,
        "pending": pending,
        "verified": verified,
        "rejected": rejected,
        "suspended": suspended,
        "with_submitted_evidence": len(with_evidence_ids),
        "with_verified_evidence": len(with_verified_evidence_ids),
        "with_active_schedule": len(schedule_ids),
        "verified_rate_percent": _percent(verified, total),
        "evidence_submission_rate_percent": _percent(len(with_evidence_ids), total),
    }


def _care_journey_metrics(db, demo_user_ids: set[int]) -> dict:
    rows = db.execute(
        "SELECT id,patient_id,state,status FROM care_journeys"
    ).fetchall()
    journeys = [row for row in rows if int(row["patient_id"]) not in demo_user_ids]
    journey_ids = {int(row["id"]) for row in journeys}
    total = len(journeys)
    active = sum(1 for row in journeys if row["status"] == "active")
    completed = sum(1 for row in journeys if row["status"] == "completed")
    blocked = sum(1 for row in journeys if row["status"] == "blocked")
    event_rows = db.execute(
        "SELECT journey_id,state FROM care_journey_events"
    ).fetchall()
    filtered_events = [row for row in event_rows if int(row["journey_id"]) in journey_ids]
    states: dict[str, int] = {}
    for row in journeys:
        state = str(row["state"])
        states[state] = states.get(state, 0) + 1
    return {
        "total": total,
        "active": active,
        "completed": completed,
        "blocked": blocked,
        "transition_events": len(filtered_events),
        "completion_rate_percent": _percent(completed, total),
        "states": dict(sorted(states.items(), key=lambda item: (-item[1], item[0]))),
    }


def _carefin_metrics(db, demo_user_ids: set[int]) -> dict:
    rows = db.execute(
        "SELECT actor_id FROM audit_logs WHERE action='carefin.discovery'"
    ).fetchall()
    real_rows = [
        row for row in rows
        if row["actor_id"] is None or int(row["actor_id"]) not in demo_user_ids
    ]
    unique_users = {
        int(row["actor_id"])
        for row in real_rows
        if row["actor_id"] is not None
    }
    return {
        "discovery_runs": len(real_rows),
        "unique_users_with_discovery": len(unique_users),
        "authoritative_confirmations": 0,
        "confirmed_savings_inr": None,
        "truth_notice": (
            "CareFin v1 records public discovery activity. Personal authoritative coverage/approval/payment "
            "is not persisted as a claimed metric until a partner-authoritative workflow exists."
        ),
    }


def _fulfilment_metrics(db, demo_user_ids: set[int]) -> dict:
    plan_rows = db.execute(
        "SELECT id,patient_id,confirmed_by_user FROM fulfilment_plans"
    ).fetchall()
    real_plans = [row for row in plan_rows if int(row["patient_id"]) not in demo_user_ids]
    staged = len(real_plans)
    confirmed_plans = sum(1 for row in real_plans if int(row["confirmed_by_user"] or 0) == 1)

    order_rows = db.execute(
        """
        SELECT id,patient_id,pharmacy_id,created_at,acknowledgement_status,
               acknowledged_at,tracking_status
        FROM medicine_orders
        """
    ).fetchall()
    real_orders = [
        row for row in order_rows
        if int(row["patient_id"]) not in demo_user_ids
        and (row["pharmacy_id"] is None or int(row["pharmacy_id"]) not in demo_user_ids)
    ]
    orders = len(real_orders)
    acknowledged_rows = [
        row for row in real_orders
        if str(row["acknowledgement_status"] or "").strip().lower() in {"accepted", "acknowledged"}
    ]
    delivered = sum(
        1 for row in real_orders
        if str(row["tracking_status"] or "").strip().upper() == "DELIVERED"
    )
    return {
        "fulfilment_plans": staged,
        "user_confirmed_plans": confirmed_plans,
        "orders_submitted": orders,
        "provider_acknowledged": len(acknowledged_rows),
        "delivered": delivered,
        "plan_to_order_conversion_percent": _percent(orders, staged),
        "order_acknowledgement_rate_percent": _percent(len(acknowledged_rows), orders),
        "delivery_completion_rate_percent": _percent(delivered, orders),
        "average_acknowledgement_minutes": _average_duration_minutes(
            [row for row in real_orders if row["acknowledged_at"] is not None],
            "created_at",
            "acknowledged_at",
        ),
    }


def _diagnostic_metrics(db, demo_user_ids: set[int]) -> dict:
    offer_rows = db.execute(
        "SELECT id,lab_id FROM diagnostic_offers"
    ).fetchall()
    offers = sum(1 for row in offer_rows if int(row["lab_id"]) not in demo_user_ids)
    booking_rows = db.execute(
        "SELECT patient_id,status,report_record_id FROM diagnostic_bookings"
    ).fetchall()
    real_bookings = [
        row for row in booking_rows
        if int(row["patient_id"]) not in demo_user_ids
    ]
    bookings = len(real_bookings)
    completed = sum(
        1 for row in real_bookings
        if str(row["status"] or "").strip().lower() == "completed"
    )
    report_linked = sum(1 for row in real_bookings if row["report_record_id"] is not None)
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


def _provider_response_metrics(db, demo_user_ids: set[int]) -> dict:
    order_rows = db.execute(
        """
        SELECT patient_id,pharmacy_id,created_at,acknowledged_at
        FROM medicine_orders
        """
    ).fetchall()
    order_rows = [
        row for row in order_rows
        if int(row["patient_id"]) not in demo_user_ids
        and (row["pharmacy_id"] is None or int(row["pharmacy_id"]) not in demo_user_ids)
    ]
    responded_order_rows = [row for row in order_rows if row["acknowledged_at"] is not None]
    order_minutes = _duration_values(responded_order_rows, "created_at", "acknowledged_at", unit="minutes")
    order_total = len(order_rows)
    order_responded = len(order_minutes)

    consultation_rows = db.execute(
        """
        SELECT cr.patient_id,cr.doctor_id,cr.created_at,cr.updated_at,cr.status,
               room.created_at room_created_at
        FROM consultation_requests cr
        LEFT JOIN consultation_rooms room ON room.consultation_id=cr.id
        """
    ).fetchall()
    consultation_rows = [
        row for row in consultation_rows
        if int(row["patient_id"]) not in demo_user_ids
        and int(row["doctor_id"]) not in demo_user_ids
    ]
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
            "Synthetic competition fixture users/providers are excluded. Medicine response uses acknowledged_at. "
            "Consultation response uses the first room-creation timestamp for accepted/scheduled requests and the "
            "terminal update timestamp for rejected requests."
        ),
    }


def _data_freshness_metrics(db, demo_user_ids: set[int]) -> dict:
    inventory_counts = {"CONFIRMED": 0, "STALE": 0, "UNKNOWN": 0, "UNAVAILABLE": 0}
    stale_pharmacies = set()
    inventory_rows = db.execute(
        "SELECT pharmacy_id, observed_at, stock_status, quantity_available FROM inventory_observations"
    ).fetchall()
    inventory_rows = [
        row for row in inventory_rows
        if int(row["pharmacy_id"]) not in demo_user_ids
    ]
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
    diagnostic_rows = [
        row for row in diagnostic_rows
        if int(row["lab_id"]) not in demo_user_ids
    ]
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


def _engagement_metrics(db, demo_user_ids: set[int]) -> dict:
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
        if actor_id in demo_user_ids:
            continue
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
            "Synthetic competition fixture actors are excluded. Repeat activity means an authenticated actor generated requests on at least two distinct UTC dates "
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


def _operations_metrics(db, demo_user_ids: set[int]) -> dict:
    task_rows = db.execute(
        "SELECT requested_by,status FROM agent_tasks"
    ).fetchall()
    task_rows = [
        row for row in task_rows
        if row["requested_by"] is None or int(row["requested_by"]) not in demo_user_ids
    ]
    agent_tasks = len(task_rows)
    failed = sum(1 for row in task_rows if row["status"] == "failed")
    waiting = sum(
        1 for row in task_rows
        if row["status"] in {"waiting_human", "waiting_approval"}
    )
    active_alerts = _count(db, "SELECT COUNT(*) c FROM agent_alerts WHERE status='active'")

    consultation_rows = db.execute(
        "SELECT patient_id,doctor_id,status FROM consultation_requests"
    ).fetchall()
    consultation_rows = [
        row for row in consultation_rows
        if int(row["patient_id"]) not in demo_user_ids
        and int(row["doctor_id"]) not in demo_user_ids
    ]
    consultations = len(consultation_rows)
    consultation_accepted = sum(
        1 for row in consultation_rows
        if row["status"] in {"accepted", "confirmed", "active", "completed"}
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
