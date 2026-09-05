"""Constrained model-assisted planning for ZENDOC Agentic Care.

Models may propose candidate READ-ONLY/LOW-RISK steps, but this module never
executes model output. Every candidate is validated against the server-side
Tool Registry, agent permissions, actor permissions, argument allowlists, and a
strict step cap. Invalid candidates are rejected and callers fall back to the
existing deterministic planner.
"""
from __future__ import annotations

from dataclasses import dataclass

from .agent_planner import PlanStep
from .agent_task_engine import MAX_STEPS
from .model_router import PrivacyClass, RiskClass, get_model_router
from .tool_registry import (
    CRITICAL_BLOCKED,
    DOCTOR_APPROVAL,
    OWNER_APPROVAL,
    check_tool_access,
    get_tool,
)

MODEL_PLAN_MAX_STEPS = min(MAX_STEPS, 6)

# Model-proposed arguments are intentionally narrower than handler capability.
# Values are validated again by handlers before use.
TOOL_ARGUMENT_ALLOWLIST = {
    "find_contact": {"query"},
    "get_unread_summary": set(),
    "search_educational_video": {"query", "category"},
    "get_iot_devices": set(),
    "search_nearby_pharmacy_inventory": {
        "query", "medicine_query", "medicine_ids", "city",
        "patient_lat", "patient_lon", "radius_km", "patient_id",
    },
    "compare_prescription_fulfilment": {
        "prescription_id", "city", "patient_lat", "patient_lon",
        "radius_km", "patient_id",
    },
    "get_diagnostic_options": {
        "test_code", "test_id", "query", "city",
        "patient_lat", "patient_lon", "patient_id",
    },
    "get_unified_healthcare_inbox": {"patient_id"},
}


@dataclass(frozen=True)
class CandidatePlanValidation:
    accepted: bool
    steps: tuple[PlanStep, ...] = ()
    reason: str = "rejected"

    def to_dict(self) -> dict:
        return {
            "accepted": self.accepted,
            "reason": self.reason,
            "steps": [step.to_dict() for step in self.steps],
        }


def validate_candidate_plan(candidate, actor, assigned_agent: str) -> CandidatePlanValidation:
    """Validate one model-proposed plan without executing it."""
    if not isinstance(candidate, dict):
        return CandidatePlanValidation(False, reason="candidate_not_object")
    raw_steps = candidate.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        return CandidatePlanValidation(False, reason="steps_missing")
    if len(raw_steps) > MODEL_PLAN_MAX_STEPS:
        return CandidatePlanValidation(False, reason="step_limit_exceeded")

    validated = []
    for index, raw in enumerate(raw_steps, start=1):
        if not isinstance(raw, dict):
            return CandidatePlanValidation(False, reason="step_not_object")
        tool_name = str(raw.get("tool_name") or "").strip()
        if tool_name not in TOOL_ARGUMENT_ALLOWLIST:
            return CandidatePlanValidation(False, reason=f"tool_not_model_plannable:{tool_name or 'missing'}")

        tool = get_tool(tool_name)
        if not tool:
            return CandidatePlanValidation(False, reason=f"tool_not_registered:{tool_name}")
        if tool.risk_class in {CRITICAL_BLOCKED, DOCTOR_APPROVAL, OWNER_APPROVAL}:
            return CandidatePlanValidation(False, reason=f"tool_risk_blocked:{tool_name}")
        if tool.requires_consent or tool.requires_doctor_approval or tool.requires_owner_approval:
            return CandidatePlanValidation(False, reason=f"tool_requires_human_authority:{tool_name}")

        decision = check_tool_access(tool_name, actor, assigned_agent)
        if not decision["allowed"]:
            return CandidatePlanValidation(False, reason=f"tool_access_denied:{tool_name}")

        arguments = raw.get("arguments") or {}
        if not isinstance(arguments, dict):
            return CandidatePlanValidation(False, reason=f"arguments_not_object:{tool_name}")
        unknown_args = set(arguments) - TOOL_ARGUMENT_ALLOWLIST[tool_name]
        if unknown_args:
            return CandidatePlanValidation(False, reason=f"argument_not_allowed:{tool_name}")

        purpose = str(raw.get("purpose") or "").strip()[:240]
        validated.append(
            PlanStep(
                sequence=index,
                tool_name=tool_name,
                arguments=dict(arguments),
                purpose=purpose or f"Use {tool_name} for the bounded care goal.",
            )
        )

    return CandidatePlanValidation(True, tuple(validated), "validated")


def propose_candidate_plan(actor, command_text: str, assigned_agent: str) -> CandidatePlanValidation:
    """Ask the configured local model for a candidate plan, then validate it.

    Health-sensitive planning is local-only. Cloud routing is disabled.
    Deterministic planning remains the fallback whenever no valid model plan
    is available.
    """
    command = str(command_text or "").strip()
    if not command:
        return CandidatePlanValidation(False, reason="empty_command")

    allowed_tools = sorted(
        name
        for name in TOOL_ARGUMENT_ALLOWLIST
        if check_tool_access(name, actor, assigned_agent)["allowed"]
    )
    if not allowed_tools:
        return CandidatePlanValidation(False, reason="no_allowed_model_tools")

    system_prompt = (
        "You are a planning assistant only. Do not execute tools. "
        "Return structured JSON in data with a 'steps' array. "
        "Use only the exact allowed tool names supplied by the server. "
        "Never propose prescription, diagnosis, payment, permission changes, "
        "emergency dispatch, record sharing, or any action requiring consent."
    )
    prompt = (
        f"User goal: {command[:1200]}\n"
        f"Assigned agent: {assigned_agent}\n"
        f"Allowed tools: {', '.join(allowed_tools)}\n"
        f"Maximum steps: {MODEL_PLAN_MAX_STEPS}"
    )
    response = get_model_router().route(
        prompt,
        intent="agentic_planning",
        task_type="planning_assistance",
        privacy_sensitive=True,
        allow_cloud=False,
        system_prompt=system_prompt,
        actor_id=_actor_id(actor),
        privacy_class=PrivacyClass.HEALTH_SENSITIVE,
        risk_class=RiskClass.READ_ONLY,
        complexity="medium",
    )
    if not response.success:
        return CandidatePlanValidation(False, reason="model_unavailable")

    data = response.output.get("data") if isinstance(response.output, dict) else None
    validation = validate_candidate_plan(data, actor, assigned_agent)
    if not validation.accepted:
        return CandidatePlanValidation(False, reason=f"model_candidate_rejected:{validation.reason}")
    return validation


def _actor_id(actor) -> int | None:
    if actor is None:
        return None
    if hasattr(actor, "keys") and "id" in actor.keys():
        return int(actor["id"])
    if isinstance(actor, dict) and actor.get("id"):
        return int(actor["id"])
    return None
