"""Evidence-bound investor traction snapshot for ZENDOC."""
from __future__ import annotations

from typing import Any

from .business_api import business_api_metrics
from .institution_pilots import institution_pilot_metrics
from .security import assert_owner
from .startup_analytics import (
    care_journey_conversion,
    india_coverage_quality,
    provider_onboarding_funnel,
    retention_metrics,
    startup_metrics,
)
from .startup_finance import financial_kpis


def investor_traction_snapshot(actor: Any, *, days: int = 30, finance_month: str | None = None) -> dict:
    assert_owner(actor)

    product = startup_metrics(actor, days=days)
    retention = retention_metrics(actor)
    care = care_journey_conversion(actor, days=days)
    providers = provider_onboarding_funnel(actor, days=90)
    pilots = institution_pilot_metrics(actor)
    business_api = business_api_metrics(actor)
    coverage = india_coverage_quality(actor)
    finance = financial_kpis(actor, month=finance_month)

    provider_stage = {item["stage"]: item for item in providers["stages"]}
    care_stage = {item["stage"]: item for item in care["stages"]}

    evidence = {
        "product": {
            "healthcare_searches": product["healthcare_searches"],
            "useful_result_rate": product["useful_result_rate"],
            "feedback_response_count": product["feedback_response_count"],
            "helpful_feedback_rate": product["helpful_feedback_rate"],
            "active_search_users": product["active_search_users"],
        },
        "retention": {
            "d7_eligible_users": retention["d7"]["eligible_users"],
            "d7_retention_rate": retention["d7"]["retention_rate"],
            "d30_eligible_users": retention["d30"]["eligible_users"],
            "d30_retention_rate": retention["d30"]["retention_rate"],
        },
        "care": {
            "started_journeys": care["started_journeys"],
            "completed_journeys": care_stage.get("completed", {}).get("journey_count", 0),
            "completed_conversion_rate": care_stage.get("completed", {}).get("conversion_from_started"),
        },
        "providers": {
            "profiles_created": providers["provider_profiles_created"],
            "provider_verified": provider_stage.get("provider_verified", {}).get("provider_count", 0),
            "patient_interaction": provider_stage.get("patient_interaction", {}).get("provider_count", 0),
        },
        "pilots": {
            "pilot_count": pilots["pilot_count"],
            "active_pilots": pilots["active_pilots"],
            "converted_pilots": pilots["converted_pilots"],
            "paid_pilots": pilots["paid_pilots"],
            "conversion_rate": pilots["conversion_rate"],
        },
        "business_api": {
            "client_count": business_api["client_count"],
            "active_clients": business_api["active_clients"],
            "requests_last_30_days": business_api["requests_last_30_days"],
        },
        "coverage": {
            "india_region_targets": coverage["region_target_count"],
            "canonical_state_nodes_loaded": coverage["canonical_state_nodes_loaded"],
            "public_healthcare_entity_count": coverage["public_healthcare_entity_count"],
            "linked_public_healthcare_entities": coverage["public_healthcare_entities_linked_to_canonical_geography"],
        },
        "finance": finance,
    }

    readiness = {
        "product_usage_observed": product["healthcare_searches"] > 0,
        "d7_retention_measurable": retention["d7"]["eligible_users"] > 0,
        "d30_retention_measurable": retention["d30"]["eligible_users"] > 0,
        "provider_network_observed": providers["provider_profiles_created"] > 0,
        "institution_demand_observed": pilots["pilot_count"] > 0,
        "paid_revenue_recorded": finance["revenue_inr"] > 0 or pilots["paid_pilots"] > 0,
        "cash_runway_measurable": finance["cash_balance_inr"] is not None,
        "india_coverage_observed": coverage["canonical_state_nodes_loaded"] > 0,
    }

    return {
        "window_days": days,
        "evidence": evidence,
        "readiness": readiness,
        "truth_notice": (
            "This snapshot contains only observed or owner-entered evidence. Missing metrics remain missing. "
            "It must not be used to claim nationwide completeness, audited financials, clinical validation, "
            "or revenue that has not actually occurred."
        ),
    }
