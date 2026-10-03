"""Role-scoped personal coordinator agents for ZENDOC Agent OS.

A personal agent is not a new permission boundary and never owns unrestricted
tools. It is a stable coordinator identity for the authenticated actor that
delegates to the existing specialist-agent registry. Every delegated tool call
is still checked by the normal server-side authorization, consent, approval,
truth and audit layers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .agent_registry import AGENT_REGISTRY, choose_agent_for_intent
from .tool_registry import CRITICAL_BLOCKED, get_tool


@dataclass(frozen=True)
class PersonalAgentRole:
    role: str
    display_name: str
    mission: str
    domains: tuple[str, ...]
    memory_scope: tuple[str, ...]
    primary_delegates: tuple[str, ...]
    proactive_capabilities: tuple[str, ...]
    forbidden: tuple[str, ...]

    def to_dict(self) -> dict:
        data = asdict(self)
        for key in (
            "domains",
            "memory_scope",
            "primary_delegates",
            "proactive_capabilities",
            "forbidden",
        ):
            data[key] = list(data[key])
        return data


ROLE_PERSONAL_AGENTS: dict[str, PersonalAgentRole] = {
    "patient": PersonalAgentRole(
        role="patient",
        display_name="My ZENDOC Personal Care Agent",
        mission="Coordinate the patient's permitted care, health memory, discovery, booking, wellness, family and support workflows.",
        domains=(
            "care", "health_memory", "find_care", "booking", "diagnostics", "pharmacy",
            "family", "fitness", "iot", "carefin", "home_health", "transport",
            "communications", "learning", "health_commerce", "referral", "interoperability",
        ),
        memory_scope=(
            "authenticated_user_owned_data",
            "explicit_family_or_caregiver_grants",
            "minimum_necessary_health_memory",
            "provenance_preserved",
        ),
        primary_delegates=(
            "SafetyAgent", "CareAgent", "HealthMemoryAgent", "ProviderDiscoveryAgent",
            "BookingAgent", "DiagnosticsAgent", "PharmacyAgent", "FamilyCareAgent",
            "FitnessAgent", "IoTAgent", "CareFinAgent", "HomeHealthAgent",
            "TransportAgent", "CommunicationAgent", "LearningAgent", "ReferralAgent", "InteroperabilityAgent",
        ),
        proactive_capabilities=(
            "safe_reminders", "care_followup_candidates", "integration_status_explanation",
            "authorized_health_memory_summaries", "reversible_search_and_comparison",
        ),
        forbidden=(
            "diagnose", "prescribe", "change_medication", "dispatch_emergency",
            "execute_payment", "expand_permissions", "access_other_users_without_grant",
        ),
    ),
    "doctor": PersonalAgentRole(
        role="doctor",
        display_name="My ZENDOC Clinical Workflow Agent",
        mission="Coordinate permitted provider workflows while preserving clinician authority and patient consent.",
        domains=("care", "appointments", "diagnostics", "communications", "health_memory", "prevention", "home_health", "transport", "referral", "interoperability"),
        memory_scope=("provider_owned_operational_data", "explicit_patient_authorization", "minimum_necessary_health_context"),
        primary_delegates=("SafetyAgent", "CareAgent", "DoctorAgent", "DiagnosticsAgent", "CommunicationAgent", "HealthMemoryAgent", "PreventionAgent", "HomeHealthAgent", "TransportAgent", "ReferralAgent", "InteroperabilityAgent"),
        proactive_capabilities=("queue_summaries", "followup_candidates", "authorized_context_retrieval", "safe_message_preparation"),
        forbidden=("override_patient_consent", "cross_patient_access", "autonomous_prescribing", "autonomous_emergency_dispatch", "execute_payment"),
    ),
    "hospital": PersonalAgentRole(
        role="hospital",
        display_name="My ZENDOC Hospital Operations Agent",
        mission="Coordinate hospital-side care, appointment, communication and permitted patient-context workflows.",
        domains=("care", "appointments", "diagnostics", "communications", "transport", "health_memory", "referral", "interoperability"),
        memory_scope=("organization_operational_data", "explicit_patient_authorization", "minimum_necessary_health_context"),
        primary_delegates=("SafetyAgent", "CareAgent", "DoctorAgent", "DiagnosticsAgent", "CommunicationAgent", "TransportAgent", "HealthMemoryAgent", "ReferralAgent", "InteroperabilityAgent"),
        proactive_capabilities=("operational_queue_summaries", "care_coordination_candidates", "integration_status_explanation"),
        forbidden=("cross_patient_access", "override_consent", "fabricate_capacity", "autonomous_clinical_decision", "execute_payment"),
    ),
    "pharmacy": PersonalAgentRole(
        role="pharmacy",
        display_name="My ZENDOC Pharmacy Operations Agent",
        mission="Coordinate permitted pharmacy communication and fulfilment workflows without changing prescriptions.",
        domains=("pharmacy", "medication_safety", "communications", "care", "interoperability"),
        memory_scope=("pharmacy_operational_data", "minimum_order_context", "consented_record_access_only"),
        primary_delegates=("SafetyAgent", "MedicationSafetyAgent", "CommunicationAgent", "CareAgent", "InteroperabilityAgent"),
        proactive_capabilities=("order_queue_summaries", "prescription_review_candidates", "safe_customer_communication"),
        forbidden=("prescribe", "substitute_medicine", "change_dose", "access_unrelated_health_records", "execute_payment"),
    ),
    "government": PersonalAgentRole(
        role="government",
        display_name="My ZENDOC Public Health Coordination Agent",
        mission="Coordinate permitted public-health discovery and aggregate operational workflows without exposing private patient data.",
        domains=("provider_discovery", "carefin", "public_health", "search", "learning", "interoperability"),
        memory_scope=("authorized_aggregate_data", "public_official_sources", "no_patient_level_access_without_legal_authority"),
        primary_delegates=("SafetyAgent", "ProviderDiscoveryAgent", "CareFinAgent", "SearchAgent", "LearningAgent", "InteroperabilityAgent"),
        proactive_capabilities=("public_source_discovery", "aggregate_source_freshness", "scheme_and_facility_research"),
        forbidden=("private_patient_surveillance", "cross_user_health_access", "fabricate_statistics", "execute_payment"),
    ),
    "admin": PersonalAgentRole(
        role="admin",
        display_name="My ZENDOC Founder / Owner Agent",
        mission="Coordinate the platform, product, reliability, integrations and bounded AI workforce for the configured owner.",
        domains=("operations", "reliability", "integrations", "product", "research", "release", "interoperability", "all_registered_specialists"),
        memory_scope=("operational_metadata", "audited_platform_events", "minimum_necessary_support_context", "no_blanket_private_clinical_chat_access"),
        primary_delegates=("SafetyAgent", "OperationsAgent", "ModelImprovementAgent", "ProviderDiscoveryAgent", "CareFinAgent", "SearchAgent", "InteroperabilityAgent"),
        proactive_capabilities=("incident_intake", "safe_retry", "integration_probes", "data_refresh", "daily_digest", "release_evidence_preparation"),
        forbidden=("silent_permission_expansion", "read_payment_secrets", "autonomous_prescribing", "autonomous_emergency_dispatch", "unreviewed_production_self_modification"),
    ),
}


def _value(actor: Any, key: str, default=None):
    if actor is None:
        return default
    if hasattr(actor, "keys") and key in actor.keys():
        return actor[key]
    return actor.get(key, default) if isinstance(actor, dict) else default


def _role(actor: Any) -> str:
    return str(_value(actor, "role", "") or "").strip().lower()


def _actor_id(actor: Any) -> int:
    return int(_value(actor, "id", 0) or 0)


def personal_agent_manifest() -> dict:
    return {
        "version": "personal-agent-v1",
        "roles": {role: profile.to_dict() for role, profile in ROLE_PERSONAL_AGENTS.items()},
        "permission_rule": "Personal-agent metadata never grants permissions; specialist tools re-check actor authorization server-side.",
        "memory_rule": "Personal agents use only actor-owned or explicitly authorized minimum-necessary context with provenance.",
    }


def personal_agent_snapshot(actor: Any) -> dict:
    role = _role(actor)
    actor_id = _actor_id(actor)
    if actor_id <= 0 or role not in ROLE_PERSONAL_AGENTS:
        raise PermissionError("An authenticated supported ZENDOC role is required for a personal agent.")

    profile = ROLE_PERSONAL_AGENTS[role]
    delegates = []
    for definition in AGENT_REGISTRY.values():
        if role not in definition.allowed_actor_roles or definition.status == "disabled":
            continue
        delegates.append({
            "identifier": definition.identifier,
            "name": definition.name,
            "status": definition.status,
            "risk_level": definition.risk_level,
        })

    return {
        "personal_agent_id": f"zendoc-personal:{role}:{actor_id}",
        "actor_id": actor_id,
        "role": role,
        "display_name": profile.display_name,
        "mission": profile.mission,
        "domains": list(profile.domains),
        "memory_scope": list(profile.memory_scope),
        "primary_delegates": list(profile.primary_delegates),
        "available_delegates": delegates,
        "proactive_capabilities": list(profile.proactive_capabilities),
        "forbidden": list(profile.forbidden),
        "permission_expansion": False,
        "raw_secret_access": False,
        "notice": "This coordinator can delegate only to specialists already permitted for this actor. Execution re-checks authorization, consent and approvals.",
    }


def route_personal_agent(actor: Any, intent: str) -> dict:
    snapshot = personal_agent_snapshot(actor)
    role = snapshot["role"]
    specialist = choose_agent_for_intent(str(intent or "").strip())
    if specialist is None or role not in specialist.allowed_actor_roles or specialist.status == "disabled":
        specialist = AGENT_REGISTRY.get("SearchAgent")
    if specialist is None or role not in specialist.allowed_actor_roles:
        raise PermissionError("No permitted specialist is available for this request.")

    allowed_tools = []
    for tool_name in specialist.allowed_tools:
        tool = get_tool(tool_name)
        if not tool or tool.risk_class == CRITICAL_BLOCKED or role not in tool.allowed_roles:
            continue
        allowed_tools.append(tool_name)

    return {
        "personal_agent_id": snapshot["personal_agent_id"],
        "intent": str(intent or "").strip(),
        "delegated_agent": specialist.identifier,
        "delegated_agent_name": specialist.name,
        "risk_level": specialist.risk_level,
        "candidate_tools": allowed_tools,
        "approval_requirements": list(specialist.approval_requirements),
        "permission_expansion": False,
        "notice": "Candidate tools are metadata only. Every invocation is checked again by the Tool Registry and domain service.",
    }
