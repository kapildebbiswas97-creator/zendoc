"""Canonical evidence-backed continuity view for one ZENDOC Care Journey.

This module does not execute care. It assembles already-authorized, already-
persisted workflow state so the UI/Agent OS can see exactly what is true, what
human/provider gate is next, and what evidence supports the next safe action.
"""
from __future__ import annotations

from typing import Any

from .care_action_ledger import ensure_care_action_ledger_schema
from .care_journey_store import get_persisted_journey
from .db import get_db
from .health_memory_continuity import determine_next_safe_actions


CANONICAL_CHAIN = [
    "AGENT_REQUEST",
    "SPECIALIST_ORCHESTRATION",
    "VERIFIED_PROVIDER_DISCOVERY",
    "REAL_PUBLISHED_SLOT",
    "PATIENT_SELECTION",
    "EXPLICIT_PATIENT_CONFIRMATION",
    "REQUESTED_APPOINTMENT",
    "CARELOOP_STAGED",
    "WAITING_PROVIDER",
    "WAITING_VISIT",
    "REAL_VISIT",
    "PROVIDER_COMPLETION",
    "VERIFIED_OUTCOME_EVIDENCE",
    "PROVIDER_RECORDED_HEALTH_MEMORY",
    "NEXT_SAFE_ACTION",
    "FOLLOW_UP",
    "LONGITUDINAL_COMPLETION",
]


def _decode_bool(value: Any) -> bool:
    return bool(value)


def get_care_continuity_snapshot(actor: Any, journey_id: int) -> dict:
    """Return one truthful continuity snapshot for an authorized journey.

    Authorization is delegated to ``get_persisted_journey`` before any linked
    action/outcome/memory rows are read. Missing evidence stays missing; this
    function never upgrades inferred/model state into provider truth.
    """
    journey = get_persisted_journey(int(journey_id), actor)
    patient_id = int(journey["patient_id"])
    ensure_care_action_ledger_schema()
    db = get_db()

    actions = db.execute(
        "SELECT * FROM care_actions WHERE journey_id=? ORDER BY id ASC",
        (int(journey_id),),
    ).fetchall()
    action_rows = [dict(row) for row in actions]
    linked_appointment_action = next(
        (
            row for row in reversed(action_rows)
            if str(row.get("service_ref") or "").startswith("zendoc_appointment:")
        ),
        None,
    )

    appointment = None
    if linked_appointment_action:
        try:
            appointment_id = int(str(linked_appointment_action["service_ref"]).split(":", 1)[1])
        except (TypeError, ValueError, IndexError):
            appointment_id = 0
        if appointment_id:
            row = db.execute(
                """
                SELECT id,patient_id,provider_id,provider_profile_id,provider_name,
                       scheduled_for,status,updated_at
                FROM appointments
                WHERE id=? AND patient_id=?
                """,
                (appointment_id, patient_id),
            ).fetchone()
            appointment = dict(row) if row else None

    outcome = db.execute(
        """
        SELECT * FROM care_outcomes
        WHERE journey_id=? AND patient_id=? AND status='VERIFIED'
        ORDER BY id DESC LIMIT 1
        """,
        (int(journey_id), patient_id),
    ).fetchone()
    outcome = dict(outcome) if outcome else None

    memory_event = None
    if outcome:
        row = db.execute(
            """
            SELECT id,event_type,event_at,title,summary,provider_name,source,source_ref,created_by
            FROM health_timeline_events
            WHERE patient_id=? AND event_type='provider_outcome'
              AND source_ref=? AND source IN ('PROVIDER_RECORDED','OWNER_RECORDED')
            ORDER BY id DESC LIMIT 1
            """,
            (patient_id, f"care_outcome:{int(outcome['id'])}"),
        ).fetchone()
        memory_event = dict(row) if row else None

    safe_actions = determine_next_safe_actions(patient_id, actor=actor)
    journey_safe_actions = [
        item for item in safe_actions
        if int(item.get("journey_id") or 0) == int(journey_id)
    ]

    appointment_status = str((appointment or {}).get("status") or "") or None
    action_status = str((linked_appointment_action or {}).get("status") or "") or None
    state = str(journey["state"])
    provider_confirmed = appointment_status in {"confirmed", "completed"}
    provider_completed = appointment_status == "completed"
    outcome_verified = bool(outcome and str(outcome.get("status")) == "VERIFIED")
    memory_recorded = bool(memory_event)

    return {
        "journey_id": int(journey["id"]),
        "journey_uid": journey["journey_uid"],
        "patient_id": patient_id,
        "state": state,
        "status": journey["status"],
        "terminal": _decode_bool(journey.get("terminal")),
        "required_actor": journey.get("required_actor"),
        "required_consent": journey.get("required_consent"),
        "next_safe_action": journey.get("next_safe_action"),
        "canonical_chain": CANONICAL_CHAIN,
        "appointment": {
            "id": int(appointment["id"]) if appointment else None,
            "provider_id": int(appointment["provider_id"]) if appointment and appointment.get("provider_id") else None,
            "provider_profile_id": int(appointment["provider_profile_id"]) if appointment and appointment.get("provider_profile_id") else None,
            "provider_name": appointment.get("provider_name") if appointment else None,
            "scheduled_for": appointment.get("scheduled_for") if appointment else None,
            "status": appointment_status,
        },
        "careloop": {
            "action_id": int(linked_appointment_action["id"]) if linked_appointment_action else None,
            "status": action_status,
            "linked": bool(linked_appointment_action),
        },
        "evidence": {
            "provider_confirmed": provider_confirmed,
            "visit_completed_by_provider_state": provider_completed,
            "verified_outcome_id": int(outcome["id"]) if outcome else None,
            "verified_outcome_present": outcome_verified,
            "health_memory_event_id": int(memory_event["id"]) if memory_event else None,
            "health_memory_provenance": memory_event.get("source") if memory_event else None,
            "provider_recorded_health_memory": bool(memory_event and memory_event.get("source") == "PROVIDER_RECORDED"),
        },
        "available_next_safe_actions": journey_safe_actions,
        "truth": {
            "model_claim_is_provider_confirmation": False,
            "patient_report_is_provider_recorded": False,
            "missing_evidence_becomes_verified": False,
            "payment_executed_by_agent": False,
            "clinical_findings_inferred_from_completion": False,
        },
    }
