"""Canonical, safety-bounded ZENDOC care-chain integration.

This module connects the competition runtime pieces without allowing model output
to become clinical authority or executable tool instructions.

The chain is intentionally split into:
- verified input/runtime evidence,
- minimum-necessary Health Memory + approved medical RAG metadata,
- local-only model advisory (never executable),
- deterministic Agent OS execution,
- persisted human/provider gates,
- authoritative outcomes, longitudinal memory and audit evidence.

Raw prompts, transcripts, clinical records and hidden reasoning are never copied
into operational/audit metadata by this module.
"""
from __future__ import annotations

from typing import Any

from .care_continuity import get_care_continuity_snapshot
from .db import get_db, now_iso
from .health_memory_continuity import get_health_memory_provenance_summary
from .knowledge_agent import run_knowledge_agent
from .model_router import (
    PrivacyClass,
    RiskClass,
    RoutingReason,
    get_model_router,
    normalize_privacy_class,
)
from .safety import SafetyEngine


CARE_CHAIN_VERSION = "2026.1"

# RAG is used only where educational/clinical knowledge grounding can actually
# improve a read-only explanation. Pure booking/search/payment-like logistics do
# not pretend a medical-knowledge retrieval step was required.
RAG_INTENTS = {
    "general_agent",
    "health_learning",
    "health_records",
    "lifecycle",
    "nutrition",
    "fitness",
    "preventive_care",
}

_HEALTH_SENSITIVE_INTENTS = {
    "diagnostics",
    "health_records",
    "lifecycle",
    "pharmacy",
    "prescription",
    "preventive_care",
    "telehealth_request",
}


def _value(actor: Any, key: str, default=None):
    if actor is None:
        return default
    if hasattr(actor, "keys") and key in actor.keys():
        return actor[key]
    if isinstance(actor, dict):
        return actor.get(key, default)
    return getattr(actor, key, default)


def _actor_id(actor: Any) -> int:
    return int(_value(actor, "id", 0) or 0)


def _actor_role(actor: Any) -> str:
    return str(_value(actor, "role", "") or "").strip().lower()


def _positive_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _validated_asr_audit(actor_id: int, audit_id: Any) -> dict | None:
    parsed = _positive_int(audit_id)
    if not parsed:
        return None
    row = get_db().execute(
        """
        SELECT id,entity_id,created_at
        FROM audit_logs
        WHERE id=? AND actor_id=? AND action='edgecare_asr_transcribe'
        LIMIT 1
        """,
        (parsed, int(actor_id)),
    ).fetchone()
    return dict(row) if row else None


def _input_evidence(actor: Any, input_channel: str, asr_audit_log_id: Any) -> dict:
    actor_id = _actor_id(actor)
    requested = str(input_channel or "typed").strip().lower()
    asr_audit = _validated_asr_audit(actor_id, asr_audit_log_id)

    provider = None
    model = None
    runtime_status = "not_evidenced"
    if asr_audit:
        parts = str(asr_audit.get("entity_id") or "").split(":", 2)
        provider = parts[0] or None if parts else None
        model = parts[1] or None if len(parts) > 1 else None
        runtime_status = "success" if len(parts) > 2 and parts[2] == "success" else "recorded"

    if requested == "local_asr_transcript" and asr_audit:
        status = "VERIFIED_LOCAL_ASR_TRANSCRIPT"
        channel = "local_asr_transcript"
    elif requested == "local_asr_transcript":
        # Never accept a caller-provided label as proof that ASR actually ran.
        status = "UNVERIFIED_INPUT_CHANNEL"
        channel = "typed_or_unverified"
    else:
        status = "TYPED_INPUT"
        channel = "typed"

    return {
        "status": status,
        "channel": channel,
        "manual_submit_required": True,
        "asr_audit_log_id": int(asr_audit["id"]) if asr_audit else None,
        "asr_runtime_status": runtime_status,
        "asr_provider": provider,
        "asr_model": model,
        "transcript_persisted_by_chain": False,
        "audio_persisted_by_chain": False,
        "input_adapter": "audit_evidence_contract",
    }


def _health_memory_metadata(actor: Any) -> dict:
    if _actor_role(actor) != "patient":
        return {
            "status": "NOT_APPLICABLE",
            "total_events": 0,
            "provenance_counts": {},
            "raw_events_exposed_to_chain": False,
        }

    try:
        memory = get_health_memory_provenance_summary(_actor_id(actor), actor=actor)
    except (LookupError, PermissionError, ValueError):
        return {
            "status": "AUTHORIZATION_REQUIRED",
            "total_events": 0,
            "provenance_counts": {},
            "raw_events_exposed_to_chain": False,
        }

    by_provenance = memory.get("by_provenance") or {}
    counts = {
        str(name): len(items or [])
        for name, items in by_provenance.items()
        if isinstance(items, list)
    }
    return {
        "status": "AUTHORIZED_MINIMUM_METADATA",
        "total_events": int(memory.get("total_events") or 0),
        "provenance_counts": counts,
        "raw_events_exposed_to_chain": False,
    }



def _minimum_health_context_for_local_advisory(actor: Any, intent: str) -> dict:
    """Return only intent-required self-context for the local advisory model.

    The returned values are transient local-inference context and are never
    copied into care-chain audit/task metadata. A workflow receives no patient
    field merely because it exists in Health Memory.
    """
    if _actor_role(actor) != "patient":
        return {"status": "NOT_APPLICABLE", "data": {}, "included_fields": []}

    intent = str(intent or "").strip().lower()
    fields_by_intent = {
        "appointment_booking": ("city",),
        "provider_discovery": ("city",),
        "diagnostics": ("city",),
        "carefin": ("city",),
        "pharmacy": ("city", "allergies"),
        "prescription": ("allergies",),
        "nutrition": ("allergies",),
        "preventive_care": ("allergies",),
    }
    requested_fields = list(fields_by_intent.get(intent, ()))

    try:
        from .context_engine import build_minimum_context_bundle

        bundle = build_minimum_context_bundle(
            actor=actor,
            patient_id=_actor_id(actor),
            purpose="health_memory_view",
            action="care_chain_local_advisory",
            requested_fields=requested_fields,
        )
    except (LookupError, PermissionError, ValueError):
        return {"status": "AUTHORIZATION_REQUIRED", "data": {}, "included_fields": []}

    allowed = set(requested_fields)
    data = {
        key: value
        for key, value in (bundle.data or {}).items()
        if key in allowed
    }
    return {
        "status": "AUTHORIZED_MINIMUM_CONTEXT",
        "data": data,
        "included_fields": sorted(data.keys()),
        "consent_status": bundle.consent_status,
    }

def _rag_metadata(actor: Any, command: str, intent: str, emergency: bool) -> dict:
    if emergency:
        return {
            "status": "SKIPPED_EMERGENCY_SAFETY",
            "evidence": [],
            "retrieval_performed": False,
        }
    if intent not in RAG_INTENTS:
        return {
            "status": "NOT_REQUIRED_FOR_LOGISTICS",
            "evidence": [],
            "retrieval_performed": False,
        }

    try:
        knowledge = run_knowledge_agent(actor, command, limit=4)
    except (LookupError, PermissionError, ValueError):
        return {
            "status": "GROUNDING_UNAVAILABLE",
            "evidence": [],
            "retrieval_performed": False,
        }

    evidence = []
    for item in knowledge.get("evidence") or []:
        evidence.append({
            "evidence_id": item.get("evidence_id"),
            "source_id": item.get("source_id"),
            "document_title": item.get("document_title"),
            "document_url": item.get("document_url"),
            "publication_date": item.get("publication_date"),
            "retrieval_score": item.get("retrieval_score"),
        })

    return {
        "status": str(knowledge.get("status") or "UNKNOWN"),
        "retrieval_mode": knowledge.get("retrieval_mode"),
        "retrieval_performed": bool(knowledge.get("retrieval_performed")),
        "evidence_count": len(evidence),
        "evidence": evidence,
        "answer_generated_by_rag_layer": False,
        "healthcare_action_executed": False,
    }


def _advisory_prompt(
    command: str,
    intent: str,
    memory: dict,
    memory_context: dict,
    rag: dict,
) -> str:
    provenance = memory.get("provenance_counts") or {}
    evidence_labels = [
        str(item.get("document_title") or item.get("source_id") or item.get("evidence_id") or "")[:120]
        for item in rag.get("evidence") or []
    ]
    minimum_context = memory_context.get("data") or {}
    return (
        "Interpret this care goal only as a bounded workflow-planning assistant. "
        "Do not diagnose, prescribe, change medication, claim provider acceptance, "
        "or propose executable tool calls.\n"
        f"Intent: {intent[:80]}\n"
        f"Care goal: {str(command or '').strip()[:1200]}\n"
        f"Minimum-necessary local patient context: {minimum_context}\n"
        f"Authorized Health Memory event counts by provenance: {provenance}\n"
        f"Approved medical-evidence labels: {evidence_labels[:4]}\n"
        "Return a short user-facing workflow interpretation and mention any human/provider gate."
    )


def _local_advisory(
    actor: Any,
    command: str,
    *,
    intent: str,
    privacy_class: str,
    emergency: bool,
    memory: dict,
    memory_context: dict,
    rag: dict,
) -> dict:
    if emergency:
        return {
            "status": "SKIPPED_EMERGENCY_SAFETY",
            "local_model_used": False,
            "tool_execution_authority": False,
            "text": None,
        }

    normalized_privacy = normalize_privacy_class(privacy_class)
    if intent in _HEALTH_SENSITIVE_INTENTS or _actor_role(actor) == "patient":
        normalized_privacy = PrivacyClass.HEALTH_SENSITIVE

    response = get_model_router().route(
        _advisory_prompt(command, intent, memory, memory_context, rag),
        intent=intent,
        task_type="planning_assistance",
        privacy_sensitive=normalized_privacy in {
            PrivacyClass.HEALTH_SENSITIVE,
            PrivacyClass.HIGH_RISK,
        },
        allow_cloud=False,
        actor_id=_actor_id(actor),
        privacy_class=normalized_privacy,
        complexity="medium",
        latency_preference="normal",
        risk_class=RiskClass.READ_ONLY,
        structured_output_required=True,
        system_prompt=(
            "You are the non-executable planning advisory layer for ZENDOC Agent OS. "
            "Never output a diagnosis, prescription, medication change, emergency-dispatch instruction, "
            "payment instruction, permission change, shell/SQL/filesystem action or tool call. "
            "The deterministic server planner owns all executable decisions."
        ),
    )

    model_log = get_db().execute(
        """
        SELECT id,provider,model,routing_reason,success,created_at
        FROM model_execution_logs
        WHERE actor_id=? AND task_type='planning_assistance'
        ORDER BY id DESC LIMIT 1
        """,
        (_actor_id(actor),),
    ).fetchone()

    local_used = response.routing_reason == RoutingReason.LOCAL_SLM and bool(response.success)
    if local_used:
        status = "LOCAL_MODEL_ADVISORY_USED"
    elif response.success:
        status = "DETERMINISTIC_FALLBACK_USED"
    else:
        status = "ADVISORY_UNAVAILABLE"

    return {
        "status": status,
        "local_model_used": local_used,
        "provider": response.provider,
        "model": response.model,
        "routing_reason": response.routing_reason,
        "latency_ms": max(0, int(response.latency_ms or 0)),
        "text": response.text,
        "tool_execution_authority": False,
        "cloud_allowed": False,
        "model_execution_log_id": int(model_log["id"]) if model_log else None,
    }


def prepare_care_chain(
    actor: Any,
    command: str,
    *,
    intent: str,
    privacy_class: str = PrivacyClass.INTERNAL,
    input_channel: str = "typed",
    asr_audit_log_id: Any = None,
) -> dict:
    """Prepare runtime/context/model evidence before deterministic Agent OS work.

    This function may run local advisory inference and approved read-only RAG, but
    it never executes a healthcare action.
    """
    actor_id = _actor_id(actor)
    if not actor_id:
        raise PermissionError("Authentication required.")

    clean_command = str(command or "").strip()
    if not clean_command:
        raise ValueError("Agent command is required.")

    safety = SafetyEngine().assess(clean_command)
    emergency = bool(safety.get("emergency"))
    input_evidence = _input_evidence(actor, input_channel, asr_audit_log_id)
    memory = _health_memory_metadata(actor)
    memory_context = _minimum_health_context_for_local_advisory(actor, str(intent or ""))
    memory["local_advisory_context_status"] = memory_context.get("status")
    memory["local_advisory_fields"] = memory_context.get("included_fields") or []
    rag = _rag_metadata(actor, clean_command, str(intent or ""), emergency)
    advisory = _local_advisory(
        actor,
        clean_command,
        intent=str(intent or "general_agent"),
        privacy_class=privacy_class,
        emergency=emergency,
        memory=memory,
        memory_context=memory_context,
        rag=rag,
    )

    return {
        "version": CARE_CHAIN_VERSION,
        "prepared_at": now_iso(),
        "safety": {
            "emergency": emergency,
            "reason": safety.get("reason"),
            "model_bypasses_safety": False,
        },
        "input": input_evidence,
        "health_memory": memory,
        "rag": rag,
        "local_advisory": advisory,
        "truth": {
            "model_output_executes_tools": False,
            "rag_evidence_is_provider_confirmation": False,
            "health_memory_counts_expose_raw_records": False,
            "minimum_health_context_persisted_in_audit": False,
            "cloud_model_used_for_health_sensitive_chain": False,
        },
    }


def _record_chain_audit(actor: Any, result: dict, chain: dict) -> int:
    plan = result.get("plan") if isinstance(result.get("plan"), dict) else {}
    task = result.get("workflow_task") if isinstance(result.get("workflow_task"), dict) else {}
    journey = result.get("care_journey") if isinstance(result.get("care_journey"), dict) else {}
    entity_id = (
        f"plan:{str(plan.get('plan_id') or '')[:40]};"
        f"task:{int(task.get('id') or 0)};"
        f"journey:{int(journey.get('id') or 0)};"
        f"input:{str((chain.get('input') or {}).get('channel') or 'typed')[:32]}"
    )
    actor_id = _actor_id(actor)
    cursor = get_db().execute(
        """
        INSERT INTO audit_logs (actor_id,action,entity_type,entity_id,created_at)
        VALUES (?,?,?,?,?)
        """,
        (actor_id, "care_chain_snapshot", "care_chain", entity_id, now_iso()),
    )
    inserted_id = getattr(cursor, "lastrowid", None)
    if inserted_id:
        return int(inserted_id)
    row = get_db().execute(
        """
        SELECT id FROM audit_logs
        WHERE actor_id=? AND action='care_chain_snapshot'
          AND entity_type='care_chain' AND entity_id=?
        ORDER BY id DESC LIMIT 1
        """,
        (actor_id, entity_id),
    ).fetchone()
    if not row:
        raise RuntimeError("Care-chain audit evidence could not be resolved.")
    return int(row["id"])


def finalize_care_chain(actor: Any, result: dict, prepared: dict) -> dict:
    """Attach persisted Agent OS, provider/outcome and audit truth to the chain."""
    chain = dict(prepared or {})
    task = result.get("workflow_task") if isinstance(result.get("workflow_task"), dict) else None
    journey = result.get("care_journey") if isinstance(result.get("care_journey"), dict) else None

    chain["agent_os"] = {
        "status": str(result.get("execution_status") or "unknown").upper(),
        "assigned_agent": result.get("assigned_agent"),
        "intent": result.get("intent"),
        "plan_id": (result.get("plan") or {}).get("plan_id") if isinstance(result.get("plan"), dict) else None,
        "workflow_task_id": int(task["id"]) if task and task.get("id") else None,
        "workflow_task_status": task.get("status") if task else None,
        "deterministic_server_validation": True,
    }
    chain["safe_action"] = {
        "status": (
            "WAITING_HUMAN"
            if bool(result.get("requires_confirmation"))
            else "BOUNDED_STEP_COMPLETE"
        ),
        "requires_confirmation": bool(result.get("requires_confirmation")),
        "human_gate": result.get("human_gate"),
        "payment_executed": False,
        "clinical_authority_delegated_to_model": False,
    }

    continuity = None
    if journey and journey.get("id"):
        continuity = get_care_continuity_snapshot(actor, int(journey["id"]))
    chain["continuity"] = continuity

    appointment = (continuity or {}).get("appointment") or {}
    evidence = (continuity or {}).get("evidence") or {}
    appointment_status = appointment.get("status")
    if not continuity:
        provider_status = "NOT_APPLICABLE_OR_NOT_LINKED"
    elif appointment_status == "completed":
        provider_status = "PROVIDER_COMPLETED"
    elif appointment_status == "confirmed":
        provider_status = "PROVIDER_CONFIRMED"
    elif appointment_status == "requested":
        provider_status = "WAITING_PROVIDER"
    else:
        provider_status = "NOT_YET_REQUESTED"

    chain["provider_confirmation"] = {
        "status": provider_status,
        "appointment_id": appointment.get("id"),
        "provider_confirmed": bool(evidence.get("provider_confirmed")),
        "model_can_assert_confirmation": False,
    }
    chain["outcome"] = {
        "status": "VERIFIED" if evidence.get("verified_outcome_present") else "NOT_VERIFIED_YET",
        "care_outcome_id": evidence.get("verified_outcome_id"),
        "clinical_findings_inferred_from_completion": False,
    }
    chain["longitudinal_memory"] = {
        "status": (
            "PROVIDER_RECORDED"
            if evidence.get("provider_recorded_health_memory")
            else "AWAITING_AUTHORITATIVE_OUTCOME"
        ),
        "health_memory_event_id": evidence.get("health_memory_event_id"),
        "provenance": evidence.get("health_memory_provenance"),
        "patient_report_becomes_provider_record": False,
    }

    audit_id = _record_chain_audit(actor, result, chain)
    chain["audit"] = {
        "status": "RECORDED",
        "audit_log_id": audit_id,
        "asr_audit_log_id": (chain.get("input") or {}).get("asr_audit_log_id"),
        "model_execution_log_id": (chain.get("local_advisory") or {}).get("model_execution_log_id"),
        "raw_prompt_stored": False,
        "raw_transcript_stored": False,
        "raw_health_memory_copied": False,
    }
    result["care_chain"] = chain
    return result


def build_persisted_care_chain(actor: Any, journey_id: int) -> dict:
    """Reconstruct the authoritative downstream half of an existing Care Journey."""
    continuity = get_care_continuity_snapshot(actor, int(journey_id))
    evidence = continuity.get("evidence") or {}
    appointment = continuity.get("appointment") or {}

    audit_count = get_db().execute(
        """
        SELECT COUNT(*) AS c
        FROM audit_logs
        WHERE actor_id=? AND action='care_chain_snapshot'
          AND entity_type='care_chain' AND entity_id LIKE ?
        """,
        (_actor_id(actor), f"%journey:{int(journey_id)};%"),
    ).fetchone()["c"]

    return {
        "version": CARE_CHAIN_VERSION,
        "journey_id": int(journey_id),
        "state": continuity.get("state"),
        "provider_confirmation": {
            "appointment_id": appointment.get("id"),
            "appointment_status": appointment.get("status"),
            "provider_confirmed": bool(evidence.get("provider_confirmed")),
        },
        "outcome": {
            "verified": bool(evidence.get("verified_outcome_present")),
            "care_outcome_id": evidence.get("verified_outcome_id"),
        },
        "longitudinal_memory": {
            "provider_recorded": bool(evidence.get("provider_recorded_health_memory")),
            "health_memory_event_id": evidence.get("health_memory_event_id"),
            "provenance": evidence.get("health_memory_provenance"),
        },
        "next_safe_actions": continuity.get("available_next_safe_actions") or [],
        "audit_snapshot_count": int(audit_count or 0),
        "truth": continuity.get("truth") or {},
    }
