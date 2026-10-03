"""Enforce Agent OS ownership for every ZENDOC capability.

The capability registry is the product truth source. This module binds every
declared capability to a registered specialist Agent OS owner and, where useful,
an internal AI-workforce owner. A new capability without an explicit mapping is
therefore detectable in CI instead of silently becoming an agent-less feature.

Coverage is responsibility metadata, not permission. Tool execution continues
to pass through the Tool Registry, domain authorization, consent and approval
boundaries.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .agent_registry import get_agent
from .ai_workforce import WORKFORCE
from .capability_registry import get_capability_registry


SPECIALIST_EXECUTABLE = "SPECIALIST_EXECUTABLE"
SPECIALIST_COORDINATION = "SPECIALIST_COORDINATION"
INTEGRATION_COORDINATION = "INTEGRATION_COORDINATION"
OPERATIONS_MONITORED = "OPERATIONS_MONITORED"
SAFETY_GUARDED = "SAFETY_GUARDED"
FUTURE_GUARDED = "FUTURE_GUARDED"

COVERAGE_MODES = {
    SPECIALIST_EXECUTABLE,
    SPECIALIST_COORDINATION,
    INTEGRATION_COORDINATION,
    OPERATIONS_MONITORED,
    SAFETY_GUARDED,
    FUTURE_GUARDED,
}


@dataclass(frozen=True)
class FeatureAgentCoverage:
    capability_key: str
    primary_agent: str
    mode: str
    workforce_owner: str | None = None
    safety_agent: str | None = None
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _c(
    key: str,
    agent: str,
    mode: str,
    *,
    workforce: str | None = None,
    safety: str | None = None,
    note: str = "",
) -> FeatureAgentCoverage:
    return FeatureAgentCoverage(
        capability_key=key,
        primary_agent=agent,
        mode=mode,
        workforce_owner=workforce,
        safety_agent=safety,
        note=note,
    )


FEATURE_AGENT_COVERAGE: dict[str, FeatureAgentCoverage] = {
    # Agent / platform control plane
    "zendoc_core_agent": _c("zendoc_core_agent", "OperationsAgent", SPECIALIST_COORDINATION, workforce="ManagerAgent"),
    "deterministic_safety_engine": _c("deterministic_safety_engine", "SafetyAgent", SAFETY_GUARDED, workforce="SecurityAgent"),
    "local_slm": _c("local_slm", "ModelImprovementAgent", OPERATIONS_MONITORED, workforce="InfrastructureAgent"),
    "slm_product_layer": _c("slm_product_layer", "ModelImprovementAgent", SPECIALIST_COORDINATION, workforce="ProductAgent"),
    "slm_knowledge_layer": _c("slm_knowledge_layer", "ModelImprovementAgent", SPECIALIST_COORDINATION, workforce="KnowledgeAgent"),
    "slm_output_validator": _c("slm_output_validator", "SafetyAgent", SAFETY_GUARDED, workforce="SecurityAgent"),
    "cloud_llm": _c("cloud_llm", "ModelImprovementAgent", INTEGRATION_COORDINATION, workforce="IntegrationAgent"),
    "model_router": _c("model_router", "ModelImprovementAgent", SPECIALIST_COORDINATION, workforce="ManagerAgent"),
    "model_evaluation_lab": _c("model_evaluation_lab", "ModelImprovementAgent", SPECIALIST_EXECUTABLE, workforce="TestAgent"),
    "real_local_model_evaluation": _c("real_local_model_evaluation", "ModelImprovementAgent", INTEGRATION_COORDINATION, workforce="TestAgent"),
    "agent_task_engine": _c("agent_task_engine", "OperationsAgent", OPERATIONS_MONITORED, workforce="ManagerAgent"),
    "approval_engine": _c("approval_engine", "OperationsAgent", SAFETY_GUARDED, workforce="SecurityAgent"),
    "proactive_alerts": _c("proactive_alerts", "OperationsAgent", SPECIALIST_EXECUTABLE, workforce="IncidentAgent"),
    "capability_registry": _c("capability_registry", "OperationsAgent", OPERATIONS_MONITORED, workforce="ProductAgent"),
    "specialized_agent_routing": _c("specialized_agent_routing", "OperationsAgent", SPECIALIST_COORDINATION, workforce="ManagerAgent"),
    "safe_operations_automation": _c("safe_operations_automation", "OperationsAgent", SPECIALIST_EXECUTABLE, workforce="IncidentAgent"),

    # Communication / community / commerce
    "connect_messaging": _c("connect_messaging", "CommunicationAgent", SPECIALIST_EXECUTABLE, workforce="SupportAgent"),
    "health_community": _c("health_community", "CommunicationAgent", SPECIALIST_COORDINATION, workforce="SupportAgent"),
    "community_media_public_durability": _c("community_media_public_durability", "OperationsAgent", INTEGRATION_COORDINATION, workforce="InfrastructureAgent"),
    "health_shop_discovery": _c("health_shop_discovery", "CommerceAgent", SPECIALIST_EXECUTABLE, workforce="ProductAgent"),
    "affiliate_referral_revenue": _c("affiliate_referral_revenue", "CommerceAgent", INTEGRATION_COORDINATION, workforce="IntegrationAgent"),
    "connected_payments_gateway": _c(
        "connected_payments_gateway",
        "CommerceAgent",
        INTEGRATION_COORDINATION,
        workforce="IntegrationAgent",
        safety="SafetyAgent",
        note="Agent may prepare checkout evidence; payment execution remains outside autonomous model authority.",
    ),
    "voice_video_calling": _c("voice_video_calling", "CommunicationAgent", INTEGRATION_COORDINATION, workforce="InfrastructureAgent"),
    "external_notifications": _c("external_notifications", "CommunicationAgent", INTEGRATION_COORDINATION, workforce="CommunicationsAgent"),
    "in_app_notifications": _c("in_app_notifications", "CommunicationAgent", SPECIALIST_EXECUTABLE, workforce="CommunicationsAgent"),
    "realtime": _c("realtime", "CommunicationAgent", OPERATIONS_MONITORED, workforce="InfrastructureAgent"),

    # Care, memory, clinical-adjacent and wellness
    "mental_wellness_private": _c("mental_wellness_private", "CareAgent", SPECIALIST_COORDINATION, workforce="SupportAgent", safety="SafetyAgent"),
    "carefin_engine": _c("carefin_engine", "CareFinAgent", SPECIALIST_EXECUTABLE, workforce="ResearchAgent"),
    "carefin_live_verification": _c("carefin_live_verification", "CareFinAgent", INTEGRATION_COORDINATION, workforce="IntegrationAgent"),
    "automatic_care_journey": _c("automatic_care_journey", "CareAgent", SPECIALIST_EXECUTABLE, workforce="ManagerAgent", safety="SafetyAgent"),
    "diagnostics_freshness_v2": _c("diagnostics_freshness_v2", "DiagnosticsAgent", SPECIALIST_EXECUTABLE, workforce="IntegrationAgent"),
    "nutrition_agent": _c("nutrition_agent", "NutritionAgent", SPECIALIST_EXECUTABLE, workforce="ResearchAgent", safety="SafetyAgent"),
    "health_memory": _c("health_memory", "HealthMemoryAgent", SPECIALIST_EXECUTABLE, workforce="KnowledgeAgent"),
    "medical_records": _c("medical_records", "HealthMemoryAgent", SPECIALIST_COORDINATION, workforce="KnowledgeAgent"),
    "appointments": _c("appointments", "BookingAgent", SPECIALIST_EXECUTABLE, workforce="IntegrationAgent"),
    "telehealth": _c("telehealth", "DoctorAgent", INTEGRATION_COORDINATION, workforce="IntegrationAgent", safety="SafetyAgent"),
    "report_intelligence": _c("report_intelligence", "CareAgent", SPECIALIST_COORDINATION, workforce="ResearchAgent", safety="SafetyAgent"),
    "fitness_coach": _c("fitness_coach", "FitnessAgent", SPECIALIST_EXECUTABLE, workforce="ProductAgent"),
    "pose_coach": _c("pose_coach", "FitnessAgent", SPECIALIST_COORDINATION, workforce="ProductAgent"),
    "fitness_videos": _c("fitness_videos", "VideoAgent", SPECIALIST_EXECUTABLE, workforce="ResearchAgent"),
    "family_care": _c("family_care", "FamilyCareAgent", SPECIALIST_EXECUTABLE, workforce="SupportAgent"),
    "home_health": _c("home_health", "HomeHealthAgent", INTEGRATION_COORDINATION, workforce="IntegrationAgent"),
    "pharmacy": _c("pharmacy", "PharmacyAgent", INTEGRATION_COORDINATION, workforce="IntegrationAgent", safety="SafetyAgent"),
    "medical_transport": _c("medical_transport", "TransportAgent", INTEGRATION_COORDINATION, workforce="IntegrationAgent", safety="SafetyAgent"),
    "iot_hub": _c("iot_hub", "IoTAgent", INTEGRATION_COORDINATION, workforce="IntegrationAgent"),

    # Language, identity, organizations and discovery
    "multilingual_foundation": _c("multilingual_foundation", "LearningAgent", SPECIALIST_COORDINATION, workforce="ProductAgent"),
    "free_form_translation": _c("free_form_translation", "LearningAgent", INTEGRATION_COORDINATION, workforce="IntegrationAgent"),
    "identity_evidence_review": _c("identity_evidence_review", "OperationsAgent", SAFETY_GUARDED, workforce="SecurityAgent"),
    "external_ekyc": _c("external_ekyc", "OperationsAgent", INTEGRATION_COORDINATION, workforce="IntegrationAgent"),
    "provider_onboarding_v1": _c("provider_onboarding_v1", "OperationsAgent", SPECIALIST_COORDINATION, workforce="SupportAgent"),
    "organization_health": _c("organization_health", "CareFinAgent", SPECIALIST_COORDINATION, workforce="ProductAgent"),
    "healthcare_finder": _c("healthcare_finder", "ProviderDiscoveryAgent", SPECIALIST_EXECUTABLE, workforce="DataAgent"),
    "external_places_discovery": _c("external_places_discovery", "ProviderDiscoveryAgent", INTEGRATION_COORDINATION, workforce="IntegrationAgent"),
    "video_intelligence": _c("video_intelligence", "VideoAgent", INTEGRATION_COORDINATION, workforce="ResearchAgent"),

    # Global/public data fabric
    "geographic_healthcare_graph": _c("geographic_healthcare_graph", "ProviderDiscoveryAgent", SPECIALIST_COORDINATION, workforce="DataAgent"),
    "official_public_data_ingestion": _c("official_public_data_ingestion", "OperationsAgent", SPECIALIST_EXECUTABLE, workforce="DataAgent"),
    "official_live_connectors": _c("official_live_connectors", "OperationsAgent", INTEGRATION_COORDINATION, workforce="ResearchAgent"),
    "universal_healthcare_interoperability_gateway": _c(
        "universal_healthcare_interoperability_gateway",
        "InteroperabilityAgent",
        SPECIALIST_COORDINATION,
        workforce="IntegrationAgent",
        safety="SafetyAgent",
        note="Adapter discovery and exchange planning are executable; external exchange remains authorization/consent/live-verification gated.",
    ),
    "live_external_fhir_exchange": _c(
        "live_external_fhir_exchange",
        "InteroperabilityAgent",
        INTEGRATION_COORDINATION,
        workforce="IntegrationAgent",
        safety="SafetyAgent",
        note="Live connectivity is never inferred from software support or environment variables alone.",
    ),
    "global_health_intelligence_fabric": _c("global_health_intelligence_fabric", "OperationsAgent", SPECIALIST_COORDINATION, workforce="ResearchAgent"),
    "organization_intelligence": _c("organization_intelligence", "OperationsAgent", SPECIALIST_COORDINATION, workforce="ResearchAgent"),
    "global_source_research_automation": _c("global_source_research_automation", "OperationsAgent", SPECIALIST_EXECUTABLE, workforce="ResearchAgent"),

    # Pilot / operations
    "carefin_pilot_ui": _c("carefin_pilot_ui", "CareFinAgent", SPECIALIST_EXECUTABLE, workforce="QAAgent"),
    "care_journey_pilot_ui": _c("care_journey_pilot_ui", "CareAgent", SPECIALIST_EXECUTABLE, workforce="QAAgent"),
    "pilot_analytics": _c("pilot_analytics", "OperationsAgent", OPERATIONS_MONITORED, workforce="ProductAgent"),
    "human_operations": _c("human_operations", "OperationsAgent", SPECIALIST_EXECUTABLE, workforce="ManagerAgent"),

    # Infrastructure
    "postgresql": _c("postgresql", "OperationsAgent", OPERATIONS_MONITORED, workforce="InfrastructureAgent"),
    "object_storage": _c("object_storage", "OperationsAgent", INTEGRATION_COORDINATION, workforce="InfrastructureAgent"),

    # Guarded future capabilities
    "zendoc_proprietary_slm": _c("zendoc_proprietary_slm", "ModelImprovementAgent", FUTURE_GUARDED, workforce="ResearchAgent"),
    "autonomous_prescribing": _c(
        "autonomous_prescribing",
        "MedicationSafetyAgent",
        FUTURE_GUARDED,
        workforce="SecurityAgent",
        safety="SafetyAgent",
        note="Remains CRITICAL_BLOCKED; mapping provides safety ownership, not executable authority.",
    ),
}


def feature_agent_coverage_snapshot() -> dict:
    capabilities = get_capability_registry()
    capability_keys = set(capabilities)
    mapped_keys = set(FEATURE_AGENT_COVERAGE)
    workforce_ids = {item.agent_id for item in WORKFORCE}

    missing = sorted(capability_keys - mapped_keys)
    stale = sorted(mapped_keys - capability_keys)
    invalid = []
    items = []

    for key in sorted(capability_keys & mapped_keys):
        coverage = FEATURE_AGENT_COVERAGE[key]
        agent = get_agent(coverage.primary_agent)
        if not agent:
            invalid.append({"capability_key": key, "reason": f"Unknown primary agent {coverage.primary_agent}"})
            continue
        if coverage.mode not in COVERAGE_MODES:
            invalid.append({"capability_key": key, "reason": f"Unknown coverage mode {coverage.mode}"})
        if coverage.workforce_owner and coverage.workforce_owner not in workforce_ids:
            invalid.append({"capability_key": key, "reason": f"Unknown workforce owner {coverage.workforce_owner}"})
        if coverage.safety_agent and not get_agent(coverage.safety_agent):
            invalid.append({"capability_key": key, "reason": f"Unknown safety agent {coverage.safety_agent}"})

        items.append({
            **coverage.to_dict(),
            "capability_status": capabilities[key]["status"],
            "capability_label": capabilities[key]["label"],
            "agent_status": agent.status,
            "actor_roles": list(agent.allowed_actor_roles),
            "agent_tools": list(agent.allowed_tools),
        })

    complete = not missing and not stale and not invalid
    return {
        "complete": complete,
        "covered_count": len(items),
        "capability_count": len(capabilities),
        "missing_capabilities": missing,
        "stale_mappings": stale,
        "invalid_mappings": invalid,
        "items": items,
        "rule": "Every capability must have an explicit Agent OS owner. Mapping responsibility never grants execution permission.",
    }


def assert_complete_agent_coverage() -> None:
    snapshot = feature_agent_coverage_snapshot()
    if not snapshot["complete"]:
        raise RuntimeError(
            "Agent OS capability coverage is incomplete: "
            f"missing={snapshot['missing_capabilities']} "
            f"stale={snapshot['stale_mappings']} "
            f"invalid={snapshot['invalid_mappings']}"
        )
