"""Bounded deterministic planner for the ZENDOC Core Agent."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from .agent_registry import choose_agent_for_intent
from .safety import SafetyEngine


@dataclass(frozen=True)
class PlanStep:
    sequence: int
    tool_name: str
    arguments: dict = field(default_factory=dict)
    purpose: str = ""

    def to_dict(self):
        return {
            "sequence": self.sequence,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "purpose": self.purpose,
        }


@dataclass(frozen=True)
class AgentPlan:
    plan_id: str
    command: str
    intent: str
    urgency: str
    assigned_agent: str
    risk_level: str
    steps: tuple[PlanStep, ...]
    requires_confirmation: bool = False
    authorization_error: str | None = None
    safety: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "plan_id": self.plan_id,
            "intent": self.intent,
            "urgency": self.urgency,
            "assigned_agent": self.assigned_agent,
            "risk_level": self.risk_level,
            "steps": [step.to_dict() for step in self.steps],
            "requires_confirmation": self.requires_confirmation,
            "authorization_error": self.authorization_error,
        }


def build_plan(actor, command_text: str) -> AgentPlan:
    command = str(command_text or "").strip()
    if not command:
        raise ValueError("Agent command is required.")
    if len(command) > 2000:
        raise ValueError("Agent command is too long.")
    safety = SafetyEngine().assess(command)
    if safety["emergency"]:
        return _plan(command, "emergency", "SafetyAgent", "read_only", (), safety=safety, urgency="emergency")

    lower = command.lower()
    from .security import is_owner
    owner = is_owner(actor)

    if any(text in lower for text in ("summary", "platform health", "operations summary", "today")) and owner:
        return _plan(command, "platform_health", "OperationsAgent", "read_only", (
            PlanStep(1, "get_platform_summary", {}, "Read aggregate operational health."),
        ))
    if "failed" in lower and owner:
        return _plan(command, "failed_operations", "OperationsAgent", "read_only", (
            PlanStep(1, "get_failed_operations", {}, "Read failed operational events."),
        ))
    if any(text in lower for text in ("run alert check", "scan alerts", "check operational alerts")):
        if not owner:
            return _unauthorized(command, "platform_health")
        return _plan(command, "platform_health", "OperationsAgent", "low_risk", (
            PlanStep(1, "run_proactive_alert_check", {}, "Run bounded deterministic operational checks."),
        ))
    if any(text in lower for text in ("find contact", "search contact", "discover contact", "who can i message", "search doctor")):
        query = lower
        for phrase in ("find contact", "search contact", "discover contact", "who can i message"):
            query = query.replace(phrase, "")
        return _plan(command, "contact_discovery", "CommunicationAgent", "read_only", (
            PlanStep(1, "find_contact", {"query": query.strip() or "doctor"}, "Find policy-permitted contacts."),
        ))
    if any(text in lower for text in ("share report", "send report", "share medical record")):
        return _plan(command, "record_share_request", "CommunicationAgent", "consent_required", (), requires_confirmation=True)
    if "share video" in lower:
        return _plan(command, "video_share", "CommunicationAgent", "low_risk", (), requires_confirmation=True)
    if any(text in lower for text in ("unread message", "check message", "my message", "inbox")):
        return _plan(command, "messages_inbox", "CommunicationAgent", "read_only", (
            PlanStep(1, "get_unread_summary", {}, "Count unread messages without reading clinical content."),
        ))
    if any(text in lower for text in ("video consultation", "doctor video", "consultation", "telehealth")):
        return _plan(command, "telehealth_request", "DoctorAgent", "low_risk", ())
    if "video" in lower:
        return _plan(command, "video_intelligence", "VideoAgent", "read_only", (
            PlanStep(1, "search_educational_video", {"query": command, "category": _video_category(lower)}, "Search truthful educational guidance."),
        ))
    if any(text in lower for text in ("device", "iot", "blood pressure", "heart rate")):
        return _plan(command, "iot_status", "IoTAgent", "read_only", (
            PlanStep(1, "get_iot_devices", {}, "List the authenticated user's device records."),
        ))
    if any(text in lower for text in ("home care", "nurse", "parent")):
        return _plan(command, "care_coordination", "CareAgent", "consent_required", ())

    return _plan(command, "general_agent", "SearchAgent", "read_only", ())


def _plan(command, intent, agent, risk, steps, *, requires_confirmation=False, safety=None, urgency="routine"):
    definition = choose_agent_for_intent(intent)
    assigned_agent = definition.identifier if definition else agent
    return AgentPlan(
        plan_id=uuid.uuid4().hex,
        command=command,
        intent=intent,
        urgency=urgency,
        assigned_agent=assigned_agent,
        risk_level=risk,
        steps=tuple(steps),
        requires_confirmation=requires_confirmation,
        safety=safety or {},
    )


def _unauthorized(command, intent):
    return AgentPlan(
        plan_id=uuid.uuid4().hex,
        command=command,
        intent=intent,
        urgency="routine",
        assigned_agent="OperationsAgent",
        risk_level="owner_approval",
        steps=(),
        authorization_error="This operation is restricted to the ZENDOC owner.",
    )


def _video_category(text):
    if "device" in text or "iot" in text:
        return "device_setup"
    if "nutrition" in text or "diet" in text:
        return "nutrition"
    if "rehab" in text or "mobility" in text:
        return "rehabilitation"
    if "staff" in text or "training" in text:
        return "staff_training"
    if "doctor" in text or "patient education" in text:
        return "patient_education"
    return "fitness"
