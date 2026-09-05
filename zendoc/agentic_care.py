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
from .agent_task_engine import get_agent_task


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
    verification = verify_agentic_result(actor, result)

    lifecycle.append(
        {
            "stage": "ACT",
            "status": "waiting_confirmation" if requires_confirmation else verification["act_status"],
            "summary": (
                "Consequential action is staged and waiting for explicit human confirmation."
                if requires_confirmation
                else verification["act_summary"]
            ),
        }
    )

    lifecycle.append(
        {
            "stage": "VERIFY",
            "status": verification["status"],
            "summary": verification["summary"],
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
        "execution_truth": verification["truth_state"],
        "verification": verification,
    }


def verify_agentic_result(actor, result: dict) -> dict:
    """Verify a run from authoritative persisted task state.

    The verifier never upgrades an internal task into a real-world success.
    Provider acceptance/delivery/dispatch must be represented by an explicit
    provider workflow state before it can be reported as such.
    """
    task_id = int(result.get("task_id") or 0)
    if not task_id:
        return {
            "status": "unknown",
            "truth_state": "UNKNOWN",
            "act_status": "unknown",
            "act_summary": "No persistent task identifier was returned.",
            "summary": "Verification could not prove an authoritative task state.",
        }

    task = get_agent_task(task_id, actor=actor)
    state = str(task.get("status") or "").lower()
    mapping = {
        "waiting_human": (
            "waiting_confirmation",
            "WAITING_HUMAN",
            "The task is persistently waiting for explicit human confirmation.",
        ),
        "waiting_approval": (
            "waiting_confirmation",
            "WAITING_HUMAN",
            "The task is persistently waiting for an authorized approval.",
        ),
        "waiting_provider": (
            "waiting_provider",
            "WAITING_PROVIDER",
            "The request exists internally and is waiting for an authoritative provider response.",
        ),
        "queued": (
            "queued",
            "REQUEST_CREATED",
            "The task is queued in ZENDOC; no external completion is claimed.",
        ),
        "running": (
            "running",
            "REQUEST_CREATED",
            "The bounded ZENDOC task is running; no external completion is claimed.",
        ),
        "completed": (
            "completed",
            "BOUNDED_EXECUTION_VERIFIED",
            "ZENDOC verified completion of the bounded internal tool/task execution only.",
        ),
        "failed": (
            "failed",
            "FAILED",
            "The authoritative ZENDOC task state is failed.",
        ),
        "cancelled": (
            "cancelled",
            "CANCELLED",
            "The authoritative ZENDOC task state is cancelled.",
        ),
    }
    stage_status, truth_state, summary = mapping.get(
        state,
        ("unknown", "UNKNOWN", "The task state is not recognized, so success is not claimed."),
    )
    return {
        "status": stage_status,
        "truth_state": truth_state,
        "act_status": stage_status,
        "act_summary": summary,
        "summary": summary,
        "task_status": state or "unknown",
        "task_id": task_id,
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
