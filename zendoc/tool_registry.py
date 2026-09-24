"""
ZENDOC Tool Registry — Milestone 8
Formal registry of agent tools with metadata, permissions, and risk classification.

Every tool must declare:
  - name, description
  - allowed agents (which specialized agents may call it)
  - allowed roles (which user roles may trigger it)
  - risk_class (READ_ONLY, LOW_RISK, CONSENT_REQUIRED, DOCTOR_APPROVAL, OWNER_APPROVAL, CRITICAL_BLOCKED)
  - requires_consent, requires_owner_approval, requires_doctor_approval
  - idempotent (safe to retry)
  - audit_required

NEVER exposes: execute_arbitrary_sql, execute_shell, eval_python, run_any_command
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ToolDefinition:
    name: str
    description: str
    allowed_agents: list[str]
    allowed_roles: list[str]
    risk_class: str
    idempotent: bool = True
    requires_consent: bool = False
    requires_owner_approval: bool = False
    requires_doctor_approval: bool = False
    audit_required: bool = True

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "allowed_agents": self.allowed_agents,
            "allowed_roles": self.allowed_roles,
            "risk_class": self.risk_class,
            "idempotent": self.idempotent,
            "requires_consent": self.requires_consent,
            "requires_owner_approval": self.requires_owner_approval,
            "requires_doctor_approval": self.requires_doctor_approval,
            "audit_required": self.audit_required,
        }


READ_ONLY = "READ_ONLY"
LOW_RISK = "LOW_RISK"
CONSENT_REQUIRED = "CONSENT_REQUIRED"
DOCTOR_APPROVAL = "DOCTOR_APPROVAL"
OWNER_APPROVAL = "OWNER_APPROVAL"
CRITICAL_BLOCKED = "CRITICAL_BLOCKED"

ALL_ROLES = ["patient", "doctor", "hospital", "pharmacy", "government", "admin"]
PROVIDER_ROLES = ["doctor", "hospital", "pharmacy", "government", "admin"]
ADMIN_ONLY = ["admin"]


def _value(actor, key, default=None):
    if actor is None:
        return default
    if hasattr(actor, "keys") and key in actor.keys():
        return actor[key]
    return actor.get(key, default) if isinstance(actor, dict) else default


TOOL_REGISTRY: dict[str, ToolDefinition] = {
    "find_contact": ToolDefinition(
        name="find_contact",
        description="Discover permitted contacts for the current user.",
        allowed_agents=["CommunicationAgent", "SearchAgent"],
        allowed_roles=ALL_ROLES,
        risk_class=READ_ONLY,
    ),
    "check_communication_permission": ToolDefinition(
        name="check_communication_permission",
        description="Check if the actor may communicate with a target user via a given channel.",
        allowed_agents=["CommunicationAgent"],
        allowed_roles=ALL_ROLES,
        risk_class=READ_ONLY,
    ),
    "start_conversation": ToolDefinition(
        name="start_conversation",
        description="Start a new ZENDOC Connect conversation (subject to policy gate).",
        allowed_agents=["CommunicationAgent"],
        allowed_roles=ALL_ROLES,
        risk_class=LOW_RISK,
        idempotent=False,
    ),
    "send_message": ToolDefinition(
        name="send_message",
        description="Send a text message in an existing permitted conversation.",
        allowed_agents=["CommunicationAgent"],
        allowed_roles=ALL_ROLES,
        risk_class=LOW_RISK,
        idempotent=False,
    ),
    "request_doctor_chat": ToolDefinition(
        name="request_doctor_chat",
        description="Request doctor chat or open a consultation request.",
        allowed_agents=["CommunicationAgent", "DoctorAgent"],
        allowed_roles=["patient"],
        risk_class=LOW_RISK,
        idempotent=False,
    ),
    "request_voice_call": ToolDefinition(
        name="request_voice_call",
        description="Check voice call permission and initiate request.",
        allowed_agents=["CommunicationAgent", "DoctorAgent"],
        allowed_roles=ALL_ROLES,
        risk_class=LOW_RISK,
    ),
    "request_video_call": ToolDefinition(
        name="request_video_call",
        description="Check video call permission and initiate request.",
        allowed_agents=["CommunicationAgent", "DoctorAgent"],
        allowed_roles=ALL_ROLES,
        risk_class=LOW_RISK,
    ),
    "share_video": ToolDefinition(
        name="share_video",
        description="Share an educational video into a conversation.",
        allowed_agents=["CommunicationAgent", "VideoAgent"],
        allowed_roles=ALL_ROLES,
        risk_class=LOW_RISK,
        idempotent=False,
    ),
    "share_report_with_consent": ToolDefinition(
        name="share_report_with_consent",
        description="Share a medical report into a conversation with patient consent gate.",
        allowed_agents=["CommunicationAgent", "CareAgent"],
        allowed_roles=ALL_ROLES,
        risk_class=CONSENT_REQUIRED,
        requires_consent=True,
        idempotent=False,
    ),
    "search_educational_video": ToolDefinition(
        name="search_educational_video",
        description="Search configured/local educational video guidance without fabricating transcripts.",
        allowed_agents=["VideoAgent", "LearningAgent"],
        allowed_roles=ALL_ROLES,
        risk_class=READ_ONLY,
    ),
    "get_iot_devices": ToolDefinition(
        name="get_iot_devices",
        description="List device records owned by the authenticated patient.",
        allowed_agents=["IoTAgent"],
        allowed_roles=["patient", "admin"],
        risk_class=READ_ONLY,
    ),

    "get_platform_summary": ToolDefinition(
        name="get_platform_summary",
        description="Retrieve high-level platform health and operation counts.",
        allowed_agents=["OperationsAgent"],
        allowed_roles=ADMIN_ONLY,
        risk_class=READ_ONLY,
    ),
    "get_pending_operations": ToolDefinition(
        name="get_pending_operations",
        description="List pending agent tasks and approvals.",
        allowed_agents=["OperationsAgent"],
        allowed_roles=ADMIN_ONLY,
        risk_class=READ_ONLY,
    ),
    "get_failed_operations": ToolDefinition(
        name="get_failed_operations",
        description="List failed platform events.",
        allowed_agents=["OperationsAgent"],
        allowed_roles=ADMIN_ONLY,
        risk_class=READ_ONLY,
    ),
    "get_appointment_summary": ToolDefinition(
        name="get_appointment_summary",
        description="Get appointment queue counts.",
        allowed_agents=["OperationsAgent", "CareAgent"],
        allowed_roles=ADMIN_ONLY,
        risk_class=READ_ONLY,
    ),
    "get_consultation_queue": ToolDefinition(
        name="get_consultation_queue",
        description="Get consultation request counts and statuses.",
        allowed_agents=["OperationsAgent", "DoctorAgent"],
        allowed_roles=ADMIN_ONLY,
        risk_class=READ_ONLY,
    ),
    "get_staff_task_summary": ToolDefinition(
        name="get_staff_task_summary",
        description="Get staff task queue status counts.",
        allowed_agents=["OperationsAgent"],
        allowed_roles=ADMIN_ONLY,
        risk_class=READ_ONLY,
    ),
    "get_provider_status": ToolDefinition(
        name="get_provider_status",
        description="Get provider availability and integration status.",
        allowed_agents=["OperationsAgent"],
        allowed_roles=ADMIN_ONLY,
        risk_class=READ_ONLY,
    ),
    "get_unread_summary": ToolDefinition(
        name="get_unread_summary",
        description="Get count of unread messages (not content).",
        allowed_agents=["CommunicationAgent", "OperationsAgent"],
        allowed_roles=ALL_ROLES,
        risk_class=READ_ONLY,
    ),
    "get_system_health": ToolDefinition(
        name="get_system_health",
        description="Get system health status, integration checks, and error counts.",
        allowed_agents=["OperationsAgent"],
        allowed_roles=ADMIN_ONLY,
        risk_class=READ_ONLY,
    ),
    "create_followup_task": ToolDefinition(
        name="create_followup_task",
        description="Create a staff follow-up task.",
        allowed_agents=["OperationsAgent", "CareAgent"],
        allowed_roles=PROVIDER_ROLES,
        risk_class=LOW_RISK,
        idempotent=False,
    ),
    "assign_allowed_task": ToolDefinition(
        name="assign_allowed_task",
        description="Assign a queued staff task to an available staff member.",
        allowed_agents=["OperationsAgent"],
        allowed_roles=ADMIN_ONLY,
        risk_class=LOW_RISK,
        idempotent=False,
    ),
    "retry_safe_task": ToolDefinition(
        name="retry_safe_task",
        description="Retry a failed agent task with a retriable error category.",
        allowed_agents=["OperationsAgent"],
        allowed_roles=ADMIN_ONLY,
        risk_class=LOW_RISK,
        requires_owner_approval=False,
    ),
    "escalate_task": ToolDefinition(
        name="escalate_task",
        description="Escalate a task for human review.",
        allowed_agents=["OperationsAgent"],
        allowed_roles=ADMIN_ONLY,
        risk_class=LOW_RISK,
        idempotent=False,
    ),
    "request_owner_approval": ToolDefinition(
        name="request_owner_approval",
        description="Submit an action for owner approval before execution.",
        allowed_agents=["OperationsAgent", "CareAgent"],
        allowed_roles=ADMIN_ONLY,
        risk_class=OWNER_APPROVAL,
        requires_owner_approval=True,
    ),
    "run_proactive_alert_check": ToolDefinition(
        name="run_proactive_alert_check",
        description="Run the bounded deterministic operational alert scan.",
        allowed_agents=["OperationsAgent"],
        allowed_roles=ADMIN_ONLY,
        risk_class=LOW_RISK,
    ),
    "run_safe_operations_automation": ToolDefinition(
        name="run_safe_operations_automation",
        description="Owner-only bounded automation: re-queue retriable failures and create deterministic operational alerts without executing arbitrary tasks.",
        allowed_agents=["OperationsAgent"],
        allowed_roles=ADMIN_ONLY,
        risk_class=LOW_RISK,
    ),

    "search_healthcare_providers": ToolDefinition(
        name="search_healthcare_providers",
        description="Search ZENDOC-verified providers plus configured external healthcare locations while preserving source/verification state.",
        allowed_agents=["ProviderDiscoveryAgent", "BookingAgent", "SearchAgent"],
        allowed_roles=ALL_ROLES,
        risk_class=READ_ONLY,
    ),
    "get_provider_booking_options": ToolDefinition(
        name="get_provider_booking_options",
        description=(
            "Read verified ZENDOC provider profile and provider-published free slots for a requested date. "
            "External/unverified listings are never converted into connected booking availability."
        ),
        allowed_agents=["BookingAgent"],
        allowed_roles=["patient", "admin"],
        risk_class=READ_ONLY,
    ),
    "confirm_provider_booking": ToolDefinition(
        name="confirm_provider_booking",
        description=(
            "Create a requested appointment for a verified connected ZENDOC provider and currently free slot. "
            "Requires fresh explicit user confirmation and is never executable in an autonomous plan."
        ),
        allowed_agents=["BookingAgent"],
        allowed_roles=["patient"],
        risk_class=CONSENT_REQUIRED,
        requires_consent=True,
        idempotent=False,
    ),
    "search_health_products": ToolDefinition(
        name="search_health_products",
        description=(
            "Return truthful external search/catalog handoffs for non-medicine health products. "
            "Does not claim stock, price, seller suitability, affiliate relationship, checkout or payment connectivity."
        ),
        allowed_agents=["CommerceAgent"],
        allowed_roles=["patient", "admin"],
        risk_class=READ_ONLY,
    ),
    "get_latest_prescription_review": ToolDefinition(
        name="get_latest_prescription_review",
        description="Read the latest authorized prescription review state; never changes medicine, dose, frequency, form, or order state.",
        allowed_agents=["MedicationSafetyAgent"],
        allowed_roles=["patient", "doctor", "pharmacy", "admin"],
        risk_class=READ_ONLY,
    ),
    "compare_nutrition_products": ToolDefinition(
        name="compare_nutrition_products",
        description="Compare user-supplied nutrition labels and normalized prices for general wellness; sponsorship never changes health suitability ranking.",
        allowed_agents=["NutritionAgent"],
        allowed_roles=["patient", "admin"],
        risk_class=READ_ONLY,
    ),
    "discover_carefin_benefits": ToolDefinition(
        name="discover_carefin_benefits",
        description=(
            "Discover possible healthcare support pathways from official/public source metadata. "
            "Returns candidates, missing information, provenance, and verification next steps. "
            "Never confirms personal eligibility, approval, or payment."
        ),
        allowed_agents=["CareFinAgent"],
        allowed_roles=ALL_ROLES,
        risk_class=READ_ONLY,
    ),

    "get_fitness_snapshot": ToolDefinition(
        name="get_fitness_snapshot",
        description="Read the authenticated patient's fitness profile, current plan and recent progress for general-wellness automation.",
        allowed_agents=["FitnessAgent"],
        allowed_roles=["patient"],
        risk_class=READ_ONLY,
    ),
    "generate_fitness_plan": ToolDefinition(
        name="generate_fitness_plan",
        description=(
            "Generate and persist a general-wellness workout plan from the authenticated patient's existing fitness profile. "
            "This does not diagnose, prescribe exercise as treatment, or override declared clinical restrictions."
        ),
        allowed_agents=["FitnessAgent"],
        allowed_roles=["patient"],
        risk_class=LOW_RISK,
        idempotent=False,
    ),
    "get_family_care_snapshot": ToolDefinition(
        name="get_family_care_snapshot",
        description=(
            "Read only family members, scoped care tasks and access-grant metadata visible to the authenticated actor. "
            "It never expands family consent or exposes another adult's care without an active grant."
        ),
        allowed_agents=["FamilyCareAgent"],
        allowed_roles=["patient", "admin"],
        risk_class=READ_ONLY,
    ),
    "get_home_health_options": ToolDefinition(
        name="get_home_health_options",
        description=(
            "List ZENDOC home-health service categories and the actor's existing request truth states. "
            "It does not claim provider assignment, availability, price or fulfilment."
        ),
        allowed_agents=["HomeHealthAgent"],
        allowed_roles=["patient", "doctor", "admin"],
        risk_class=READ_ONLY,
    ),
    "confirm_home_health_request": ToolDefinition(
        name="confirm_home_health_request",
        description=(
            "Create a home-health intake request after fresh explicit user confirmation. "
            "The request remains unconfirmed until a verified provider accepts it."
        ),
        allowed_agents=["HomeHealthAgent"],
        allowed_roles=["patient", "doctor", "admin"],
        risk_class=CONSENT_REQUIRED,
        requires_consent=True,
        idempotent=False,
    ),
    "get_transport_options": ToolDefinition(
        name="get_transport_options",
        description=(
            "List medical-transport categories and the actor's existing request truth states. "
            "It never claims a vehicle, ETA, provider acceptance or dispatch."
        ),
        allowed_agents=["TransportAgent"],
        allowed_roles=["patient", "doctor", "hospital", "admin"],
        risk_class=READ_ONLY,
    ),
    "confirm_transport_request": ToolDefinition(
        name="confirm_transport_request",
        description=(
            "Record a non-autonomous medical-transport intake request after fresh explicit user confirmation. "
            "This does not dispatch an ambulance or confirm a vehicle/provider."
        ),
        allowed_agents=["TransportAgent"],
        allowed_roles=["patient", "doctor", "hospital", "admin"],
        risk_class=CONSENT_REQUIRED,
        requires_consent=True,
        idempotent=False,
    ),

    "autonomous_prescribe": ToolDefinition(
        name="autonomous_prescribe",
        description="[BLOCKED] Autonomous prescribing is CRITICAL_BLOCKED. Requires legally valid doctor workflow.",
        allowed_agents=[],
        allowed_roles=[],
        risk_class=CRITICAL_BLOCKED,
    ),
    "dispatch_emergency": ToolDefinition(
        name="dispatch_emergency",
        description="[BLOCKED] Real emergency dispatch cannot be autonomously triggered by an agent.",
        allowed_agents=[],
        allowed_roles=[],
        risk_class=CRITICAL_BLOCKED,
    ),
    "execute_payment": ToolDefinition(
        name="execute_payment",
        description="[BLOCKED] Models never execute payment or receive payment secrets. A future verified payment integration must use a separate deterministic user-authorized flow.",
        allowed_agents=[],
        allowed_roles=[],
        risk_class=CRITICAL_BLOCKED,
    ),
    "self_modify_production": ToolDefinition(
        name="self_modify_production",
        description="[BLOCKED] Agents cannot rewrite production code/policy, broaden permissions, disable safeguards, or deploy themselves.",
        allowed_agents=[],
        allowed_roles=[],
        risk_class=CRITICAL_BLOCKED,
    ),

    "search_nearby_pharmacy_inventory": ToolDefinition(
        name="search_nearby_pharmacy_inventory",
        description=(
            "Search pharmacy inventory observations near a patient location for a medicine query. "
            "Returns freshness-labelled offers (CONFIRMED / STALE / UNKNOWN). "
            "UNKNOWN inventory is NEVER promoted to available."
        ),
        allowed_agents=["PharmacyAgent", "CareAgent", "SearchAgent"],
        allowed_roles=["patient", "doctor", "admin"],
        risk_class=READ_ONLY,
    ),
    "compare_prescription_fulfilment": ToolDefinition(
        name="compare_prescription_fulfilment",
        description=(
            "Compare multi-pharmacy fulfilment options for an active prescription. "
            "Returns ranked plans (single complete, split, stale) for user selection. "
            "Does NOT place any order — read only."
        ),
        allowed_agents=["PharmacyAgent", "CareAgent"],
        allowed_roles=["patient", "doctor", "admin"],
        risk_class=READ_ONLY,
    ),
    "stage_fulfilment_plan": ToolDefinition(
        name="stage_fulfilment_plan",
        description=(
            "Stage a pharmacy fulfilment plan from an active prescription for user review. "
            "Persists the plan in DB but does NOT submit any order. Requires user confirmation to proceed."
        ),
        allowed_agents=["PharmacyAgent", "CareAgent"],
        allowed_roles=["patient", "doctor", "admin"],
        risk_class=LOW_RISK,
        idempotent=False,
    ),
    "confirm_and_execute_order": ToolDefinition(
        name="confirm_and_execute_order",
        description=(
            "Submit a staged fulfilment plan as a real medicine order. "
            "REQUIRES explicit user_confirmed=True. "
            "This is a consequential action — AI may NEVER call this without user's explicit approval."
        ),
        allowed_agents=["PharmacyAgent"],
        allowed_roles=["patient", "admin"],
        risk_class=CONSENT_REQUIRED,
        requires_consent=True,
        idempotent=False,
    ),
    "get_diagnostic_options": ToolDefinition(
        name="get_diagnostic_options",
        description="Search available diagnostic tests and lab offers near a patient location.",
        allowed_agents=["CareAgent", "SearchAgent", "DiagnosticsAgent"],
        allowed_roles=ALL_ROLES,
        risk_class=READ_ONLY,
    ),
    "get_unified_healthcare_inbox": ToolDefinition(
        name="get_unified_healthcare_inbox",
        description="Retrieve the unified healthcare inbox: recent orders, diagnostic bookings, and health memory events.",
        allowed_agents=["CareAgent", "HealthMemoryAgent"],
        allowed_roles=["patient", "doctor", "admin"],
        risk_class=READ_ONLY,
    ),
    "get_health_memory_context": ToolDefinition(
        name="get_health_memory_context",
        description=(
            "Build an authorized, minimum-necessary Health Memory view with provenance and non-clinical next-safe actions. "
            "Cross-patient access requires explicit context authorization."
        ),
        allowed_agents=["HealthMemoryAgent", "PreventionAgent", "LifecycleAgent"],
        allowed_roles=["patient", "doctor", "hospital", "admin"],
        risk_class=READ_ONLY,
    ),
    "search_health_memory_evidence": ToolDefinition(
        name="search_health_memory_evidence",
        description=(
            "Search only authorized ZENDOC-stored Health Memory events using local lexical retrieval. "
            "Returns provenance-bearing evidence and excludes prior AI chat interactions from medical evidence."
        ),
        allowed_agents=["HealthMemoryAgent", "PreventionAgent", "LifecycleAgent"],
        allowed_roles=["patient", "doctor", "hospital", "admin"],
        risk_class=READ_ONLY,
    ),
}


def get_tool(tool_name: str) -> ToolDefinition | None:
    return TOOL_REGISTRY.get(tool_name)


def check_tool_access(tool_name: str, actor: dict, agent_name: str | None = None) -> dict:
    """Check whether the actor (and agent) may use this tool. Unknown/blocked tools fail closed."""
    tool = get_tool(tool_name)
    if not tool:
        return {"allowed": False, "reason": f"Tool '{tool_name}' is not registered."}

    if tool.risk_class == CRITICAL_BLOCKED:
        return {"allowed": False, "reason": f"Tool '{tool_name}' is CRITICAL_BLOCKED and cannot be executed by any agent."}

    actor_role = _value(actor, "role", "")
    if actor_role == "admin":
        from .security import is_owner
        if not is_owner(actor):
            return {"allowed": False, "reason": "Admin tools are restricted to the configured ZENDOC owner."}
    if actor_role not in tool.allowed_roles:
        return {"allowed": False, "reason": f"Role '{actor_role}' is not permitted to use tool '{tool_name}'."}

    if agent_name and tool.allowed_agents and agent_name not in tool.allowed_agents:
        return {"allowed": False, "reason": f"Agent '{agent_name}' is not permitted to use tool '{tool_name}'."}

    if tool.requires_owner_approval and actor_role != "admin":
        return {"allowed": False, "reason": f"Tool '{tool_name}' requires owner approval."}

    return {"allowed": True, "reason": "Access granted."}


def list_tools_for_role(role: str) -> list[dict]:
    return [
        t.to_dict()
        for t in TOOL_REGISTRY.values()
        if role in t.allowed_roles and t.risk_class != CRITICAL_BLOCKED
    ]


def list_tools_for_actor(actor: dict) -> list[dict]:
    result = []
    for tool in TOOL_REGISTRY.values():
        decision = check_tool_access(tool.name, actor)
        if decision["allowed"]:
            result.append(tool.to_dict())
    return result
