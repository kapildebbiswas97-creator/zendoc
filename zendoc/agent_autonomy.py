"""Bounded autonomy policy for the ZENDOC multi-agent operating layer.

This module is intentionally deterministic and model-agnostic. It answers one
question before a specialized agent attempts work: may this action run
reversibly, does it require an explicit human gate, or is it forbidden to an
AI agent altogether?

The policy is deliberately stricter than a general browser agent because ZENDOC
handles health, family, financial and provider workflows. Models may plan,
search, compare, summarize, retry safe reads and prepare actions. They may not
turn model output into diagnosis/prescribing, silently spend money, broaden
their own permissions, rewrite the production safety policy, or deploy a new
model/code version by themselves.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


AUTOMATIC = "AUTOMATIC"
AUTOMATIC_SANDBOX = "AUTOMATIC_SANDBOX"
USER_CONFIRMATION_REQUIRED = "USER_CONFIRMATION_REQUIRED"
OWNER_APPROVAL_REQUIRED = "OWNER_APPROVAL_REQUIRED"
CLINICIAN_REVIEW_REQUIRED = "CLINICIAN_REVIEW_REQUIRED"
CRITICAL_BLOCKED = "CRITICAL_BLOCKED"
UNKNOWN_ACTION = "UNKNOWN_ACTION"


@dataclass(frozen=True)
class AutonomyDecision:
    agent_id: str
    action: str
    decision: str
    reason: str
    can_execute_now: bool
    human_gate: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


# Reversible operations that may run without asking the user on every step.
_AUTOMATIC_ACTIONS = {
    "read",
    "search",
    "browse_connected_source",
    "compare",
    "summarize",
    "plan",
    "rewrite_query",
    "change_search_parameters",
    "rank_truthful_options",
    "retry_safe_read",
    "check_availability",
    "prepare_action",
    "stage_action",
    "stage_cart",
    "prepare_checkout",
    "prepare_booking",
    "prepare_order",
}

# Consequential but legitimate user actions. An agent may prepare them, but a
# deterministic executor must receive fresh, explicit human confirmation.
_USER_GATED_ACTIONS = {
    "book",
    "confirm_booking",
    "cancel_booking",
    "reschedule_booking",
    "submit_order",
    "place_order",
    "confirm_checkout",
    "share_health_record",
    "start_paid_service",
    "change_permission",
    "revoke_permission",
}

# Clinical actions that need qualified human authority rather than ordinary
# user confirmation.
_CLINICIAN_GATED_ACTIONS = {
    "interpret_as_diagnosis",
    "clinical_treatment_decision",
    "medical_diet_decision",
    "medication_review_for_ambiguity",
}

# Offline improvement can be automatic inside a tool-free evaluation sandbox.
_SANDBOX_IMPROVEMENT_ACTIONS = {
    "propose_prompt_candidate",
    "propose_routing_candidate",
    "propose_model_candidate",
    "run_offline_eval",
    "score_offline_eval",
    "compare_eval_results",
}

# Promotion changes the production system and must be decided by the owner.
_OWNER_GATED_ACTIONS = {
    "promote_prompt_candidate",
    "promote_routing_candidate",
    "promote_model_candidate",
    "change_agent_allowlist",
    "change_tool_permission",
}

# No ZENDOC model/agent is allowed to perform these actions. Some may exist as
# separate legally/operationally authorized human workflows, but never as an AI
# tool invocation.
_CRITICAL_ACTIONS = {
    "diagnose",
    "prescribe",
    "change_medication",
    "change_dose",
    "substitute_medicine",
    "execute_payment",
    "enter_payment_secret",
    "read_payment_secret",
    "dispatch_emergency",
    "execute_arbitrary_sql",
    "execute_shell",
    "execute_arbitrary_code",
    "read_server_secret",
    "create_secret",
    "self_modify_production_code",
    "self_modify_policy",
    "disable_safety",
    "disable_audit",
    "expand_own_permissions",
    "self_promote_model",
    "deploy_production",
}


# Every specialized domain is explicit. This is a product/control-plane catalog,
# not a claim that a third-party integration is connected.
DOMAIN_AGENTS = {
    "safety": "SafetyAgent",
    "care": "CareAgent",
    "booking": "BookingAgent",
    "commerce": "CommerceAgent",
    "pharmacy": "PharmacyAgent",
    "diagnostics": "DiagnosticsAgent",
    "fitness": "FitnessAgent",
    "nutrition": "NutritionAgent",
    "family": "FamilyCareAgent",
    "lifecycle": "LifecycleAgent",
    "prevention": "PreventionAgent",
    "health_memory": "HealthMemoryAgent",
    "provider_discovery": "ProviderDiscoveryAgent",
    "doctor_telehealth": "DoctorAgent",
    "devices": "IoTAgent",
    "learning": "LearningAgent",
    "affordability": "CareFinAgent",
    "home_health": "HomeHealthAgent",
    "transport": "TransportAgent",
    "communication": "CommunicationAgent",
    "video": "VideoAgent",
    "operations": "OperationsAgent",
    "model_improvement": "ModelImprovementAgent",
}


def classify_agent_action(agent_id: str, action: str) -> dict:
    """Return a deterministic autonomy decision for an agent action.

    Unknown actions fail closed. Callers should use a registered tool/action
    rather than interpreting an unknown action permissively.
    """
    normalized_agent = str(agent_id or "").strip()
    normalized_action = str(action or "").strip().lower().replace(" ", "_")

    if normalized_action in _CRITICAL_ACTIONS:
        return AutonomyDecision(
            normalized_agent,
            normalized_action,
            CRITICAL_BLOCKED,
            "This action is outside model authority and cannot be executed by a ZENDOC agent.",
            False,
            "deterministic_or_qualified_human_workflow_only",
        ).to_dict()

    if normalized_action in _CLINICIAN_GATED_ACTIONS:
        return AutonomyDecision(
            normalized_agent,
            normalized_action,
            CLINICIAN_REVIEW_REQUIRED,
            "Clinical authority cannot be delegated to a general-purpose model.",
            False,
            "qualified_clinician_review",
        ).to_dict()

    if normalized_action in _OWNER_GATED_ACTIONS:
        return AutonomyDecision(
            normalized_agent,
            normalized_action,
            OWNER_APPROVAL_REQUIRED,
            "Production model/policy changes require explicit owner review and deterministic promotion.",
            False,
            "configured_owner_approval",
        ).to_dict()

    if normalized_action in _USER_GATED_ACTIONS:
        return AutonomyDecision(
            normalized_agent,
            normalized_action,
            USER_CONFIRMATION_REQUIRED,
            "The agent may prepare this consequential action but cannot finalize it without fresh explicit confirmation.",
            False,
            "explicit_user_confirmation",
        ).to_dict()

    if normalized_action in _SANDBOX_IMPROVEMENT_ACTIONS:
        if normalized_agent != "ModelImprovementAgent":
            return AutonomyDecision(
                normalized_agent,
                normalized_action,
                CRITICAL_BLOCKED,
                "Only the isolated Model Improvement Agent may run offline candidate evaluation.",
                False,
                "model_evaluation_sandbox",
            ).to_dict()
        return AutonomyDecision(
            normalized_agent,
            normalized_action,
            AUTOMATIC_SANDBOX,
            "Allowed only inside the no-tools/offline evaluation boundary; it cannot promote itself to production.",
            True,
            None,
        ).to_dict()

    if normalized_action in _AUTOMATIC_ACTIONS:
        return AutonomyDecision(
            normalized_agent,
            normalized_action,
            AUTOMATIC,
            "Reversible/read-only preparation may run inside the agent's registered tool allowlist.",
            True,
            None,
        ).to_dict()

    return AutonomyDecision(
        normalized_agent,
        normalized_action,
        UNKNOWN_ACTION,
        "Unknown actions fail closed until they are explicitly classified and tested.",
        False,
        "policy_registration_required",
    ).to_dict()


def bounded_autonomy_manifest() -> dict:
    """Machine-readable product statement for UI, docs and regression tests."""
    return {
        "domain_agents": dict(DOMAIN_AGENTS),
        "automatic_examples": sorted(_AUTOMATIC_ACTIONS),
        "user_confirmation_examples": sorted(_USER_GATED_ACTIONS),
        "clinician_review_examples": sorted(_CLINICIAN_GATED_ACTIONS),
        "sandbox_improvement_examples": sorted(_SANDBOX_IMPROVEMENT_ACTIONS),
        "owner_approval_examples": sorted(_OWNER_GATED_ACTIONS),
        "critical_blocked_examples": sorted(_CRITICAL_ACTIONS),
        "browser_like_pattern": (
            "intent -> plan -> authenticated/connected search -> compare -> prepare -> "
            "human gate for consequential action -> deterministic executor -> evidence/audit"
        ),
        "payment_policy": "Agents may prepare checkout; models never execute payment or receive payment secrets.",
        "self_improvement_policy": (
            "Agents may propose and evaluate candidates offline. Production promotion, permission changes and deployment "
            "require deterministic owner-controlled workflows; self-modification is blocked."
        ),
    }
