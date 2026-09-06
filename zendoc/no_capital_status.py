"""Truthful owner-facing no-capital completion report."""
from __future__ import annotations

from .capability_registry import (
    STATUS_BETA,
    STATUS_DISABLED,
    STATUS_FUTURE,
    STATUS_INTEGRATION_REQUIRED,
    STATUS_WORKING,
    get_capability_registry,
)


NO_CAPITAL_CAPABILITY_KEYS = (
    "zendoc_core_agent",
    "deterministic_safety_engine",
    "model_router",
    "agent_task_engine",
    "approval_engine",
    "proactive_alerts",
    "specialized_agent_routing",
    "health_memory",
    "appointments",
    "family_care",
    "connect_messaging",
    "pharmacy",
    "carefin_engine",
    "automatic_care_journey",
    "safe_operations_automation",
    "diagnostics_freshness_v2",
    "nutrition_agent",
    "multilingual_foundation",
    "geographic_healthcare_graph",
    "capability_registry",
)

INTEGRATION_DEPENDENCIES = (
    "carefin_live_verification",
    "cloud_llm",
    "local_slm",
    "free_form_translation",
    "external_notifications",
    "postgresql",
)

PARTNER_DEPENDENCIES = (
    "ABDM / ABHA production onboarding",
    "PM-JAY beneficiary/claims verification",
    "Swasthya Sathi patient-level verification",
    "insurer/LIC policy and claims APIs",
    "real pharmacy inventory/dispensing feeds",
    "real diagnostic provider availability feeds",
    "hospital external booking feeds",
    "live ambulance dispatch",
    "home-health fulfilment providers",
    "device vendor SDK/API access",
    "production telehealth/WebRTC provider",
    "authorized payments/settlement partner",
)

PHYSICAL_CAPITAL_DEPENDENCIES = (
    "medicine inventory",
    "compliant warehouse and cold chain",
    "owned medical/IoT device inventory",
    "delivery fleet and riders",
    "ambulances",
    "diagnostic equipment",
    "clinical facilities",
    "large field/operations workforce",
)


def no_capital_completion_report() -> dict:
    registry = get_capability_registry()
    rows = []
    working = 0
    beta = 0
    incomplete = 0
    for key in NO_CAPITAL_CAPABILITY_KEYS:
        capability = registry.get(key)
        if capability is None:
            status = "MISSING"
            label = key
            incomplete += 1
        else:
            status = capability["status"]
            label = capability["label"]
            if status == STATUS_WORKING:
                working += 1
            elif status == STATUS_BETA:
                beta += 1
            else:
                incomplete += 1
        rows.append({"key": key, "label": label, "status": status})

    total = len(NO_CAPITAL_CAPABILITY_KEYS)
    # "Complete" means currently marked WORKING. Beta is intentionally not
    # counted as complete. This is a software readiness indicator, not company
    # or market readiness.
    completion_percent = round((working / total) * 100, 1) if total else 0.0

    integration = []
    for key in INTEGRATION_DEPENDENCIES:
        item = registry.get(key)
        if item:
            integration.append({
                "key": key,
                "label": item["label"],
                "status": item["status"],
                "description": item["description"],
            })

    return {
        "software_no_capital_scope": {
            "total": total,
            "working": working,
            "beta": beta,
            "incomplete": incomplete,
            "working_percent": completion_percent,
            "measurement_rule": "Only capabilities explicitly marked WORKING count as complete; BETA does not.",
            "capabilities": rows,
        },
        "integration_dependencies": integration,
        "partner_dependencies": list(PARTNER_DEPENDENCIES),
        "physical_capital_dependencies": list(PHYSICAL_CAPITAL_DEPENDENCIES),
        "disclaimer": (
            "This percentage measures the named no-capital software checklist only. "
            "It does not represent regulatory approval, commercial partnerships, clinical validation, product-market fit, or company completion."
        ),
    }
