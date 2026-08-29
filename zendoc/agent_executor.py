"""Permissioned, bounded plan executor. No shell, SQL, filesystem, or arbitrary call access."""
from __future__ import annotations

import time

from .agent_registry import get_agent
from .agent_task_engine import EXECUTION_TIMEOUT_SECONDS, MAX_STEPS
from .tool_registry import check_tool_access, get_tool


def _value(actor, key, default=None):
    if actor is None:
        return default
    if hasattr(actor, "keys") and key in actor.keys():
        return actor[key]
    return actor.get(key, default) if isinstance(actor, dict) else default


def execute_plan(plan, actor) -> dict:
    if plan.authorization_error:
        raise PermissionError(plan.authorization_error)
    agent = get_agent(plan.assigned_agent)
    if not agent:
        raise LookupError("Assigned specialized agent is not registered.")
    role = _value(actor, "role", "")
    if role not in agent.allowed_actor_roles:
        raise PermissionError(f"Role '{role}' cannot invoke {agent.name}.")
    if len(plan.steps) > MAX_STEPS:
        raise ValueError(f"Plan exceeds the {MAX_STEPS}-step execution limit.")

    started = time.perf_counter()
    results = []
    for step in plan.steps:
        if time.perf_counter() - started > EXECUTION_TIMEOUT_SECONDS:
            raise TimeoutError("Plan execution exceeded the bounded request timeout.")
        tool = get_tool(step.tool_name)
        decision = check_tool_access(step.tool_name, actor, plan.assigned_agent)
        if not decision["allowed"]:
            raise PermissionError(decision["reason"])
        if tool.requires_consent or tool.requires_doctor_approval:
            raise PermissionError(f"Tool '{tool.name}' requires an explicit human authorization workflow.")
        handler = TOOL_HANDLERS.get(step.tool_name)
        if not handler:
            raise LookupError(f"Tool '{step.tool_name}' has no bounded server-side handler.")
        tool_started = time.perf_counter()
        output = handler(actor, dict(step.arguments or {}))
        results.append(
            {
                "sequence": step.sequence,
                "tool_name": step.tool_name,
                "status": "completed",
                "duration_ms": int((time.perf_counter() - tool_started) * 1000),
                "output": output,
            }
        )
    return {
        "plan_id": plan.plan_id,
        "intent": plan.intent,
        "assigned_agent": plan.assigned_agent,
        "status": "completed" if not plan.requires_confirmation else "waiting_human",
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "tool_results": results,
    }


def _platform_summary(actor, arguments):
    from .agent_core import get_platform_health
    return get_platform_health()


def _failed_operations(actor, arguments):
    from .agent_core import get_failed_operations
    return get_failed_operations(limit=25)


def _find_contact(actor, arguments):
    from .connect import discover_contacts
    return discover_contacts(actor, query=str(arguments.get("query") or "")[:120])


def _unread_summary(actor, arguments):
    from .connect import unread_count
    return {"unread_count": unread_count(actor)}


def _educational_video(actor, arguments):
    from .video_intelligence import find_educational_video
    return find_educational_video(
        actor,
        str(arguments.get("query") or "")[:500],
        category=str(arguments.get("category") or "fitness")[:80],
    )


def _iot_devices(actor, arguments):
    from .iot_hub import list_devices
    return list_devices(actor)


def _alert_check(actor, arguments):
    from .security import assert_owner
    from .agent_alerts import run_proactive_alert_check
    assert_owner(actor)
    return {"created_alerts": run_proactive_alert_check()}


TOOL_HANDLERS = {
    "get_platform_summary": _platform_summary,
    "get_failed_operations": _failed_operations,
    "find_contact": _find_contact,
    "get_unread_summary": _unread_summary,
    "search_educational_video": _educational_video,
    "get_iot_devices": _iot_devices,
    "run_proactive_alert_check": _alert_check,
}
