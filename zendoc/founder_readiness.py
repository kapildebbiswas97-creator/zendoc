"""Owner-only founder readiness aggregation for demos and fundraising.

This module deliberately avoids a single percentage score. Demo runtime,
pilot/deployment readiness and observed fundraising evidence are different
truth domains and must remain separate.
"""
from __future__ import annotations

from typing import Any

from flask import current_app

from .db import now_iso
from .edgecare_asr import get_edgecare_asr
from .investor_dashboard import investor_traction_snapshot
from .launch_readiness import first50_launch_readiness, public_launch_readiness, software_completion_readiness
from .model_router import get_model_router
from .security import assert_owner


VIRTUAL_DEMO_ROUTES = (
    "/showcase",
    "/finder",
    "/appointments",
    "/agent-os",
    "/ai",
    "/health-hub",
    "/records",
    "/messages",
    "/admin/edgecare",
    "/admin/startup",
)

EVIDENCE_LABELS = {
    "product_usage_observed": "Observed product usage",
    "d7_retention_measurable": "D7 retention measurable",
    "d30_retention_measurable": "D30 retention measurable",
    "provider_network_observed": "Real provider-network evidence",
    "institution_demand_observed": "Institution/pilot demand evidence",
    "paid_revenue_recorded": "Paid revenue recorded",
    "cash_runway_measurable": "Cash/runway measurable",
    "india_coverage_observed": "Imported India coverage evidence",
    "patient_activation_measurable": "Patient activation measurable",
    "appointment_request_observed": "Appointment-request usage observed",
}


def _bounded_days(value: Any) -> int:
    try:
        return max(1, min(int(value or 30), 365))
    except (TypeError, ValueError):
        return 30


def _demo_route_contract() -> dict:
    registered = {str(rule.rule) for rule in current_app.url_map.iter_rules()}
    missing = [path for path in VIRTUAL_DEMO_ROUTES if path not in registered]
    return {
        "required": list(VIRTUAL_DEMO_ROUTES),
        "registered_count": len(VIRTUAL_DEMO_ROUTES) - len(missing),
        "missing": missing,
        "contract_present": not missing,
        "truth_notice": (
            "Route registration proves only that the expected demo endpoints exist in this application build. "
            "HTTP 200 behavior is verified separately by automated route smoke tests and the real demo machine."
        ),
    }


def _funding_evidence(readiness: dict) -> dict:
    present = []
    missing = []
    for key, label in EVIDENCE_LABELS.items():
        item = {"key": key, "label": label}
        if bool(readiness.get(key)):
            present.append(item)
        else:
            missing.append(item)

    if not present:
        status = "EARLY_EVIDENCE_COLLECTION"
    elif missing:
        status = "PARTIAL_OBSERVED_EVIDENCE"
    else:
        status = "OBSERVED_EVIDENCE_PRESENT"

    return {
        "status": status,
        "present": present,
        "missing": missing,
        "present_count": len(present),
        "required_signal_count": len(EVIDENCE_LABELS),
        "truth_notice": (
            "These are evidence-presence signals, not an investment score, valuation, fundraising probability "
            "or claim that ZENDOC is fundable. Missing evidence remains missing."
        ),
    }


def founder_readiness_snapshot(
    actor: Any,
    *,
    check_runtime: bool = True,
    days: Any = 30,
    finance_month: str | None = None,
) -> dict:
    """Return a truthful founder pre-call snapshot from existing evidence."""
    assert_owner(actor)
    window_days = _bounded_days(days)

    software = software_completion_readiness()
    launch = first50_launch_readiness()
    public_launch = public_launch_readiness()
    investor = investor_traction_snapshot(
        actor,
        days=window_days,
        finance_month=finance_month,
    )
    router = get_model_router().status(check_health=bool(check_runtime))
    local_ai = dict(router.get("local_ai") or {})
    local_asr = dict(get_edgecare_asr().status(check_health=bool(check_runtime)))
    routes = _demo_route_contract()

    local_ai_ready = local_ai.get("status") == "ready"
    local_asr_ready = local_asr.get("status") == "ready"

    if not routes["contract_present"]:
        meeting_mode = "FIX_SOFTWARE_BEFORE_CALL"
        meeting_note = "One or more required virtual-demo routes are missing from this application build."
    elif local_ai_ready and local_asr_ready:
        meeting_mode = "LIVE_LOCAL_DEMO_MODE"
        meeting_note = "The expected demo routes are registered and both configured local runtimes report ready."
    else:
        meeting_mode = "SAFE_FALLBACK_DEMO_MODE"
        meeting_note = (
            "The expected demo routes are registered, but one or both local runtimes are not ready. "
            "Use typed input and deterministic fallback; do not present unavailable local runtime behavior as live."
        )

    return {
        "generated_at": now_iso(),
        "window_days": window_days,
        "meeting_mode": meeting_mode,
        "meeting_note": meeting_note,
        "demo": {
            "route_contract": routes,
            "local_ai": local_ai,
            "local_asr": local_asr,
            "local_ai_ready": local_ai_ready,
            "local_asr_ready": local_asr_ready,
            "typed_input_fallback_available": True,
            "deterministic_safety_fallback_available": True,
            "runtime_health_checked": bool(check_runtime),
        },
        "software": software,
        "pilot": launch,
        "public_launch": public_launch,
        "funding": _funding_evidence(investor.get("readiness") or {}),
        "investor_snapshot": investor,
        "claims": {
            "synthetic_demo_fixture_counts_as_traction": False,
            "runtime_configuration_proves_snapdragon_npu": False,
            "software_implementation_proves_provider_fulfilment": False,
            "missing_funding_evidence_becomes_zero_or_unknown_not_success": True,
        },
        "truth_notice": (
            "Founder Readiness keeps software/demo readiness, pilot readiness and fundraising evidence separate. "
            "It does not predict selection, investment, valuation, clinical success or regulatory approval."
        ),
    }
