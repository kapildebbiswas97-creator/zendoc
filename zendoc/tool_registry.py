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

from dataclasses import dataclass, field


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


# ── Risk classes ───────────────────────────────────────────────────────────────
READ_ONLY         = "READ_ONLY"
LOW_RISK          = "LOW_RISK"
CONSENT_REQUIRED  = "CONSENT_REQUIRED"
DOCTOR_APPROVAL   = "DOCTOR_APPROVAL"
OWNER_APPROVAL    = "OWNER_APPROVAL"
CRITICAL_BLOCKED  = "CRITICAL_BLOCKED"

ALL_ROLES = ["patient", "doctor", "hospital", "pharmacy", "government", "admin"]
PROVIDER_ROLES = ["doctor", "hospital", "pharmacy", "government", "admin"]
ADMIN_ONLY = ["admin"]


def _value(actor, key, default=None):
    if actor is None:
        return default
    if hasattr(actor, "keys") and key in actor.keys():
        return actor[key]
    return actor.get(key, default) if isinstance(actor, dict) else default


# ── Tool Registry ──────────────────────────────────────────────────────────────
TOOL_REGISTRY: dict[str, ToolDefinition] = {

    # ── Communication tools (M7.1 preserved) ──────────────────────────────────
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
        allowed_agents=["VideoAgent"],
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

    # ── Platform operational tools (owner only) ────────────────────────────────
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

    # ── Safety / Blocked tools ─────────────────────────────────────────────────
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

    # ── Milestone 10: Connected Care tools ────────────────────────────────────
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
        allowed_agents=["CareAgent", "SearchAgent"],
        allowed_roles=ALL_ROLES,
        risk_class=READ_ONLY,
    ),
    "get_unified_healthcare_inbox": ToolDefinition(
        name="get_unified_healthcare_inbox",
        description="Retrieve the unified healthcare inbox: recent orders, diagnostic bookings, and health memory events.",
        allowed_agents=["CareAgent"],
        allowed_roles=["patient", "doctor", "admin"],
        risk_class=READ_ONLY,
    ),
}


def get_tool(tool_name: str) -> ToolDefinition | None:
    return TOOL_REGISTRY.get(tool_name)


def check_tool_access(tool_name: str, actor: dict, agent_name: str | None = None) -> dict:
    """
    Check whether the actor (and agent) may use this tool.
    Returns {"allowed": bool, "reason": str}
    This is a SERVER-SIDE check. Never trust client claims.
    """
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
    """List all tools accessible to a given role (excluding CRITICAL_BLOCKED)."""
    return [
        t.to_dict()
        for t in TOOL_REGISTRY.values()
        if role in t.allowed_roles and t.risk_class != CRITICAL_BLOCKED
    ]


def list_tools_for_actor(actor: dict) -> list[dict]:
    """Return only tool metadata this authenticated actor may request."""
    result = []
    for tool in TOOL_REGISTRY.values():
        decision = check_tool_access(tool.name, actor)
        if decision["allowed"]:
            result.append(tool.to_dict())
    return result
