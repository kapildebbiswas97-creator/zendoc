"""Bounded specialist-agent orchestration for the ZENDOC Agent OS.

This module turns the existing planner/registry/tool system into a usable staged
workflow. Reversible/read-only steps run immediately. Consequential actions are
prepared but remain behind existing deterministic user/clinician/owner gates.

It intentionally does not expose arbitrary tools, URLs, SQL, shell, filesystem,
code execution, payment execution, prescribing, or emergency dispatch.
"""
from __future__ import annotations

import re
from dataclasses import replace

from .agent_executor import execute_plan
from .agentic_decision_layer import evaluate_agent_control
from .agent_planner import PlanStep, build_plan


_SPECIALTY_ALIASES = (
    (("cardiologist", "heart doctor", "heart specialist"), "Cardiology"),
    (("dermatologist", "skin doctor", "skin specialist"), "Dermatology"),
    (("neurologist", "brain doctor", "neuro doctor"), "Neurology"),
    (("orthopedist", "orthopaedist", "orthopedic", "orthopaedic", "bone doctor"), "Orthopedics"),
    (("pediatrician", "paediatrician", "child doctor"), "Pediatrics"),
    (("gynecologist", "gynaecologist", "gyne doctor", "gynae doctor"), "Gynecology"),
    (("psychiatrist",), "Psychiatry"),
    (("ophthalmologist", "eye doctor", "eye specialist"), "Ophthalmology"),
    (("ent doctor", "ear nose throat doctor"), "ENT"),
    (("general physician", "general doctor", "physician"), "General Medicine"),
)

_TEMPORAL_TAIL = re.compile(
    r"\b(?:today|tomorrow|tonight|this\s+(?:morning|afternoon|evening|week|month)|"
    r"next\s+(?:week|month|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"on\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b.*$",
    re.IGNORECASE,
)


def _value(actor, key, default=None):
    if actor is None:
        return default
    if hasattr(actor, "keys") and key in actor.keys():
        return actor[key]
    return actor.get(key, default) if isinstance(actor, dict) else default


def _clean_context(context):
    raw = context if isinstance(context, dict) else {}
    cleaned = {}
    if raw.get("provider_profile_id") not in (None, ""):
        try:
            cleaned["provider_profile_id"] = int(raw["provider_profile_id"])
        except (TypeError, ValueError) as exc:
            raise ValueError("provider_profile_id must be an integer.") from exc
    if raw.get("date"):
        cleaned["date"] = str(raw.get("date") or "").strip()[:10]
    if raw.get("category"):
        cleaned["category"] = str(raw.get("category") or "").strip().lower()[:60]
    return cleaned


def _booking_discovery_arguments(command):
    """Normalize ordinary booking language without inventing location or availability."""
    text = " ".join(str(command or "").strip().split())[:500]
    lower = text.lower()

    specialty = ""
    for aliases, canonical in _SPECIALTY_ALIASES:
        if canonical.lower() in lower or any(alias in lower for alias in aliases):
            specialty = canonical
            break

    location = ""
    for marker in (" in ", " near "):
        if marker in lower:
            start = lower.rfind(marker) + len(marker)
            candidate = text[start:].strip(" ,.-")
            candidate = _TEMPORAL_TAIL.sub("", candidate).strip(" ,.-")
            if candidate.lower() not in {"me", "my location", "current location", "nearby"}:
                location = candidate[:100]
            break

    if specialty and location:
        normalized_query = f"{specialty} in {location}"
    elif specialty:
        normalized_query = specialty
    else:
        normalized_query = text

    result = {"query": normalized_query}
    if location:
        result["location"] = location
    return result


def _specialize_plan(plan, context):
    """Apply only fixed, allowlisted context transitions to an existing plan."""
    if plan.intent == "appointment_booking" and context.get("provider_profile_id") and context.get("date"):
        return replace(
            plan,
            assigned_agent="BookingAgent",
            risk_level="read_only",
            steps=(
                PlanStep(
                    1,
                    "get_provider_booking_options",
                    {
                        "provider_profile_id": context["provider_profile_id"],
                        "date": context["date"],
                    },
                    "Read verified provider-published availability before any appointment is created.",
                ),
            ),
            requires_confirmation=True,
            required_context=("verified_provider", "selected_date"),
            human_gate="explicit_user_confirmation_before_booking",
            expected_output="verified_provider_slots",
            fallback_strategy="no_booking_when_availability_unknown",
        )

    if plan.intent == "appointment_booking" and plan.steps:
        step = plan.steps[0]
        if step.tool_name == "search_healthcare_providers":
            return replace(
                plan,
                steps=(
                    replace(
                        step,
                        arguments=_booking_discovery_arguments(plan.command),
                    ),
                ),
            )

    if plan.intent == "health_commerce" and context.get("category") and plan.steps:
        step = plan.steps[0]
        return replace(
            plan,
            steps=(
                replace(
                    step,
                    arguments={**dict(step.arguments or {}), "category": context["category"]},
                ),
            ),
        )
    return plan


def _first_output(execution):
    results = execution.get("tool_results") or []
    return results[0].get("output") if results else None


def _payload_for_plan(plan, execution):
    """Preserve established single-tool payloads while retaining bounded multi-step evidence."""
    results = execution.get("tool_results") or []
    if plan.intent == "health_records":
        health_memory = results[0].get("output") if len(results) > 0 else None
        retrieval = results[1].get("output") if len(results) > 1 else None
        return {
            "health_memory": health_memory or {},
            "retrieval": retrieval or {
                "status": "NO_MATCHES",
                "matches": [],
                "context_lines": [],
                "model_called": False,
            },
        }
    return _first_output(execution)


def _compose(plan, execution, payload):
    intent = plan.intent
    actions = []
    message = "The specialist agent completed the bounded part of this request."

    if intent == "appointment_booking":
        if isinstance(payload, dict) and "available_slots" in payload:
            slots = payload.get("available_slots") or []
            message = (
                f"Booking Agent checked {payload.get('provider_name') or 'the selected provider'} on "
                f"{payload.get('date')}. It found {len(slots)} currently free ZENDOC-connected slot(s). "
                "No appointment has been created. Choose a slot and explicitly confirm the request."
            )
            actions = [{
                "type": "booking_slots",
                "label": "Choose a verified slot",
                "provider_profile_id": payload.get("provider_profile_id"),
                "date": payload.get("date"),
                "slots": slots,
                "confirmation_required": True,
            }]
        else:
            registered = payload.get("registered_providers", []) if isinstance(payload, dict) else []
            external = (payload.get("external_places") or {}).get("results", []) if isinstance(payload, dict) else []
            message = (
                f"Booking Agent found {len(registered)} ZENDOC-verified provider(s) and {len(external)} external discovery result(s). "
                "Only verified connected ZENDOC providers can expose in-app appointment slots. Select one and a date to continue."
            )
            actions = [{
                "type": "provider_shortlist",
                "label": "Select a verified provider and date",
                "providers": registered,
                "external_results": external,
            }]

    elif intent == "health_commerce":
        results = payload.get("results", []) if isinstance(payload, dict) else []
        message = (
            f"Commerce Agent prepared {len(results)} external health-product search/catalog handoff(s). "
            "Stock, price, seller suitability, affiliate status, checkout and payment are not claimed or executed."
        )
        actions = [{"type": "commerce_handoffs", "label": "Review external product searches", "results": results}]

    elif intent == "health_records":
        memory = payload.get("health_memory", {}) if isinstance(payload, dict) else {}
        retrieval = payload.get("retrieval", {}) if isinstance(payload, dict) else {}
        matches = retrieval.get("matches", []) if isinstance(retrieval, dict) else []
        message = (
            f"Health Memory Agent built the authorized longitudinal context and retrieved {len(matches)} "
            "matching stored evidence item(s). Provenance is preserved and prior AI chat is excluded from medical evidence."
        )
        actions = [{
            "type": "health_memory_evidence",
            "label": "Review matching Health Memory evidence",
            "data": {
                "context": memory,
                "retrieval": retrieval,
            },
        }]

    elif intent == "preventive_care":
        next_actions = payload.get("next_safe_actions", []) if isinstance(payload, dict) else []
        message = (
            f"Prevention Agent reviewed authorized minimum-necessary Health Memory context and found {len(next_actions)} "
            "non-clinical next-safe action(s). It did not diagnose or change treatment."
        )
        actions = [{"type": "prevention_context", "label": "Review prevention context", "data": payload or {}}]

    elif intent == "lifecycle":
        message = (
            "Life-stage Continuity Agent used only authorized context for the explicitly selected journey. "
            "It does not infer pregnancy, fertility, menopause, child status, or another sensitive life stage from profile data."
        )
        actions = [{"type": "lifecycle_context", "label": "Review life-stage continuity context", "data": payload or {}}]

    elif intent == "health_learning":
        results = payload.get("results", []) if isinstance(payload, dict) else []
        reason = payload.get("reason") if isinstance(payload, dict) else None
        message = reason or f"Health Learning Agent found {len(results)} educational resource result(s)."
        actions = [{"type": "learning_resources", "label": "Review health learning resources", "data": payload or {}}]

    elif intent == "fitness":
        message = (
            "Fitness Agent is responsible for this request. It can work with the authenticated user's fitness profile, plans, "
            "sessions and progress while keeping medical restrictions outside autonomous fitness coaching."
        )
        actions = [{"type": "fitness", "label": "Open Fitness", "url": "/fitness"}]

    elif intent == "model_improvement":
        message = (
            "Model Improvement Agent may prepare and evaluate candidates only inside the isolated offline evaluation boundary. "
            "It has no production tools and cannot promote, deploy, broaden permissions, or disable safeguards by itself."
        )
        actions = [{"type": "model_evaluation", "label": "Open owner Model Evaluation Lab", "url": "/admin/model-evaluation"}]

    elif intent == "provider_discovery":
        registered = payload.get("registered_providers", []) if isinstance(payload, dict) else []
        external = (payload.get("external_places") or {}).get("results", []) if isinstance(payload, dict) else []
        message = (
            f"Provider Discovery Agent found {len(registered)} ZENDOC-verified provider(s) and {len(external)} external location result(s). "
            "External discovery is not treated as verified credentials or live booking availability."
        )
        actions = [{"type": "provider_discovery", "label": "Review provider options", "data": payload or {}}]

    elif intent == "diagnostics":
        offers = payload.get("offers", []) if isinstance(payload, dict) else []
        message = (
            f"Diagnostics Agent found {len(offers)} offer record(s). Availability truth states are preserved and booking remains user-confirmed."
        )
        actions = [{"type": "diagnostics", "label": "Review diagnostic options", "data": payload or {}}]

    elif intent == "pharmacy":
        offers = payload.get("offers", []) if isinstance(payload, dict) else []
        message = (
            f"Pharmacy Agent found {len(offers)} inventory offer record(s). It has not changed a prescription or submitted an order."
        )
        actions = [{"type": "pharmacy", "label": "Review pharmacy options", "data": payload or {}}]

    elif intent == "carefin":
        count = int((payload or {}).get("candidate_count", 0)) if isinstance(payload, dict) else 0
        message = (
            f"CareFin Agent found {count} possible support pathway(s). Eligibility, approval and payment remain unconfirmed until authoritative evidence exists."
        )
        actions = [{"type": "carefin", "label": "Review support pathways", "data": payload or {}}]

    else:
        if payload is not None:
            actions = [{"type": "specialist_result", "label": "Review specialist result", "data": payload}]
        else:
            actions = [{"type": "specialist_navigation", "label": "Continue in the relevant ZENDOC workflow"}]

    return {
        "intent": intent,
        "assigned_agent": plan.assigned_agent,
        "risk_level": plan.risk_level,
        "privacy_class": plan.privacy_class,
        "execution_status": execution.get("status", "completed"),
        "message": message,
        "actions": actions,
        "payload": payload,
        "requires_confirmation": bool(plan.requires_confirmation),
        "human_gate": plan.human_gate,
        "plan": plan.to_dict(),
        "truth": {
            "arbitrary_tool_access": False,
            "payment_executed": False,
            "clinical_authority_delegated_to_model": False,
            "production_self_modification": False,
        },
    }


def orchestrate_specialist(actor, command_text: str, context=None) -> dict:
    """Plan and run only bounded specialist work for one authenticated actor."""
    if not actor:
        raise PermissionError("Authentication required.")
    plan = build_plan(actor, command_text)
    if plan.authorization_error:
        raise PermissionError(plan.authorization_error)
    context = _clean_context(context)
    plan = _specialize_plan(plan, context)
    decision_control = evaluate_agent_control(plan, command_text, context)

    if plan.steps and decision_control.get("allow_reversible_execution", True):
        execution = execute_plan(plan, actor)
    elif plan.steps:
        execution = {
            "status": "blocked" if decision_control.get("action") == "STOP" else "waiting_human",
            "tool_results": [],
        }
    else:
        execution = {
            "status": "waiting_human" if plan.requires_confirmation else "completed",
            "tool_results": [],
        }
    payload = _payload_for_plan(plan, execution)
    result = _compose(plan, execution, payload)
    result["decision_control"] = decision_control
    return result
