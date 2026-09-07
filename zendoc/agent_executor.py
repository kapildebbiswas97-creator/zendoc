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


def _safe_operations_automation(actor, arguments):
    from .operations_automation import run_safe_operations_automation
    return run_safe_operations_automation(
        actor,
        retry_limit=int(arguments.get("retry_limit") or 10),
    )




def _patient_target(actor, arguments, purpose):
    """Resolve and authorize a patient target for a read/stage tool."""
    from .context_engine import verify_context_authorization

    actor_id = int(_value(actor, "id", 0) or 0)
    patient_id = int(arguments.get("patient_id") or actor_id)
    verify_context_authorization(actor, patient_id, purpose)
    return patient_id



def _provider_discovery(actor, arguments):
    from .healthcare_finder import HealthcareFinder, normalize_query
    from .provider_service import SPECIALTIES

    query = str(arguments.get("query") or "")[:500]
    lower = query.lower()
    if "pharmacy" in lower:
        category = "pharmacy"
    elif any(term in lower for term in ("diagnostic", "laboratory", " lab ")):
        category = "diagnostic_centre"
    elif "clinic" in lower:
        category = "clinic"
    elif "hospital" in lower:
        category = "hospital"
    else:
        category = "doctor"

    specialty = ""
    for item in SPECIALTIES:
        if item.lower() in lower:
            specialty = item
            break

    location = str(arguments.get("location") or _value(actor, "city", "") or "").strip()
    if not location and " in " in lower:
        location = query.rsplit(" in ", 1)[-1].strip()[:100]

    normalized = normalize_query(
        category=category,
        specialty=specialty,
        location=location,
        latitude=arguments.get("latitude"),
        longitude=arguments.get("longitude"),
        radius_km=arguments.get("radius_km", 10),
    )
    result = HealthcareFinder().search(normalized)
    result["source_state_notice"] = (
        "ZENDOC provider verification and external place discovery are separate. "
        "External results do not imply credentials, live appointments, emergency readiness, or ZENDOC booking connectivity."
    )
    return result


def _latest_prescription_review(actor, arguments):
    from .db import get_db
    from .prescription_intelligence import prescription_intelligence_state

    patient_id = _patient_target(actor, arguments, "prescription_view")
    row = get_db().execute(
        "SELECT id FROM prescriptions WHERE patient_id=? ORDER BY issue_date DESC, id DESC LIMIT 1",
        (patient_id,),
    ).fetchone()
    if not row:
        return {
            "status": "NO_PRESCRIPTION",
            "patient_id": patient_id,
            "needs_review": False,
            "fulfilment_ready": False,
            "items": [],
        }

    projected = prescription_intelligence_state(int(row["id"]), actor=actor)
    return {
        "status": projected["overall_stage"],
        "patient_id": patient_id,
        **projected,
        "safety_notice": "Read-only review. No medicine substitution, dose/frequency/form change, prescribing, or order submission occurred.",
    }


def _nutrition_compare(actor, arguments):
    from .nutrition_agent import compare_products

    products = arguments.get("products") or []
    if not isinstance(products, list):
        raise ValueError("products must be a list.")
    return compare_products(
        products,
        goal=str(arguments.get("goal") or "general_wellness")[:100],
        allergens=arguments.get("allergens") or [],
    )


def _carefin_discovery(actor, arguments):
    from .carefin_engine import discover_benefits

    query = str(arguments.get("query") or "")[:1000]
    lower = query.lower()
    actor_city = str(_value(actor, "city", "") or "").strip()
    actor_age = _value(actor, "age", None)

    state = None
    if "west bengal" in lower or " westbengal" in lower or " wb " in f" {lower} ":
        state = "West Bengal"

    desired_categories = []
    if "insurance" in lower or "policy" in lower:
        desired_categories.extend(["life_insurance", "government_health_assurance"])
    if any(term in lower for term in ("csr", "charity", "trust", "ngo", "financial help", "medical funding")):
        desired_categories.extend(["csr", "charitable_support", "health_welfare"])
    if "government" in lower or "scheme" in lower:
        desired_categories.extend(["government_scheme", "government_health_assurance", "state_health_scheme"])

    return discover_benefits({
        "geography": state or "INDIA",
        "state": state,
        "district": actor_city or None,
        "age": actor_age,
        "existing_insurer": "LIC" if "lic" in lower else None,
        "needs_charitable_support": any(
            term in lower for term in ("csr", "charity", "trust", "ngo", "financial help", "medical funding")
        ),
        "desired_categories": desired_categories,
    })

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
    confirmed = [item for item in offers if item.get("availability_state") == "CONFIRMED"]
    if confirmed:
        status = "OK"
        message = "Confirmed-fresh diagnostic offers found."
    elif offers:
        status = "STALE_ONLY"
        message = "Only stale diagnostic offers were found; refresh provider availability before booking."
    else:
        status = "UNKNOWN"
        message = "No current verified diagnostic offer is known for this test; availability is unknown, not confirmed unavailable."
    return {
        "status": status,
        "message": message,
        "patient_id": patient_id,
        "offers": offers,
    }


def _unified_inbox(actor, arguments):
    from .care_graph import get_patient_care_graph

    patient_id = _patient_target(actor, arguments, "care_graph_view")
    return {"status": "OK", "patient_id": patient_id, "care_graph": get_patient_care_graph(patient_id, actor=actor)}


def _health_memory_context(actor, arguments):
    from .context_engine import build_minimum_context_bundle
    from .health_memory_continuity import determine_next_safe_actions, get_health_memory_provenance_summary

    patient_id = _patient_target(actor, arguments, "health_memory_view")
    bundle = build_minimum_context_bundle(
        actor=actor,
        patient_id=patient_id,
        purpose="health_memory_view",
        action="core_agent_health_memory_review",
        requested_fields=["patient_name", "city", "allergies"],
    )
    return {
        "status": "OK",
        "patient_id": patient_id,
        "context_contract": {
            "consent_status": bundle.consent_status,
            "included_fields": bundle.included_fields,
            "excluded_fields": bundle.excluded_fields,
            "data": bundle.data,
            "provenance": bundle.provenance,
            "created_at": bundle.created_at,
        },
        "health_memory": get_health_memory_provenance_summary(patient_id, actor=actor),
        "next_safe_actions": determine_next_safe_actions(patient_id, actor=actor),
        "safety_notice": (
            "Read-only continuity support. This does not diagnose, prescribe, change treatment, "
            "or bypass patient consent."
        ),
    }


TOOL_HANDLERS = {
    "get_platform_summary": _platform_summary,
    "get_failed_operations": _failed_operations,
    "find_contact": _find_contact,
    "get_unread_summary": _unread_summary,
    "search_educational_video": _educational_video,
    "get_iot_devices": _iot_devices,
    "run_proactive_alert_check": _alert_check,
    "run_safe_operations_automation": _safe_operations_automation,
    "search_healthcare_providers": _provider_discovery,
    "get_latest_prescription_review": _latest_prescription_review,
    "compare_nutrition_products": _nutrition_compare,
    "discover_carefin_benefits": _carefin_discovery,
    "search_nearby_pharmacy_inventory": _pharmacy_search,
    "compare_prescription_fulfilment": _pharmacy_compare,
    "stage_fulfilment_plan": _pharmacy_stage,
    "confirm_and_execute_order": _confirm_order,
    "get_diagnostic_options": _diagnostic_options,
    "get_unified_healthcare_inbox": _unified_inbox,
    "get_health_memory_context": _health_memory_context,
}
