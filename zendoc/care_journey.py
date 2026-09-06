"""Automatic Care Journey coordinator for ZENDOC.

This module coordinates workflow state only. It never diagnoses, prescribes,
approves insurance/schemes, dispatches emergency services, or executes a
consequential action without the required human/authority gate.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


NEW = "NEW"
CONTEXT_READY = "CONTEXT_READY"
WAITING_INFORMATION = "WAITING_INFORMATION"
PROVIDER_SEARCH = "PROVIDER_SEARCH"
WAITING_USER_SELECTION = "WAITING_USER_SELECTION"
APPOINTMENT_STAGED = "APPOINTMENT_STAGED"
WAITING_PROVIDER = "WAITING_PROVIDER"
CONSULTATION = "CONSULTATION"
PRESCRIPTION_RECEIVED = "PRESCRIPTION_RECEIVED"
DIAGNOSTICS_REQUIRED = "DIAGNOSTICS_REQUIRED"
CAREFIN_CHECK = "CAREFIN_CHECK"
FULFILMENT = "FULFILMENT"
FOLLOW_UP = "FOLLOW_UP"
COMPLETED = "COMPLETED"
BLOCKED = "BLOCKED"
WAITING_HUMAN = "WAITING_HUMAN"

CARE_JOURNEY_STATES = {
    NEW,
    CONTEXT_READY,
    WAITING_INFORMATION,
    PROVIDER_SEARCH,
    WAITING_USER_SELECTION,
    APPOINTMENT_STAGED,
    WAITING_PROVIDER,
    CONSULTATION,
    PRESCRIPTION_RECEIVED,
    DIAGNOSTICS_REQUIRED,
    CAREFIN_CHECK,
    FULFILMENT,
    FOLLOW_UP,
    COMPLETED,
    BLOCKED,
    WAITING_HUMAN,
}

TERMINAL_STATES = {COMPLETED, BLOCKED}

_ALLOWED = {
    NEW: {CONTEXT_READY, WAITING_INFORMATION, BLOCKED},
    CONTEXT_READY: {PROVIDER_SEARCH, CAREFIN_CHECK, WAITING_INFORMATION, BLOCKED},
    WAITING_INFORMATION: {CONTEXT_READY, PROVIDER_SEARCH, CAREFIN_CHECK, WAITING_HUMAN, BLOCKED},
    PROVIDER_SEARCH: {WAITING_USER_SELECTION, WAITING_INFORMATION, BLOCKED},
    WAITING_USER_SELECTION: {APPOINTMENT_STAGED, WAITING_HUMAN, PROVIDER_SEARCH, BLOCKED},
    APPOINTMENT_STAGED: {WAITING_PROVIDER, WAITING_HUMAN, BLOCKED},
    WAITING_PROVIDER: {CONSULTATION, APPOINTMENT_STAGED, WAITING_HUMAN, BLOCKED},
    CONSULTATION: {PRESCRIPTION_RECEIVED, DIAGNOSTICS_REQUIRED, CAREFIN_CHECK, FOLLOW_UP, WAITING_HUMAN, BLOCKED},
    PRESCRIPTION_RECEIVED: {DIAGNOSTICS_REQUIRED, CAREFIN_CHECK, FULFILMENT, WAITING_HUMAN, BLOCKED},
    DIAGNOSTICS_REQUIRED: {CAREFIN_CHECK, FULFILMENT, FOLLOW_UP, WAITING_HUMAN, BLOCKED},
    CAREFIN_CHECK: {FULFILMENT, FOLLOW_UP, WAITING_HUMAN, BLOCKED},
    FULFILMENT: {FOLLOW_UP, WAITING_HUMAN, BLOCKED},
    FOLLOW_UP: {COMPLETED, PROVIDER_SEARCH, WAITING_HUMAN, BLOCKED},
    WAITING_HUMAN: {
        CONTEXT_READY,
        PROVIDER_SEARCH,
        WAITING_USER_SELECTION,
        APPOINTMENT_STAGED,
        WAITING_PROVIDER,
        CONSULTATION,
        PRESCRIPTION_RECEIVED,
        DIAGNOSTICS_REQUIRED,
        CAREFIN_CHECK,
        FULFILMENT,
        FOLLOW_UP,
        BLOCKED,
    },
    COMPLETED: set(),
    BLOCKED: set(),
}


@dataclass(frozen=True)
class JourneyEvent:
    previous_state: str
    state: str
    reason: str
    actor_type: str
    provenance: dict
    occurred_at: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CareJourney:
    journey_id: str
    patient_id: int
    state: str = NEW
    next_safe_action: str = "collect_context"
    blocked_reason: str | None = None
    required_actor: str | None = None
    required_consent: str | None = None
    provenance: dict = field(default_factory=dict)
    history: tuple[JourneyEvent, ...] = ()

    def to_dict(self) -> dict:
        data = asdict(self)
        data["history"] = [event.to_dict() for event in self.history]
        data["terminal"] = self.state in TERMINAL_STATES
        return data


def start_journey(
    *,
    patient_id: int,
    journey_id: str,
    provenance: dict | None = None,
) -> CareJourney:
    if int(patient_id or 0) <= 0:
        raise ValueError("patient_id must be positive.")
    clean_id = str(journey_id or "").strip()
    if not clean_id:
        raise ValueError("journey_id is required.")
    return CareJourney(
        journey_id=clean_id,
        patient_id=int(patient_id),
        state=NEW,
        next_safe_action="collect_minimum_necessary_context",
        provenance=dict(provenance or {}),
    )


def transition_journey(
    journey: CareJourney,
    *,
    target_state: str,
    reason: str,
    actor_type: str = "system",
    next_safe_action: str | None = None,
    required_actor: str | None = None,
    required_consent: str | None = None,
    blocked_reason: str | None = None,
    provenance: dict | None = None,
) -> CareJourney:
    target = str(target_state or "").strip().upper()
    if target not in CARE_JOURNEY_STATES:
        raise ValueError("Unknown care journey state.")
    if journey.state in TERMINAL_STATES:
        raise ValueError(f"Care journey is terminal in state {journey.state}.")
    if target not in _ALLOWED[journey.state]:
        raise ValueError(f"Invalid care journey transition: {journey.state} -> {target}.")

    reason_text = str(reason or "").strip()
    if not reason_text:
        raise ValueError("A transition reason is required.")

    if target == WAITING_HUMAN and not required_actor:
        raise ValueError("WAITING_HUMAN requires required_actor.")
    if target == BLOCKED and not blocked_reason:
        raise ValueError("BLOCKED requires blocked_reason.")
    if target in {APPOINTMENT_STAGED, FULFILMENT} and actor_type == "ai":
        # AI may propose/stage bounded read-only workflow output, but the state
        # must make the human gate explicit before a consequential action.
        required_actor = required_actor or "patient"
    if target == COMPLETED and required_actor:
        raise ValueError("A completed journey cannot still require a human actor.")

    event = JourneyEvent(
        previous_state=journey.state,
        state=target,
        reason=reason_text[:500],
        actor_type=str(actor_type or "system")[:80],
        provenance=dict(provenance or {}),
        occurred_at=_now(),
    )
    action = str(next_safe_action or _default_next_action(target)).strip()
    return CareJourney(
        journey_id=journey.journey_id,
        patient_id=journey.patient_id,
        state=target,
        next_safe_action=action,
        blocked_reason=str(blocked_reason).strip() if blocked_reason else None,
        required_actor=str(required_actor).strip() if required_actor else None,
        required_consent=str(required_consent).strip() if required_consent else None,
        provenance={**journey.provenance, **dict(provenance or {})},
        history=journey.history + (event,),
    )


def _default_next_action(state: str) -> str:
    return {
        NEW: "collect_minimum_necessary_context",
        CONTEXT_READY: "identify_care_goal",
        WAITING_INFORMATION: "collect_missing_information",
        PROVIDER_SEARCH: "search_verified_and_external_providers",
        WAITING_USER_SELECTION: "ask_user_to_select_provider",
        APPOINTMENT_STAGED: "ask_user_to_confirm_appointment",
        WAITING_PROVIDER: "wait_for_provider_response",
        CONSULTATION: "coordinate_consultation_without_clinical_authority",
        PRESCRIPTION_RECEIVED: "run_medication_safety_review",
        DIAGNOSTICS_REQUIRED: "find_truthful_diagnostic_options",
        CAREFIN_CHECK: "discover_and_verify_support_pathways",
        FULFILMENT: "stage_fulfilment_and_request_confirmation",
        FOLLOW_UP: "schedule_safe_follow_up",
        WAITING_HUMAN: "wait_for_required_human",
        COMPLETED: "none",
        BLOCKED: "resolve_blocked_reason",
    }[state]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
