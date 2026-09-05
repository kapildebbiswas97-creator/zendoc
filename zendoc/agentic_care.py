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
from .agent_task_engine import create_agent_task, execute_safe_task, get_agent_task, set_task_waiting


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



def run_orchestrated_care(actor, command_text: str) -> dict:
    """Wrap the existing healthcare orchestrator in the Agentic Care lifecycle.

    This path is for naturally phrased multi-step care goals such as family
    prescription fulfilment or diagnostics. It preserves the M11
    HealthcareOrchestrator as the domain authority and adds persistent task,
    verification, and visible agent lifecycle metadata.
    """
    from .orchestrator import HealthcareOrchestrator

    command = str(command_text or "").strip()
    if not command:
        raise ValueError("Care goal is required.")

    lifecycle = [
        {"stage": "OBSERVE", "status": "completed", "summary": "Received a multi-step healthcare goal."},
        {"stage": "UNDERSTAND", "status": "completed", "summary": "Selected the Care Agent and trust-first healthcare orchestrator."},
    ]

    plan = HealthcareOrchestrator().orchestrate(actor, command)
    plan_data = plan.to_dict()
    lifecycle.append(
        {
            "stage": "PLAN",
            "status": "completed",
            "summary": f"Prepared {len(plan.steps)} healthcare step(s); orchestration state={plan.status}.",
        }
    )

    task = create_agent_task(
        task_type="healthcare_orchestration",
        requested_by=int(actor["id"]),
        assigned_agent="CareAgent",
        priority="critical" if plan.urgency == "emergency" else "normal",
        risk_level="consent_required" if plan.status == "AWAITING_CONFIRMATION" else "read_only",
        metadata={"orchestration_plan_id": plan.plan_id, "intent": plan.intent, "status": plan.status},
        actor=actor,
    )

    if plan.status == "AWAITING_CONFIRMATION":
        task = set_task_waiting(
            task["id"],
            "waiting_human",
            "Healthcare plan is staged and waiting for explicit user confirmation.",
        )
        act_status = "waiting_confirmation"
        truth_state = "WAITING_HUMAN"
        act_summary = "The healthcare plan is staged; no consequential action has been executed."
    else:
        task = execute_safe_task(
            task["id"],
            actor,
            handler_fn=lambda _task: f"Healthcare orchestration evaluated with state {plan.status}.",
        )
        act_status = "completed" if plan.status == "COMPLETED" else "blocked"
        truth_state = {
            "COMPLETED": "BOUNDED_EXECUTION_VERIFIED",
            "BLOCKED_PERMISSION": "BLOCKED_PERMISSION",
            "BLOCKED_DATA": "BLOCKED_DATA",
            "EMERGENCY": "L0_SAFETY_OVERRIDE",
            "FAILED": "FAILED",
        }.get(plan.status, "UNKNOWN")
        act_summary = (
            "The bounded healthcare orchestration completed internally."
            if plan.status == "COMPLETED"
            else f"The healthcare orchestration stopped truthfully at {plan.status}."
        )

    lifecycle.append({"stage": "ACT", "status": act_status, "summary": act_summary})
    lifecycle.append(
        {
            "stage": "VERIFY",
            "status": "completed" if truth_state != "UNKNOWN" else "unknown",
            "summary": f"Verified orchestration state {plan.status}; truth state={truth_state}.",
        }
    )
    lifecycle.append(
        {
            "stage": "REMEMBER",
            "status": "completed",
            "summary": f"Recorded Agent task #{task['id']} and orchestration plan {plan.plan_id}.",
        }
    )

    return {
        "intent": plan.intent,
        "urgency": plan.urgency,
        "message": plan.explanation,
        "actions": [{"type": action, "label": action.replace("_", " ").title()} for action in plan.next_safe_actions],
        "requires_confirmation": plan.status == "AWAITING_CONFIRMATION",
        "task_id": task["id"],
        "run_id": None,
        "plan": {
            "plan_id": plan.plan_id,
            "intent": plan.intent,
            "urgency": plan.urgency,
            "assigned_agent": "CareAgent",
            "risk_level": "consent_required" if plan.status == "AWAITING_CONFIRMATION" else "read_only",
            "requires_confirmation": plan.status == "AWAITING_CONFIRMATION",
            "steps": [
                {
                    "sequence": index + 1,
                    "tool_name": step.tool_name or step.step_id,
                    "purpose": step.purpose,
                    "status": step.status,
                }
                for index, step in enumerate(plan.steps)
            ],
        },
        "orchestration_plan": plan_data,
        "agentic_lifecycle": lifecycle,
        "autonomy_level": "L4_CONFIRM_AND_ACT" if plan.status == "AWAITING_CONFIRMATION" else "L3_SAFE_AUTONOMY",
        "execution_truth": truth_state,
        "verification": {
            "status": plan.status,
            "truth_state": truth_state,
            "task_status": task["status"],
            "task_id": task["id"],
        },
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
