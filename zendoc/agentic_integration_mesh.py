"""Agentic ownership policy for ZENDOC external integrations.

This module does not pretend that missing third-party credentials, contracts,
provider acceptance or regulated verification can be created by AI. Instead it
makes every integration operationally owned: a specialist agent can observe,
route, retry or degrade safely while deterministic code preserves truth.
"""
from __future__ import annotations


INTEGRATION_POLICIES = {
    "jev_decisions": {
        "owner_agents": ["OperationsAgent", "ModelImprovementAgent"],
        "autonomous_scope": "health-check configuration state, use bounded decisions when configured, fall back safely on outage",
        "fallback_mode": "existing deterministic bounded Agent OS policy",
        "human_gate": "operator supplies and verifies a real Jev credential or approved private runtime",
    },
    "payments": {
        "owner_agents": ["CareAgent", "OperationsAgent"],
        "autonomous_scope": "prepare invoices, reconcile webhook-confirmed state, surface gateway readiness and failures",
        "fallback_mode": "preserve invoice/unpaid state; never fabricate paid status or move money",
        "human_gate": "user authorizes payment and the configured gateway provides cryptographic confirmation",
    },
    "external_ekyc": {
        "owner_agents": ["CareAgent", "OperationsAgent"],
        "autonomous_scope": "collect minimum required workflow state, route verification, track pending/failed provider events",
        "fallback_mode": "manual evidence/review path with identity remaining unverified",
        "human_gate": "authorized identity provider and operator verification",
    },
    "carefin_partner": {
        "owner_agents": ["CareFinAgent"],
        "autonomous_scope": "discover support paths, organize evidence, retry safe lookups and maintain coverage truth states",
        "fallback_mode": "public-source discovery with eligibility/approval marked unconfirmed",
        "human_gate": "authoritative insurer/scheme/partner confirmation",
    },
    "durable_media": {
        "owner_agents": ["HealthMemoryAgent", "OperationsAgent"],
        "autonomous_scope": "choose configured storage adapter, verify capability state, surface save/read/delete failures",
        "fallback_mode": "development/local storage only; public durable-storage claim remains blocked",
        "human_gate": "operator configures and verifies durable object storage",
    },
    "webrtc": {
        "owner_agents": ["CommunicationAgent"],
        "autonomous_scope": "permission checks, call-request signaling, connection-state handling and safe fallback",
        "fallback_mode": "permissioned ZENDOC messaging when public-network calling is unavailable",
        "human_gate": "call participants accept; operator verifies TURN/STUN for public-network reliability",
    },
    "affiliate": {
        "owner_agents": ["CommerceAgent"],
        "autonomous_scope": "product discovery, disclosed outbound attribution and click tracking",
        "fallback_mode": "non-affiliate external handoff with no commission/revenue claim",
        "human_gate": "merchant affiliate approval and real conversion/settlement evidence",
    },
    "maps": {
        "owner_agents": ["ProviderDiscoveryAgent", "SearchAgent"],
        "autonomous_scope": "normalize location intent, search configured providers, rank/source-label results and fail soft",
        "fallback_mode": "ZENDOC registered providers plus official/OpenStreetMap discovery when available",
        "human_gate": "none for read-only discovery; booking still requires a connected verified provider",
    },
    "video_search": {
        "owner_agents": ["VideoAgent", "LearningAgent"],
        "autonomous_scope": "query educational sources, preserve source state and produce learning handoffs",
        "fallback_mode": "written ZENDOC education and local/community resources without fabricated videos",
        "human_gate": "none for education; personal medical decisions remain clinician-reviewed",
    },
    "external_notifications": {
        "owner_agents": ["CommunicationAgent", "OperationsAgent"],
        "autonomous_scope": "route notification events, track delivery capability and retry safe transient failures",
        "fallback_mode": "authenticated in-app notifications",
        "human_gate": "operator configures authorized email/SMS/WhatsApp/push providers",
    },
    "database": {
        "owner_agents": ["OperationsAgent"],
        "autonomous_scope": "read health/readiness, safe retry/recovery signaling and persistence verification state",
        "fallback_mode": "public-release gate remains closed rather than accepting real health data without durable persistence",
        "human_gate": "operator provisions and verifies durable PostgreSQL plus backup/restore",
    },
}


def integration_ownership(key: str) -> dict:
    policy = INTEGRATION_POLICIES.get(str(key or "").strip())
    if policy is None:
        return {
            "owner_agents": ["OperationsAgent"],
            "autonomous_scope": "observe readiness and escalate unknown integration state",
            "fallback_mode": "fail closed or degrade to a truthful local/read-only capability",
            "human_gate": "operator review",
        }
    return {
        "owner_agents": list(policy["owner_agents"]),
        "autonomous_scope": policy["autonomous_scope"],
        "fallback_mode": policy["fallback_mode"],
        "human_gate": policy["human_gate"],
    }


def integration_policy_manifest() -> dict:
    return {
        "integration_count": len(INTEGRATION_POLICIES),
        "integrations": {key: integration_ownership(key) for key in sorted(INTEGRATION_POLICIES)},
        "principle": (
            "Agents automate observation, routing, retry, staging and safe degradation. "
            "They never invent credentials, contracts, provider acceptance, regulatory verification, payment or fulfilment."
        ),
    }
