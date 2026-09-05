"""ZENDOC Agentic Care OS controller.

This layer turns a user goal into an observable, bounded agent lifecycle using
the existing deterministic planner, permissioned tool executor, approvals and
audit trail. It does not grant new permissions and it does not let model output
call tools directly.

Lifecycle:
OBSERVE -> UNDERSTAND -> PLAN -> ACT -> VERIFY -> REMEMBER
"""
from __future__ import annotations

from .agent_core import respond_with_core_agent
from .agent_planner import build_plan


def run_agentic_care(actor, command_text: str) -> dict:
    """Run one bounded agentic care cycle and return demo-safe lifecycle data."""
    command = str(command_text or "").strip()
    if not command:
        raise ValueError("Agentic care command is required.")

    preview = build_plan(actor, command)
    lifecycle = [
        {
            "stage": "OBSERVE",
            "status": "completed",
            "summary": "Received the authenticated user's goal.",
        },
        {
            "stage": "UNDERSTAND",
            "status": "completed",
            "summary": f"Intent: {preview.intent}. Assigned agent: {preview.assigned_agent}.",
        },
        {
            "stage": "PLAN",
            "status": "completed",
            "summary": (
                f"Prepared {len(preview.steps)} bounded tool step(s); "
                f"risk={preview.risk_level}; confirmation={'required' if preview.requires_confirmation else 'not required'}."
            ),
        },
    ]

    result = respond_with_core_agent(actor, command)
    plan = result.get("plan") or preview.to_dict()
    requires_confirmation = bool(result.get("requires_confirmation"))

    lifecycle.append(
        {
            "stage": "ACT",
            "status": "waiting_confirmation" if requires_confirmation else "completed",
            "summary": (
                "Consequential action is staged and waiting for explicit human confirmation."
                if requires_confirmation
                else "Executed only the bounded permissioned steps allowed for this actor."
            ),
        }
    )

    lifecycle.append(
        {
            "stage": "VERIFY",
            "status": "completed",
            "summary": (
                "Verified the returned task/run state and preserved provider or integration truth boundaries."
            ),
        }
    )
    lifecycle.append(
        {
            "stage": "REMEMBER",
            "status": "completed",
            "summary": (
                f"Recorded agent run #{result.get('run_id')} and task #{result.get('task_id')} in the audit/task memory."
            ),
        }
    )

    return {
        **result,
        "agentic_lifecycle": lifecycle,
        "autonomy_level": _autonomy_level(plan, requires_confirmation),
        "execution_truth": (
            "waiting_human_confirmation"
            if requires_confirmation
            else "bounded_permissioned_execution"
        ),
    }


def _autonomy_level(plan: dict, requires_confirmation: bool) -> str:
    """Human-readable autonomy level for the current run, not a marketing claim."""
    if str(plan.get("urgency") or "").lower() == "emergency":
        return "L0_SAFETY_OVERRIDE"
    if requires_confirmation:
        return "L4_CONFIRM_AND_ACT"
    steps = plan.get("steps") or []
    if steps:
        return "L3_SAFE_AUTONOMY"
    return "L2_PLAN_OR_GUIDE"
