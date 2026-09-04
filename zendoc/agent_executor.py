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


def _patient_target(actor, arguments, purpose):
    """Resolve and authorize a patient target for a read/stage tool."""
    from .context_engine import verify_context_authorization

    actor_id = int(_value(actor, "id", 0) or 0)
    patient_id = int(arguments.get("patient_id") or actor_id)
    verify_context_authorization(actor, patient_id, purpose)
    return patient_id


def _pharmacy_search(actor, arguments):
    from .inventory_service import search_pharmacy_offers

    patient_id = _patient_target(actor, arguments, "find_prescribed_medicines")
    offers = search_pharmacy_offers(
        query=arguments.get("query") or arguments.get("medicine_query"),
        medicine_ids=arguments.get("medicine_ids"),
        city=arguments.get("city"),
        user_lat=arguments.get("patient_lat"),
        user_lon=arguments.get("patient_lon"),
        radius_km=float(arguments.get("radius_km", 10)),
    )
    return {
        "status": "OK" if offers else "NO_RESULTS",
        "message": ("Provider inventory offers found." if offers else "No confirmed pharmacy inventory matched this request."),
        "patient_id": patient_id,
        "offers": offers,
    }


def _pharmacy_compare(actor, arguments):
    from .fulfilment_optimizer import optimize_prescription_fulfilment

    patient_id = _patient_target(actor, arguments, "pharmacy_fulfilment")
    prescription_id = int(arguments.get("prescription_id") or 0)
    if not prescription_id:
        raise ValueError("prescription_id is required for fulfilment comparison.")
    plan = optimize_prescription_fulfilment(
        prescription_id=prescription_id,
        patient_id=patient_id,
        actor=actor,
        patient_lat=arguments.get("patient_lat"),
        patient_lon=arguments.get("patient_lon"),
        city=arguments.get("city"),
        radius_km=float(arguments.get("radius_km", 12)),
        stage_in_db=False,
    )
    return plan


def _pharmacy_stage(actor, arguments):
    from .fulfilment_optimizer import optimize_prescription_fulfilment

    patient_id = _patient_target(actor, arguments, "pharmacy_fulfilment")
    prescription_id = int(arguments.get("prescription_id") or 0)
    if not prescription_id:
        raise ValueError("prescription_id is required to stage fulfilment.")
    return optimize_prescription_fulfilment(
        prescription_id=prescription_id,
        patient_id=patient_id,
        actor=actor,
        patient_lat=arguments.get("patient_lat"),
        patient_lon=arguments.get("patient_lon"),
        city=arguments.get("city"),
        radius_km=float(arguments.get("radius_km", 12)),
        stage_in_db=True,
    )


def _confirm_order(actor, arguments):
    """Bounded confirmation handler; executor still blocks this tool in agent plans."""
    from .order_service import submit_order_from_plan

    if arguments.get("user_confirmed") is not True:
        raise PermissionError("Explicit user confirmation is required before an order can be submitted.")
    return submit_order_from_plan(
        plan_id=int(arguments.get("plan_id") or 0),
        actor=actor,
        user_confirmed=True,
        delivery_address=arguments.get("delivery_address"),
        idempotency_key=arguments.get("idempotency_key"),
        expected_plan_hash=arguments.get("plan_hash"),
    )


def _diagnostic_options(actor, arguments):
    from .diagnostic_service import search_lab_offers

    patient_id = _patient_target(actor, arguments, "find_lab_tests")
    test = arguments.get("test_code") or arguments.get("test_id") or arguments.get("query")
    if test in (None, ""):
        raise ValueError("test_code or test_id is required for diagnostic search.")
    offers = search_lab_offers(
        test,
        city=arguments.get("city"),
        user_lat=arguments.get("patient_lat"),
        user_lon=arguments.get("patient_lon"),
    )
    return {
        "status": "OK" if offers else "NO_RESULTS",
        "message": ("Verified diagnostic offers found." if offers else "No verified lab offer is currently available for this test."),
        "patient_id": patient_id,
        "offers": offers,
    }


def _unified_inbox(actor, arguments):
    from .care_graph import get_patient_care_graph

    patient_id = _patient_target(actor, arguments, "care_graph_view")
    return {"status": "OK", "patient_id": patient_id, "care_graph": get_patient_care_graph(patient_id, actor=actor)}


TOOL_HANDLERS = {
    "get_platform_summary": _platform_summary,
    "get_failed_operations": _failed_operations,
    "find_contact": _find_contact,
    "get_unread_summary": _unread_summary,
    "search_educational_video": _educational_video,
    "get_iot_devices": _iot_devices,
    "run_proactive_alert_check": _alert_check,
    "search_nearby_pharmacy_inventory": _pharmacy_search,
    "compare_prescription_fulfilment": _pharmacy_compare,
    "stage_fulfilment_plan": _pharmacy_stage,
    "confirm_and_execute_order": _confirm_order,
    "get_diagnostic_options": _diagnostic_options,
    "get_unified_healthcare_inbox": _unified_inbox,
}
