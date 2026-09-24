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
        if not tool:
            raise LookupError(f"Tool '{step.tool_name}' is not registered.")
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
    if "pharmacy" in lower or "medical store" in lower or "chemist" in lower:
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


def _provider_booking_options(actor, arguments):
    """Read connected provider-published slots; never invent external availability."""
    from .provider_service import available_slots, get_public_provider_profile

    try:
        provider_profile_id = int(arguments.get("provider_profile_id") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("provider_profile_id is required for booking options.") from exc
    date_text = str(arguments.get("date") or "").strip()[:10]
    if not provider_profile_id or not date_text:
        raise ValueError("provider_profile_id and date are required for booking options.")

    profile = get_public_provider_profile(provider_profile_id)
    if not profile:
        raise PermissionError("Only an active, ZENDOC-verified connected provider can expose in-app booking options.")
    slots = available_slots(provider_profile_id, date_text)
    return {
        "status": "OK",
        "provider_profile_id": provider_profile_id,
        "provider_name": profile.get("organization") or profile.get("provider_name"),
        "specialty": profile.get("specialty") or "",
        "date": date_text,
        "available_slots": slots,
        "bookable_in_zendoc": True,
        "confirmation_required": True,
        "truth_notice": (
            "These slots come from the verified ZENDOC provider's published schedule and current appointment/hold state. "
            "No appointment has been created yet."
        ),
    }


def _confirm_provider_booking(actor, arguments):
    """Human-gated handler. execute_plan blocks this consent-required tool."""
    from .provider_service import book_provider_slot

    if arguments.get("user_confirmed") is not True:
        raise PermissionError("Fresh explicit user confirmation is required before booking a provider slot.")
    if str(_value(actor, "role", "")) != "patient":
        raise PermissionError("Only the authenticated patient can confirm an appointment booking.")
    provider_profile_id = int(arguments.get("provider_profile_id") or 0)
    scheduled_for = str(arguments.get("scheduled_for") or "").strip()[:32]
    reason = str(arguments.get("reason") or "Appointment request").strip()[:500]
    if not provider_profile_id or not scheduled_for:
        raise ValueError("provider_profile_id and scheduled_for are required.")
    appointment_id = book_provider_slot(actor, provider_profile_id, scheduled_for, reason)
    return {
        "status": "REQUESTED",
        "appointment_id": appointment_id,
        "provider_profile_id": provider_profile_id,
        "scheduled_for": scheduled_for,
        "payment_executed": False,
    }


def _health_product_search(actor, arguments):
    from .health_commerce import search_health_products

    return search_health_products(
        arguments.get("query"),
        category=arguments.get("category") or "general_wellness",
    )


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
    return optimize_prescription_fulfilment(
        prescription_id=prescription_id,
        patient_id=patient_id,
        actor=actor,
        patient_lat=arguments.get("patient_lat"),
        patient_lon=arguments.get("patient_lon"),
        city=arguments.get("city"),
        radius_km=float(arguments.get("radius_km", 12)),
        stage_in_db=False,
    )


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
    from .context_engine import build_minimum_context_bundle, verify_context_authorization
    from .health_memory_continuity import determine_next_safe_actions, get_health_memory_provenance_summary

    patient_id = _patient_target(actor, arguments, "health_memory_view")
    bundle = build_minimum_context_bundle(
        actor=actor,
        patient_id=patient_id,
        purpose="health_memory_view",
        action="core_agent_health_memory_review",
        requested_fields=["patient_name", "city", "allergies"],
    )

    next_safe_actions = []
    next_safe_actions_authorized = False
    try:
        verify_context_authorization(actor, patient_id, "next_safe_action")
        next_safe_actions = determine_next_safe_actions(patient_id, actor=actor)
        next_safe_actions_authorized = True
    except PermissionError:
        pass

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
        "next_safe_actions": next_safe_actions,
        "next_safe_actions_authorized": next_safe_actions_authorized,
        "safety_notice": (
            "Read-only continuity support. This does not diagnose, prescribe, change treatment, "
            "or bypass patient consent. Proactive next-safe actions are included only when separately authorized."
        ),
    }


def _fitness_snapshot(actor, arguments):
    from .fitness_analytics import get_fitness_progress
    from .fitness_profile import get_fitness_profile
    from .workout_engine import get_latest_plan

    profile = get_fitness_profile(actor)
    return {
        "status": "OK",
        "profile": profile,
        "latest_plan": get_latest_plan(actor),
        "progress_30d": get_fitness_progress(actor, period="30d"),
        "truth_notice": (
            "General-wellness fitness context only. ZENDOC does not turn this snapshot into diagnosis, "
            "treatment or clinical exercise clearance."
        ),
    }


def _generate_fitness_plan(actor, arguments):
    from .fitness_profile import get_fitness_profile
    from .workout_engine import create_plan

    profile = get_fitness_profile(actor)
    if not profile.get("fitness_goal"):
        raise ValueError("Set a fitness goal in the fitness profile before automatic plan generation.")
    if profile.get("limitations"):
        return {
            "status": "REVIEW_RECOMMENDED",
            "plan_created": False,
            "reason": (
                "The fitness profile contains declared limitations. Review them with an appropriate "
                "professional before generating a new automated workout plan."
            ),
        }
    plan = create_plan(
        actor,
        label=str(arguments.get("label") or "").strip()[:120] or None,
        fitness_profile=profile,
    )
    return {
        "status": "CREATED",
        "plan_created": True,
        "plan": plan,
        "truth_notice": "General-wellness workout plan only; not a medical exercise prescription.",
    }


def _family_care_snapshot(actor, arguments):
    from .family_care import list_care_tasks, list_family_access_grants, list_family_members

    return {
        "status": "OK",
        "family_members": list_family_members(actor),
        "care_tasks": list_care_tasks(actor, status=arguments.get("status")),
        "access_given": list_family_access_grants(actor, direction="given"),
        "access_received": list_family_access_grants(actor, direction="received"),
        "truth_notice": (
            "Only relationships, tasks and grants visible to the authenticated actor are returned. "
            "This tool cannot create or expand consent."
        ),
    }


def _home_health_options(actor, arguments):
    from .home_health import list_home_health_requests, list_home_health_services

    return {
        "status": "OK",
        "services": list_home_health_services(),
        "requests": list_home_health_requests(actor),
        "request_confirmation_required": True,
        "truth_notice": (
            "Service categories and recorded request states are shown without claiming live provider availability, "
            "price, assignment or fulfilment."
        ),
    }


def _confirm_home_health_request(actor, arguments):
    from .home_health import create_home_health_request

    if arguments.get("user_confirmed") is not True:
        raise PermissionError("Fresh explicit user confirmation is required before creating a home-health request.")
    result = create_home_health_request(actor, arguments)
    result["payment_executed"] = False
    result["user_confirmed"] = True
    return result


def _transport_options(actor, arguments):
    from .medical_transport import list_transport_requests, list_transport_types

    return {
        "status": "OK",
        "transport_types": list_transport_types(),
        "requests": list_transport_requests(actor),
        "request_confirmation_required": True,
        "dispatch_executed": False,
        "truth_notice": (
            "Transport categories and recorded request states are shown without claiming dispatch, vehicle, ETA, "
            "price or provider acceptance. Emergencies must use the deterministic emergency guidance path."
        ),
    }


def _confirm_transport_request(actor, arguments):
    from .medical_transport import create_transport_request

    if arguments.get("user_confirmed") is not True:
        raise PermissionError("Fresh explicit user confirmation is required before recording a transport request.")
    result = create_transport_request(actor, arguments)
    result["payment_executed"] = False
    result["user_confirmed"] = True
    return result


def _search_health_memory_evidence(actor, arguments):
    from .health_memory_rag import search_health_memory_evidence

    patient_id = _patient_target(actor, arguments, "health_memory_view")
    return search_health_memory_evidence(
        actor,
        str(arguments.get("query") or "")[:500],
        patient_id=patient_id,
        limit=arguments.get("limit", 5),
    )


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
    "get_provider_booking_options": _provider_booking_options,
    "confirm_provider_booking": _confirm_provider_booking,
    "search_health_products": _health_product_search,
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
    "search_health_memory_evidence": _search_health_memory_evidence,
    "get_fitness_snapshot": _fitness_snapshot,
    "generate_fitness_plan": _generate_fitness_plan,
    "get_family_care_snapshot": _family_care_snapshot,
    "get_home_health_options": _home_health_options,
    "confirm_home_health_request": _confirm_home_health_request,
    "get_transport_options": _transport_options,
    "confirm_transport_request": _confirm_transport_request,
}
