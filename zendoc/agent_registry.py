"""
ZENDOC Specialized Agent Registry — Milestone 8
Registry of specialized agents with their purpose, tools, risk, and status.

Each agent entry is a real metadata definition.
Agents are NOT autonomous AI LLMs — they are structured handlers
chosen by the Core Agent based on validated intent.

CRITICAL: An agent can NEVER bypass authentication, authorization,
consent, doctor authority, emergency safeguards, or financial approval.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentDefinition:
    identifier: str
    name: str
    purpose: str
    allowed_tools: list[str]
    allowed_actor_roles: list[str]
    risk_level: str          # READ_ONLY | LOW_RISK | CONSENT_REQUIRED | OWNER_APPROVAL
    approval_requirements: list[str]
    status: str              # connected | beta | integration_required | disabled
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "identifier": self.identifier,
            "name": self.name,
            "purpose": self.purpose,
            "allowed_tools": self.allowed_tools,
            "allowed_actor_roles": self.allowed_actor_roles,
            "risk_level": self.risk_level,
            "approval_requirements": self.approval_requirements,
            "status": self.status,
            "description": self.description,
        }


ALL_ROLES = ["patient", "doctor", "hospital", "pharmacy", "government", "admin"]
PROVIDER_ROLES = ["doctor", "hospital", "pharmacy", "government", "admin"]


AGENT_REGISTRY: dict[str, AgentDefinition] = {

    "SafetyAgent": AgentDefinition(
        identifier="SafetyAgent",
        name="Safety Agent",
        purpose="Emergency detection and safety escalation — always first.",
        allowed_tools=["get_system_health"],
        allowed_actor_roles=ALL_ROLES,
        risk_level="READ_ONLY",
        approval_requirements=[],
        status="connected",
        description="Deterministic safety engine. Never routed to an LLM. Emergency check runs before any other agent.",
    ),

    "CareAgent": AgentDefinition(
        identifier="CareAgent",
        name="Care Agent",
        purpose="Appointments, medical reports, family care coordination.",
        allowed_tools=[
            "find_contact",
            "get_appointment_summary",
            "share_report_with_consent",
            "create_followup_task",
            "search_nearby_pharmacy_inventory",
            "compare_prescription_fulfilment",
            "stage_fulfilment_plan",
            "get_diagnostic_options",
            "get_unified_healthcare_inbox",
        ],
        allowed_actor_roles=ALL_ROLES,
        risk_level="CONSENT_REQUIRED",
        approval_requirements=["patient_consent_for_record_sharing"],
        status="connected",
        description="Coordinates care workflows. Report sharing requires patient consent.",
    ),

    "DoctorAgent": AgentDefinition(
        identifier="DoctorAgent",
        name="Doctor / Telehealth Agent",
        purpose="Doctor availability, consultation requests, telehealth routing.",
        allowed_tools=["request_doctor_chat", "request_voice_call", "request_video_call", "get_consultation_queue"],
        allowed_actor_roles=["patient", "doctor", "hospital", "admin"],
        risk_level="LOW_RISK",
        approval_requirements=["doctor_acceptance_required"],
        status="beta",
        description="Coordinates telehealth requests. Doctors retain full clinical authority.",
    ),

    "CommunicationAgent": AgentDefinition(
        identifier="CommunicationAgent",
        name="Communication Agent",
        purpose="Permissioned messaging, contacts, video/report sharing through policy layer.",
        allowed_tools=[
            "find_contact",
            "check_communication_permission",
            "start_conversation",
            "send_message",
            "share_video",
            "share_report_with_consent",
            "get_unread_summary",
            "request_voice_call",
            "request_video_call",
        ],
        allowed_actor_roles=ALL_ROLES,
        risk_level="LOW_RISK",
        approval_requirements=["communication_policy_gate"],
        status="connected",
        description="ALWAYS routes through communication_policy.py. Cannot bypass doctor policies.",
    ),

    "FitnessAgent": AgentDefinition(
        identifier="FitnessAgent",
        name="Fitness Agent",
        purpose="Workout plans, sessions, nutrition, pose coaching.",
        allowed_tools=["find_contact"],
        allowed_actor_roles=["patient", "admin"],
        risk_level="READ_ONLY",
        approval_requirements=[],
        status="connected",
        description="Fitness plans and session data for the authenticated patient only.",
    ),

    "VideoAgent": AgentDefinition(
        identifier="VideoAgent",
        name="Video Intelligence Agent",
        purpose="Educational video search and guidance generation.",
        allowed_tools=["share_video", "search_educational_video"],
        allowed_actor_roles=ALL_ROLES,
        risk_level="READ_ONLY",
        approval_requirements=[],
        status="beta",
        description="Video search is honest about provider availability. No fake transcripts.",
    ),

    "FamilyCareAgent": AgentDefinition(
        identifier="FamilyCareAgent",
        name="Family Care Agent",
        purpose="Remote parent care with consent — appointments, reports, home care.",
        allowed_tools=["share_report_with_consent", "create_followup_task"],
        allowed_actor_roles=["patient", "admin"],
        risk_level="CONSENT_REQUIRED",
        approval_requirements=["family_access_grant_required"],
        status="connected",
        description="Requires active family access grant. Cannot access another adult's care without consent.",
    ),

    "PharmacyAgent": AgentDefinition(
        identifier="PharmacyAgent",
        name="Pharmacy Agent",
        purpose="Medicine search, hyperlocal inventory discovery, and delivery requests.",
        allowed_tools=[
            "find_contact",
            "search_nearby_pharmacy_inventory",
            "compare_prescription_fulfilment",
            "stage_fulfilment_plan",
            "confirm_and_execute_order",
        ],
        allowed_actor_roles=["patient", "pharmacy", "admin"],
        risk_level="LOW_RISK",
        approval_requirements=[],
        status="connected",
        description="Medicine information, multi-pharmacy fulfilment staging, and confirmed order intake.",
    ),

    "HomeHealthAgent": AgentDefinition(
        identifier="HomeHealthAgent",
        name="Home Health Agent",
        purpose="Home-care request intake (nursing, physiotherapy, elder care).",
        allowed_tools=["create_followup_task"],
        allowed_actor_roles=["patient", "doctor", "admin"],
        risk_level="LOW_RISK",
        approval_requirements=[],
        status="integration_required",
        description="Service intake working. Live provider fulfillment requires external integration.",
    ),

    "TransportAgent": AgentDefinition(
        identifier="TransportAgent",
        name="Transport Agent",
        purpose="Medical transport requests (ambulance, wheelchair van).",
        allowed_tools=["create_followup_task"],
        allowed_actor_roles=["patient", "doctor", "hospital", "admin"],
        risk_level="LOW_RISK",
        approval_requirements=[],
        status="integration_required",
        description="Transport intake without live dispatch. Real dispatch requires provider integration.",
    ),

    "IoTAgent": AgentDefinition(
        identifier="IoTAgent",
        name="IoT Agent",
        purpose="Authorized health device measurements and alerts.",
        allowed_tools=["get_iot_devices"],
        allowed_actor_roles=["patient", "admin"],
        risk_level="READ_ONLY",
        approval_requirements=[],
        status="beta",
        description="Reads registered device data for the authenticated patient only.",
    ),

    "OperationsAgent": AgentDefinition(
        identifier="OperationsAgent",
        name="Operations Agent",
        purpose="Staff tasks, operational queues, failed operations — owner-only.",
        allowed_tools=[
            "get_platform_summary",
            "get_pending_operations",
            "get_failed_operations",
            "get_appointment_summary",
            "get_consultation_queue",
            "get_staff_task_summary",
            "get_provider_status",
            "get_system_health",
            "create_followup_task",
            "assign_allowed_task",
            "retry_safe_task",
            "escalate_task",
            "request_owner_approval",
            "run_proactive_alert_check",
        ],
        allowed_actor_roles=["admin"],
        risk_level="OWNER_APPROVAL",
        approval_requirements=["owner_auth_required"],
        status="beta",
        description="Owner-only operational control. Read tools work freely. Write tools may require approval.",
    ),

    "SearchAgent": AgentDefinition(
        identifier="SearchAgent",
        name="Search Agent",
        purpose="Universal search across permitted platform data.",
        allowed_tools=[
            "find_contact",
            "search_nearby_pharmacy_inventory",
            "get_diagnostic_options",
        ],
        allowed_actor_roles=ALL_ROLES,
        risk_level="READ_ONLY",
        approval_requirements=[],
        status="connected",
        description="Never leaks cross-user private data. Respects role and access boundaries.",
    ),
}


def get_agent(identifier: str) -> AgentDefinition | None:
    return AGENT_REGISTRY.get(identifier)


def list_agents() -> list[dict]:
    return [a.to_dict() for a in AGENT_REGISTRY.values()]


def choose_agent_for_intent(intent: str) -> AgentDefinition | None:
    """Map an intent to the most appropriate specialized agent."""
    mapping = {
        "emergency":        "SafetyAgent",
        "symptoms":         "CareAgent",
        "appointment":      "CareAgent",
        "report_history":   "CareAgent",
        "report_intelligence": "CareAgent",
        "health_timeline":  "CareAgent",
        "health_analytics": "CareAgent",
        "health_profile":   "CareAgent",
        "health_records":   "CareAgent",
        "telehealth":       "DoctorAgent",
        "telehealth_request": "DoctorAgent",
        "video_consultation": "DoctorAgent",
        "doctor":           "DoctorAgent",
        "contact_discovery": "CommunicationAgent",
        "messages_inbox":   "CommunicationAgent",
        "video_share":      "CommunicationAgent",
        "record_share_request": "CommunicationAgent",
        "fitness":          "FitnessAgent",
        "fitness_coach":    "FitnessAgent",
        "workout_plan":     "FitnessAgent",
        "workout_session":  "FitnessAgent",
        "exercise_instruction": "FitnessAgent",
        "fitness_analytics": "FitnessAgent",
        "video_intelligence": "VideoAgent",
        "fitness_video_search": "VideoAgent",
        "family_care":      "FamilyCareAgent",
        "home_health":      "HomeHealthAgent",
        "ambulance":        "TransportAgent",
        "pharmacy":         "PharmacyAgent",
        "iot_hub":          "IoTAgent",
        "iot_status":       "IoTAgent",
        "platform_health":  "OperationsAgent",
        "failed_operations": "OperationsAgent",
        "core_agent":       "OperationsAgent",
        "care_coordination": "CareAgent",
        "general_agent":    "SearchAgent",
        "general_assistant": "SearchAgent",
    }
    agent_id = mapping.get(intent, "SearchAgent")
    return AGENT_REGISTRY.get(agent_id)
