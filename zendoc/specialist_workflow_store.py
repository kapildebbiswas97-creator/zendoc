"""Persistent bounded workflow state for the ZENDOC specialist Agent OS.

General specialist workflows reuse the existing agent_tasks/event infrastructure.
Clinical appointment progression additionally uses the existing Care Journey state
machine. This module stores operational metadata only; it intentionally does not
persist raw prompts, health payloads, payment secrets, or third-party credentials.
"""
from __future__ import annotations

from typing import Any

from .agent_handoffs import handoff_for_intent
from .agent_task_engine import (
    create_agent_task,
    execute_safe_task,
    get_agent_task,
    set_task_waiting,
)
from .audit_privacy import redact_operational_text
from .care_journey_store import (
    advance_persisted_journey,
    create_persisted_journey,
    get_persisted_journey,
)
from .db import get_db, now_iso


def _value(actor: Any, key: str, default=None):
    if actor is None:
        return default
    if hasattr(actor, "keys") and key in actor.keys():
        return actor[key]
    return actor.get(key, default) if isinstance(actor, dict) else default


def _actor_id(actor: Any) -> int:
    return int(_value(actor, "id", 0) or 0)


def _actor_role(actor: Any) -> str:
    return str(_value(actor, "role", "") or "").strip().lower()


def _positive_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Workflow identifiers must be positive integers.") from exc
    if parsed <= 0:
        raise ValueError("Workflow identifiers must be positive integers.")
    return parsed


def _task_view(task: dict | None) -> dict | None:
    if not task:
        return None
    return {
        "id": int(task["id"]),
        "task_type": task["task_type"],
        "assigned_agent": task["assigned_agent"],
        "status": task["status"],
        "attempt_count": int(task.get("attempt_count") or 0),
        "risk_level": task["risk_level"],
    }


def _journey_view(journey: dict | None) -> dict | None:
    if not journey:
        return None
    return {
        "id": int(journey["id"]),
        "journey_uid": journey["journey_uid"],
        "state": journey["state"],
        "status": journey["status"],
        "next_safe_action": journey["next_safe_action"],
        "required_actor": journey.get("required_actor"),
        "required_consent": journey.get("required_consent"),
        "terminal": bool(journey.get("terminal")),
    }


def _task_metadata(result: dict, context: dict) -> dict:
    plan = result.get("plan") if isinstance(result.get("plan"), dict) else {}
    care_chain = result.get("care_chain") if isinstance(result.get("care_chain"), dict) else {}
    chain = result.get("handoff_chain")
    if not isinstance(chain, list):
        chain = handoff_for_intent(result.get("intent"))
    return {
        "plan_id": str(plan.get("plan_id") or "")[:80],
        "intent": str(result.get("intent") or "")[:80],
        "privacy_class": str(result.get("privacy_class") or "INTERNAL")[:40],
        "execution_status": str(result.get("execution_status") or "")[:40],
        "requires_confirmation": bool(result.get("requires_confirmation")),
        "human_gate": str(result.get("human_gate") or "")[:120] or None,
        "context_keys": sorted(str(key)[:80] for key in context.keys()),
        "handoff_chain": [
            {
                "agent": str(stage.get("agent") or "")[:80],
                "stage": str(stage.get("stage") or "")[:100],
                "mode": str(stage.get("mode") or "")[:80],
                "gate": str(stage.get("gate") or "")[:120] or None,
            }
            for stage in chain
            if isinstance(stage, dict)
        ],
        "care_chain": {
            "version": str(care_chain.get("version") or "")[:40] or None,
            "input_channel": str((care_chain.get("input") or {}).get("channel") or "typed")[:40],
            "asr_audit_log_id": (care_chain.get("input") or {}).get("asr_audit_log_id"),
            "health_memory_total_events": int((care_chain.get("health_memory") or {}).get("total_events") or 0),
            "health_memory_status": str((care_chain.get("health_memory") or {}).get("status") or "")[:80],
            "rag_status": str((care_chain.get("rag") or {}).get("status") or "")[:80],
            "rag_evidence_ids": [
                str(item.get("evidence_id") or "")[:120]
                for item in (care_chain.get("rag") or {}).get("evidence", [])
                if isinstance(item, dict) and item.get("evidence_id")
            ][:8],
            "local_advisory_status": str((care_chain.get("local_advisory") or {}).get("status") or "")[:80],
            "local_model_used": bool((care_chain.get("local_advisory") or {}).get("local_model_used")),
            "model_execution_log_id": (care_chain.get("local_advisory") or {}).get("model_execution_log_id"),
            "raw_prompt_stored": False,
            "raw_transcript_stored": False,
            "raw_health_memory_stored": False,
        },
        "raw_prompt_stored": False,
        "tool_payload_stored": False,
    }


def complete_waiting_specialist_task(
    actor: Any,
    task_id: int,
    *,
    expected_intent: str | None = None,
    summary: str = "Authenticated human action advanced the specialist workflow.",
) -> dict:
    """Close one waiting specialist task after a real human continuation."""
    task = get_agent_task(int(task_id), actor=actor)
    if not str(task["task_type"]).startswith("specialist_workflow:"):
        raise ValueError("Task is not a specialist Agent OS workflow.")
    if expected_intent:
        expected_type = f"specialist_workflow:{expected_intent}"
        if task["task_type"] != expected_type:
            raise ValueError("Workflow task intent does not match this continuation.")
    if task["status"] != "waiting_human":
        raise ValueError("Specialist workflow task is not waiting for human action.")

    now = now_iso()
    safe_summary = redact_operational_text(summary, 300)
    db = get_db()
    db.execute(
        """
        UPDATE agent_tasks
        SET status='completed', result_summary=?, completed_at=?, updated_at=?
        WHERE id=? AND status='waiting_human'
        """,
        (safe_summary, now, now, int(task_id)),
    )
    db.commit()
    completed = get_agent_task(int(task_id), actor=actor)
    try:
        from .event_bus import publish_event

        publish_event(
            "agent.task.completed_after_human",
            actor=actor,
            entity_type="agent_task",
            entity_id=str(task_id),
            status="completed",
            agent_name=completed["assigned_agent"],
            payload={"task_type": completed["task_type"], "attempt_count": completed["attempt_count"]},
        )
    except Exception:
        pass
    return completed


def _advance(journey: dict, actor: Any, target_state: str, **kwargs) -> dict:
    return advance_persisted_journey(
        actor,
        int(journey["id"]),
        target_state=target_state,
        **kwargs,
    )


def _appointment_result_has_options(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if "available_slots" in payload:
        return bool(payload.get("available_slots"))
    registered = payload.get("registered_providers") or []
    external = (payload.get("external_places") or {}).get("results", [])
    return bool(registered or external)


def _sync_appointment_journey(actor: Any, result: dict, context: dict) -> dict | None:
    if _actor_role(actor) != "patient":
        return None

    requested_id = _positive_int(context.get("journey_id"))
    if requested_id:
        journey = get_persisted_journey(requested_id, actor)
    else:
        plan = result.get("plan") if isinstance(result.get("plan"), dict) else {}
        journey = create_persisted_journey(
            actor,
            provenance={
                "source": "agent_os",
                "intent": "appointment_booking",
                "plan_id": str(plan.get("plan_id") or "")[:80],
            },
        )

    if journey["state"] in {
        "APPOINTMENT_STAGED",
        "WAITING_PROVIDER",
        "CONSULTATION",
        "PRESCRIPTION_RECEIVED",
        "DIAGNOSTICS_REQUIRED",
        "CAREFIN_CHECK",
        "FULFILMENT",
        "FOLLOW_UP",
        "COMPLETED",
        "BLOCKED",
        "WAITING_HUMAN",
    }:
        return journey

    if journey["state"] == "NEW":
        journey = _advance(
            journey,
            actor,
            "CONTEXT_READY",
            reason="Authenticated patient context authorized for appointment coordination.",
            actor_type="system",
            provenance={"source": "agent_os", "context_authorized": True},
        )

    if journey["state"] in {"CONTEXT_READY", "WAITING_INFORMATION"}:
        journey = _advance(
            journey,
            actor,
            "PROVIDER_SEARCH",
            reason="Specialist Agent OS started truthful provider discovery.",
            actor_type="ai",
            next_safe_action="search_verified_and_external_providers",
            provenance={"source": "agent_os", "discovery_started": True},
        )

    payload = result.get("payload")
    has_slots_payload = isinstance(payload, dict) and "available_slots" in payload
    has_slots = bool(payload.get("available_slots")) if has_slots_payload else False
    has_options = _appointment_result_has_options(payload)

    if journey["state"] == "PROVIDER_SEARCH":
        if has_slots or (not has_slots_payload and has_options):
            journey = _advance(
                journey,
                actor,
                "WAITING_USER_SELECTION",
                reason="Provider or slot options were prepared without creating an appointment.",
                actor_type="ai",
                next_safe_action="select_connected_provider_or_refine_search",
                required_actor="patient",
                provenance={
                    "source": "agent_os",
                    "evidence_state": "verified_slot_read" if has_slots_payload else "provider_discovery",
                },
            )
        else:
            return _advance(
                journey,
                actor,
                "WAITING_INFORMATION",
                reason="No usable provider option was available from the current search.",
                actor_type="ai",
                next_safe_action="refine_provider_search",
                required_actor="patient",
                provenance={"source": "agent_os", "evidence_state": "no_usable_provider_option"},
            )

    if has_slots and journey["state"] == "WAITING_USER_SELECTION":
        provider_profile_id = payload.get("provider_profile_id") if isinstance(payload, dict) else None
        journey = _advance(
            journey,
            actor,
            "APPOINTMENT_STAGED",
            reason="Verified connected provider availability was inspected; no appointment has been created yet.",
            actor_type="ai",
            next_safe_action="ask_user_to_confirm_appointment",
            required_actor="patient",
            required_consent="explicit_booking_confirmation",
            provenance={
                "source": "agent_os",
                "provider_profile_id": int(provider_profile_id) if provider_profile_id else None,
                "provider_confirmation_state": "not_requested",
            },
        )
    return journey


def persist_specialist_result(actor: Any, result: dict, context: dict | None = None) -> dict:
    """Persist a bounded specialist result without storing raw sensitive content."""
    actor_id = _actor_id(actor)
    if not actor_id:
        raise PermissionError("Authentication required.")
    context = context if isinstance(context, dict) else {}

    intent = str(result.get("intent") or "").strip()
    assigned_agent = str(result.get("assigned_agent") or "").strip()
    plan = result.get("plan") if isinstance(result.get("plan"), dict) else {}
    plan_id = str(plan.get("plan_id") or "").strip()
    if not intent or not assigned_agent or not plan_id:
        raise ValueError("Specialist result is missing workflow identity.")

    previous_task_id = _positive_int(context.get("workflow_task_id"))
    if previous_task_id:
        complete_waiting_specialist_task(
            actor,
            previous_task_id,
            expected_intent=intent,
            summary="Authenticated user supplied continuation context and advanced the specialist workflow.",
        )

    task = create_agent_task(
        task_type=f"specialist_workflow:{intent}",
        requested_by=actor_id,
        assigned_agent=assigned_agent,
        priority="normal",
        risk_level=str(result.get("risk_level") or "read_only"),
        max_attempts=1,
        idempotency_key=f"specialist:{actor_id}:{plan_id}"[:160],
        metadata=_task_metadata(result, context),
        actor=actor,
    )

    if task["status"] == "queued":
        if bool(result.get("requires_confirmation")) or result.get("execution_status") == "waiting_human":
            task = set_task_waiting(
                int(task["id"]),
                "waiting_human",
                "The bounded specialist step completed; authenticated human continuation is required.",
            )
        else:
            task = execute_safe_task(
                int(task["id"]),
                actor,
                handler_fn=lambda _task: (
                    f"{assigned_agent} specialist workflow record completed after bounded read-only execution."
                ),
            )
    else:
        task = get_agent_task(int(task["id"]), actor=actor)

    result["workflow_task"] = _task_view(task)

    if intent == "appointment_booking":
        journey = _sync_appointment_journey(actor, result, context)
        result["care_journey"] = _journey_view(journey)

    return result


def validate_booking_confirmation(
    actor: Any,
    *,
    journey_id: Any = None,
    workflow_task_id: Any = None,
) -> dict:
    """Validate optional persisted workflow references before creating a booking."""
    journey = None
    task = None

    parsed_journey_id = _positive_int(journey_id)
    if parsed_journey_id:
        journey = get_persisted_journey(parsed_journey_id, actor)
        if journey["state"] != "APPOINTMENT_STAGED":
            raise ValueError("Care journey is not staged for appointment confirmation.")

    parsed_task_id = _positive_int(workflow_task_id)
    if parsed_task_id:
        task = get_agent_task(parsed_task_id, actor=actor)
        if task["task_type"] != "specialist_workflow:appointment_booking":
            raise ValueError("Workflow task is not an appointment-booking workflow.")
        if task["assigned_agent"] != "BookingAgent":
            raise ValueError("Workflow task is not owned by the Booking Agent.")
        if task["status"] != "waiting_human":
            raise ValueError("Booking workflow task is not waiting for user confirmation.")

    return {"journey": journey, "task": task}


def mark_booking_requested(
    actor: Any,
    *,
    appointment_id: int,
    provider_profile_id: int,
    journey_id: Any = None,
    workflow_task_id: Any = None,
) -> dict:
    """Advance persisted state only after a real REQUESTED appointment exists."""
    actor_id = _actor_id(actor)
    appointment = get_db().execute(
        """
        SELECT id,patient_id,provider_profile_id,status
        FROM appointments
        WHERE id=? AND patient_id=? AND provider_profile_id=?
        """,
        (int(appointment_id), actor_id, int(provider_profile_id)),
    ).fetchone()
    if not appointment or appointment["status"] != "requested":
        raise ValueError("A persisted REQUESTED appointment is required before workflow completion.")

    refs = validate_booking_confirmation(
        actor,
        journey_id=journey_id,
        workflow_task_id=workflow_task_id,
    )
    journey = refs["journey"]
    task = refs["task"]

    if journey:
        journey = advance_persisted_journey(
            actor,
            int(journey["id"]),
            target_state="WAITING_PROVIDER",
            reason="Authenticated patient confirmed a connected appointment request.",
            actor_type="user",
            next_safe_action="wait_for_provider_response",
            required_actor="provider",
            provenance={
                "source": "agent_os",
                "appointment_id": int(appointment_id),
                "provider_profile_id": int(provider_profile_id),
                "provider_confirmation_state": "requested",
                "workflow_task_id": int(task["id"]) if task else None,
            },
        )

    if task:
        task = set_task_waiting(
            int(task["id"]),
            "waiting_provider",
            "Authenticated patient created the connected appointment request; provider confirmation is still pending.",
        )

    return {
        "workflow_task": _task_view(task),
        "care_journey": _journey_view(journey),
    }
