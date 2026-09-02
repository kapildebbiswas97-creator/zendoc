"""ZENDOC-SLM v1 product layer.

This module is the product-facing language intelligence boundary.  It is not a
claim that ZENDOC trained a proprietary medical model.  The layer owns the
approved product context, deterministic privacy/task policy, model routing,
structured-output normalization, and post-generation safety validation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .local_ai_provider import FORBIDDEN_ACTION_KEYS
from .model_router import PrivacyClass, RiskClass, get_model_router, normalize_privacy_class
from .safety import SafetyEngine


SLM_VERSION = "zendoc-slm-v1"
SLM_DISPLAY_NAME = "ZENDOC-SLM v1 — healthcare-focused local model layer"
KNOWLEDGE_LAYER_VERSION = "zendoc-approved-knowledge-v1"


# Repository-owned, human-authored product facts only.  These records are
# deliberately small and provenance-bearing; this is not a general web RAG
# index and it is not a clinical knowledge base.
APPROVED_KNOWLEDGE = (
    {
        "knowledge_id": "product.dashboard",
        "topic": "platform_navigation",
        "text": "The ZENDOC dashboard is the starting point for care activity, notifications, and the next useful action.",
        "provenance": "zendoc_product_spec:m9",
        "approved_use": "platform_navigation",
    },
    {
        "knowledge_id": "product.appointments",
        "topic": "appointments",
        "text": "Appointments lets an authenticated patient find a provider, review published availability, and submit a request.",
        "provenance": "zendoc_product_spec:m9",
        "approved_use": "platform_navigation",
    },
    {
        "knowledge_id": "product.finder",
        "topic": "provider_discovery",
        "text": "Find Care displays provider profiles from the configured ZENDOC directory; availability and verification are shown only when stored.",
        "provenance": "zendoc_product_spec:m9",
        "approved_use": "care_navigation",
    },
    {
        "knowledge_id": "product.health_memory",
        "topic": "health_memory",
        "text": "Health Memory organizes authorized reports, measurements, appointments, and care activity into a private timeline.",
        "provenance": "zendoc_product_spec:m9",
        "approved_use": "health_navigation",
    },
    {
        "knowledge_id": "product.messaging",
        "topic": "communication",
        "text": "Messages and telehealth requests remain subject to account roles, consent, provider availability, and doctor acceptance.",
        "provenance": "zendoc_product_spec:m9",
        "approved_use": "care_navigation",
    },
    {
        "knowledge_id": "product.boundaries",
        "topic": "truthful_capabilities",
        "text": "Telehealth, live device sync, medical transport dispatch, external video search, and external notification delivery require the integrations shown in the capability matrix.",
        "provenance": "zendoc_capability_registry:m9",
        "approved_use": "capability_status",
    },
    {
        "knowledge_id": "safety.educational",
        "topic": "healthcare_safety",
        "text": "ZENDOC guidance is educational and does not confirm a diagnosis, prescribe treatment, or replace a qualified clinician.",
        "provenance": "zendoc_safety_policy:v1",
        "approved_use": "safety_notice",
    },
    {
        "knowledge_id": "safety.emergency",
        "topic": "emergency",
        "text": "When emergency warning signs are detected, contact local emergency services or the nearest emergency department and do not wait for an AI response.",
        "provenance": "zendoc_safety_policy:v1",
        "approved_use": "emergency_deferral",
    },
)

_STOP_WORDS = {"a", "an", "and", "are", "can", "do", "for", "i", "in", "is", "me", "my", "of", "the", "to", "what", "where", "with", "you"}
_HEALTH_SENSITIVE_TERMS = {
    "symptom", "symptoms", "fever", "cough", "pain", "rash", "blood", "report", "medical", "medicine",
    "medication", "prescription", "diagnosis", "health", "vital", "glucose", "pressure", "sleep", "stress",
}
_PERSONAL_TERMS = {"my", "mine", "me", "account", "profile", "record", "records", "timeline", "appointment"}
_UNSAFE_OUTPUT_PATTERNS = (
    re.compile(r"\b(?:you have|diagnosis is|prescription changed|take \d+\s?mg|stop taking)\b", re.I),
    re.compile(r"\b(?:i|we|zendoc)\s+(?:have\s+)?(?:booked|sent|uploaded|dispatched|prescribed|confirmed)\b", re.I),
)


@dataclass(frozen=True)
class SLMProductOutput:
    """Sanitized, UI/API-safe output from the product layer."""

    intent: str
    urgency: str
    emergency: bool
    summary: str
    guidance: str
    specialist: str | None
    follow_up_questions: tuple[str, ...]
    recommended_actions: tuple[dict, ...]
    provider_route: dict
    safety_notice: str
    model_metadata: dict

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "urgency": self.urgency,
            "emergency": self.emergency,
            "summary": self.summary,
            "guidance": self.guidance,
            "specialist": self.specialist,
            "follow_up_questions": list(self.follow_up_questions),
            "recommended_actions": [dict(action) for action in self.recommended_actions],
            "provider_route": dict(self.provider_route),
            "safety_notice": self.safety_notice,
            "model_metadata": dict(self.model_metadata),
        }


def retrieve_approved_knowledge(message: str, intent: str = "general_assistant", *, limit: int = 3) -> list[dict]:
    """Return only curated context records, including provenance metadata."""
    tokens = {token for token in re.findall(r"[a-z0-9_]+", str(message or "").lower()) if token not in _STOP_WORDS}
    intent_tokens = set(re.findall(r"[a-z0-9_]+", str(intent or "").lower()))
    scored = []
    for record in APPROVED_KNOWLEDGE:
        record_tokens = set(re.findall(r"[a-z0-9_]+", f"{record['topic']} {record['text']}".lower()))
        score = len(tokens & record_tokens) + (1 if intent_tokens & record_tokens else 0)
        if score:
            scored.append((score, record))
    scored.sort(key=lambda item: (-item[0], item[1]["knowledge_id"]))
    selected = [record for _score, record in scored[: max(1, min(int(limit), 5))]]
    if not selected:
        selected = [APPROVED_KNOWLEDGE[0], APPROVED_KNOWLEDGE[6]]
    return [dict(record, knowledge_layer=KNOWLEDGE_LAYER_VERSION) for record in selected]


def knowledge_layer_status() -> dict:
    return {
        "status": "WORKING",
        "version": KNOWLEDGE_LAYER_VERSION,
        "source_policy": "Curated ZENDOC product facts and approved synthetic safety guidance only.",
        "document_count": len(APPROVED_KNOWLEDGE),
        "provenance_required": True,
        "external_web_retrieval": False,
        "sensitive_prompt_storage": False,
    }


def classify_privacy(message: str, intent: str = "general_assistant") -> str:
    text = str(message or "").lower()
    intent = str(intent or "").lower()
    if intent == "emergency" or any(term in text for term in ("suicide", "kill myself", "chest pain", "shortness of breath")):
        return PrivacyClass.HIGH_RISK
    if intent in {"symptoms", "health_timeline", "health_records", "report_history", "report_intelligence", "health_analytics", "health_monitoring", "health_profile", "medical_report", "mental_wellness", "sleep"} or any(term in text for term in _HEALTH_SENSITIVE_TERMS):
        return PrivacyClass.HEALTH_SENSITIVE
    if intent in {"general_platform_question", "navigation_help"} and not any(term in text for term in _PERSONAL_TERMS):
        return PrivacyClass.PUBLIC
    if any(term in text for term in _PERSONAL_TERMS):
        return PrivacyClass.PERSONAL
    return normalize_privacy_class(PrivacyClass.INTERNAL)


def run_slm_product_layer(message: str, intent: str = "general_assistant", *, router=None) -> SLMProductOutput:
    """Run the safe product path; model output never provides executable actions."""
    clean_message = str(message or "").strip()[:4000]
    intent = str(intent or "general_assistant").strip().lower()[:100]
    safety = SafetyEngine().assess(clean_message)
    if safety["emergency"]:
        return _emergency_output(intent, safety)

    privacy_class = classify_privacy(clean_message, intent)
    knowledge = retrieve_approved_knowledge(clean_message, intent)
    prompt = _build_prompt(clean_message, intent, knowledge)
    response = (router or get_model_router()).route(
        prompt,
        intent=intent,
        task_type=_task_type(intent),
        allow_cloud=False,
        privacy_class=privacy_class,
        risk_class=RiskClass.READ_ONLY,
        structured_output_required=True,
        system_prompt=(
            f"You are the language component of {SLM_DISPLAY_NAME}. Use only the supplied approved context. "
            "Return advisory text; never diagnose, prescribe, expose private data, invoke tools, or claim an action occurred."
        ),
    )
    fallback_text = _deterministic_fallback(intent)
    text, structured_valid, safety_validated, validation_reason = _validate_model_text(response.output, fallback_text)
    used_fallback = bool(response.fallback_used or not structured_valid or not safety_validated)
    if used_fallback and validation_reason:
        fallback_reason = f"{response.fallback_reason or 'model_fallback'},{validation_reason}"
    else:
        fallback_reason = response.fallback_reason
    action = _recommended_action(intent)
    return SLMProductOutput(
        intent=intent,
        urgency="routine",
        emergency=False,
        summary=text,
        guidance=text,
        specialist=None,
        follow_up_questions=("Would you like help with another ZENDOC area?",),
        recommended_actions=(action,) if action else (),
        provider_route={
            "layer": SLM_VERSION,
            "provider": response.provider,
            "model": response.model,
            "routing_reason": response.routing_reason,
            "privacy_class": privacy_class,
            "fallback_used": used_fallback,
            "fallback_reason": fallback_reason,
            "knowledge_refs": [record["knowledge_id"] for record in knowledge],
        },
        safety_notice="Educational guidance only. ZENDOC does not diagnose, prescribe, or replace a qualified clinician.",
        model_metadata={
            "product_layer": SLM_VERSION,
            "component": "language_intelligence",
            "structured_output_validated": structured_valid,
            "safety_validated": safety_validated,
            "knowledge_layer": KNOWLEDGE_LAYER_VERSION,
            "provider_available": response.provider not in {"local_fallback", "cloud_llm"} and response.success,
        },
    )


def _build_prompt(message: str, intent: str, knowledge: list[dict]) -> str:
    context = "\n".join(f"[{record['knowledge_id']} | {record['provenance']}] {record['text']}" for record in knowledge)
    return (
        "Approved ZENDOC context (do not invent beyond it):\n"
        f"{context}\n\nIntent: {intent}\nUser request: {message}\n"
        "Return the required structured advisory envelope."
    )[:8000]


def _validate_model_text(output, fallback_text: str) -> tuple[str, bool, bool, str | None]:
    if not isinstance(output, dict) or set(output) - {"text", "data"} or not isinstance(output.get("data", {}), dict):
        return fallback_text, False, True, "structured_output_invalid"
    if _contains_forbidden_key(output.get("data", {})):
        return fallback_text, False, False, "executable_output_rejected"
    text = output.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > 12000:
        return fallback_text, False, True, "structured_output_invalid"
    if any(pattern.search(text) for pattern in _UNSAFE_OUTPUT_PATTERNS):
        return fallback_text, True, False, "unsafe_output_rejected"
    return text.strip(), True, True, None


def _contains_forbidden_key(value, depth: int = 0) -> bool:
    if depth > 6:
        return True
    if isinstance(value, dict):
        return any(
            str(key).strip().lower() in FORBIDDEN_ACTION_KEYS or _contains_forbidden_key(item, depth + 1)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_key(item, depth + 1) for item in value[:100])
    return False


def _emergency_output(intent: str, safety: dict) -> SLMProductOutput:
    return SLMProductOutput(
        intent="emergency",
        urgency="emergency",
        emergency=True,
        summary=safety["reason"],
        guidance=safety["guidance"],
        specialist="Emergency medicine",
        follow_up_questions=(),
        recommended_actions=({"type": "emergency_care", "label": "Seek urgent care now"},),
        provider_route={"layer": SLM_VERSION, "provider": "deterministic_safety", "routing_reason": "emergency_safety_gate", "privacy_class": PrivacyClass.HIGH_RISK},
        safety_notice="Emergency guidance is deterministic. Do not wait for an AI response.",
        model_metadata={"product_layer": SLM_VERSION, "component": "safety_gate", "model_called": False, "knowledge_layer": KNOWLEDGE_LAYER_VERSION},
    )


def _deterministic_fallback(intent: str) -> str:
    return {
        "general_assistant": "I can guide you through ZENDOC safely. Open the dashboard to choose AI guidance, Find Care, Appointments, or Health Memory.",
        "general_platform_question": "Open the ZENDOC dashboard to review care activity, then use Appointments or Health Memory for the relevant next step.",
        "core_agent": "ZENDOC Core Agent coordinates authorized workflows through permissions, registered tools, and audit logs; it does not bypass safety checks.",
        "appointment": "Use ZENDOC Appointments to review providers and request an available time. A request is not confirmed until the provider accepts it.",
        "doctor": "Use Find Care to review stored provider profiles and published availability. ZENDOC does not invent ratings or appointment slots.",
        "health_memory": "Open Health Memory to review authorized reports, measurements, appointments, and care activity in your private timeline.",
    }.get(intent, "I can guide you to the appropriate ZENDOC service and safe next step.")


def _recommended_action(intent: str) -> dict | None:
    if intent in {"appointment", "doctor", "hospital", "clinic", "pharmacy"}:
        return {"type": "find_healthcare", "label": "Open Find Care"}
    if intent in {"health_memory", "health_timeline", "health_records"}:
        return {"type": "health_timeline", "label": "Open Health Memory"}
    return {"type": "assistant", "label": "Continue with ZENDOC guidance"}


def _task_type(intent: str) -> str:
    return {
        "general_assistant": "general_platform_question",
        "general_platform_question": "general_platform_question",
        "core_agent": "owner_operational_summary",
        "appointment": "navigation_help",
        "doctor": "provider_discovery_query",
        "hospital": "provider_discovery_query",
        "clinic": "provider_discovery_query",
        "pharmacy": "provider_discovery_query",
        "health_memory": "navigation_help",
    }.get(intent, "general")
