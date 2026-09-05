"""Specialized ZENDOC AI experiences.

The product exposes several assistants with distinct responsibilities instead of
pretending that every request is the same chatbot:

- ZENDOC AI: top-level care/platform orchestrator (implemented in intelligence.py)
- Doctor AI: safety-first symptom and medicine education, never a licensed doctor
- Mental Wellness AI: structured wellbeing support, never a therapist
- General Assistant: local-first/general LLM assistant for non-clinical tasks

All modes remain behind the deterministic SafetyEngine.  None of these helpers
can execute tools or bypass consent/authorization.
"""
from __future__ import annotations

import re

from .ai_types import IntelligenceResult
from .local_ai_provider import FORBIDDEN_ACTION_KEYS
from .model_router import PrivacyClass, RiskClass, get_model_router
from .safety import SafetyEngine
from .slm import classify_privacy


AI_MODES = {
    "zendoc": {
        "label": "ZENDOC AI",
        "short_label": "Boss AI",
        "description": "Coordinates care, records, providers, family workflows and the safest next action.",
        "accent": "orchestrator",
    },
    "doctor": {
        "label": "Doctor AI",
        "short_label": "Clinical Guidance",
        "description": "Focused symptom, medicine and care guidance with emergency-first safety checks.",
        "accent": "doctor",
    },
    "mental": {
        "label": "Mental Wellness AI",
        "short_label": "Wellbeing Support",
        "description": "Focused support for stress, sleep, overwhelm and emotional wellbeing.",
        "accent": "mental",
    },
    "assistant": {
        "label": "General Assistant",
        "short_label": "Everyday AI",
        "description": "A general local/cloud LLM assistant for writing, learning, coding and everyday questions.",
        "accent": "assistant",
    },
}
DEFAULT_AI_MODE = "zendoc"


def normalize_ai_mode(value: str | None) -> str:
    mode = str(value or DEFAULT_AI_MODE).strip().lower()
    return mode if mode in AI_MODES else DEFAULT_AI_MODE


def ai_mode_profile(mode: str | None) -> dict:
    key = normalize_ai_mode(mode)
    return {"key": key, **AI_MODES[key]}


def _bounded_context(messages, limit: int = 3) -> list[str]:
    cleaned = [str(item or "").strip()[:500] for item in (messages or []) if str(item or "").strip()]
    return cleaned[-max(1, min(int(limit or 3), 4)):]


def doctor_ai_response(message: str, *, recent_user_messages=None) -> IntelligenceResult:
    """Return bounded, non-diagnostic clinical guidance.

    This is intentionally deterministic.  ZENDOC may provide common
    non-prescription medicine education but does not choose a prescription,
    dose, antibiotic, or treatment plan for a patient.
    """
    text = str(message or "").strip()
    context_messages = _bounded_context(recent_user_messages)
    combined_text = " ".join([*context_messages, text]).strip()
    safety = SafetyEngine().assess(combined_text)
    if safety["emergency"]:
        return IntelligenceResult(
            intent="emergency",
            urgency="emergency",
            message=f"{safety['reason']} {safety['guidance']}",
            emergency=True,
            provider="deterministic_safety",
            specialist="Emergency medicine",
            possible_actions=[
                {"type": "emergency_care", "label": "Seek urgent care now"},
                {"type": "future_nearby_emergency", "label": "Find nearby emergency care"},
            ],
            follow_up_questions=[],
            next_step="Do not wait for Doctor AI; seek urgent professional care.",
            model_metadata={"assistant_mode": "doctor", "model_called": False},
        )

    lower = combined_text.lower()
    prescription_request = any(
        phrase in lower
        for phrase in (
            "which antibiotic", "give me antibiotic", "prescribe", "prescription medicine",
            "change my dose", "change dosage", "stop my medicine", "increase my dose",
        )
    )

    tips: list[str] = []
    medicine_note = None
    urgency = "routine"
    specialist = "Primary care clinician"

    if any(word in lower for word in ("fever", "headache", "body ache", "body pain")):
        tips.extend([
            "Rest, drink fluids, and monitor temperature and worsening symptoms.",
            "A common non-prescription option for fever or pain is paracetamol/acetaminophen for people who can safely take it; follow the product label and confirm suitability with a pharmacist or clinician.",
        ])
    if any(word in lower for word in ("vomit", "vomiting", "diarrhea", "dehydration")):
        tips.extend([
            "Take small, frequent fluids if you can keep them down.",
            "Oral rehydration solution (ORS) is commonly used to replace fluids and salts during dehydration; use a properly prepared product and seek care if you cannot keep fluids down.",
        ])
    if any(word in lower for word in ("cough", "cold", "sore throat")):
        if "fever" in lower and "cough" in lower:
            tips.append(
                "Possible respiratory infection: fever and cough can occur with respiratory infections, but Doctor AI cannot diagnose the cause from chat alone."
            )
        tips.extend([
            "Warm fluids, rest, and avoiding smoke may help mild respiratory symptoms.",
            "Cough/cold combination medicines are not suitable for everyone, especially young children or people taking interacting medicines; a pharmacist can help choose an appropriate non-prescription product.",
        ])
    if any(word in lower for word in ("allergy", "itch", "sneezing", "runny nose")):
        medicine_note = (
            "For some mild allergy symptoms, non-prescription antihistamines such as cetirizine are commonly used, "
            "but suitability varies and some products can cause drowsiness. Check the label and ask a pharmacist or clinician."
        )
    if any(word in lower for word in ("ibuprofen", "nsaid")):
        medicine_note = (
            "Ibuprofen is a non-steroidal anti-inflammatory medicine used for pain/fever by some people, but it can be unsuitable "
            "with stomach ulcers, kidney disease, some blood thinners, pregnancy, or other conditions. Confirm suitability before use."
        )
    if any(word in lower for word in ("paracetamol", "acetaminophen")):
        medicine_note = (
            "Paracetamol/acetaminophen is commonly used for pain or fever. Follow the product label and avoid combining multiple products "
            "that contain the same ingredient; liver disease or other medicines can change what is safe."
        )
    if any(word in lower for word in ("rash", "skin")):
        specialist = "Dermatology or primary care clinician"
    if any(word in lower for word in ("heart", "palpitation")):
        specialist = "Primary care clinician or cardiology, depending on assessment"
    if any(word in lower for word in ("persistent", "worsening", "severe", "many days", "week")):
        urgency = "prompt"

    if prescription_request:
        message_text = (
            "I can explain medicines and common non-prescription options, but I cannot select an antibiotic, prescribe a medicine, "
            "or change a dose for you. Those decisions need a licensed clinician who can review your history, allergies, examination, and current medicines."
        )
    elif tips or medicine_note:
        parts = ["Based on what you wrote, I can offer general educational guidance rather than a diagnosis."]
        if tips:
            parts.append(" ".join(dict.fromkeys(tips)))
        if medicine_note:
            parts.append(medicine_note)
        parts.append(
            "If symptoms are severe, worsening, unusual for you, or not improving, arrange professional assessment."
        )
        message_text = " ".join(parts)
    else:
        message_text = (
            "Tell me the main symptom, how long it has been happening, how severe it is, your age group, and any important medicines, allergies, "
            "pregnancy, or long-term conditions. I can then give safer educational next steps without pretending to diagnose you."
        )

    return IntelligenceResult(
        intent="doctor_ai",
        urgency=urgency,
        message=message_text,
        guidance=message_text,
        summary="Doctor AI clinical guidance",
        follow_up_questions=[
            "How long has this been happening and is it getting better or worse?",
            "Are you taking any regular medicines or do you have important allergies or long-term conditions?",
        ],
        possible_actions=[
            {"type": "telehealth", "label": "Request real clinician consultation"},
            {"type": "appointment", "label": "Find a clinician"},
            {"type": "medical_records", "label": "Review related reports"},
        ],
        specialist=specialist,
        provider="doctor_ai_deterministic",
        next_step="Add the missing clinical context or request a real clinician consultation.",
        safety_notice=(
            "Doctor AI is not a licensed doctor and does not diagnose or prescribe. "
            "A real clinician consultation is a separate provider workflow."
        ),
        model_metadata={
            "assistant_mode": "doctor",
            "clinical_boundary": "educational_only",
            "model_called": False,
            "conversation_context_used": bool(context_messages),
            "context_messages_used": len(context_messages),
        },
    )


def mental_wellness_ai_response(message: str, *, recent_user_messages=None) -> IntelligenceResult:
    text = str(message or "").strip()
    context_messages = _bounded_context(recent_user_messages)
    combined_text = " ".join([*context_messages, text]).strip()
    safety = SafetyEngine().assess(combined_text)
    if safety["emergency"]:
        return IntelligenceResult(
            intent="emergency",
            urgency="emergency",
            message=f"{safety['reason']} {safety['guidance']}",
            emergency=True,
            provider="deterministic_safety",
            possible_actions=[{"type": "emergency_care", "label": "Seek urgent support now"}],
            follow_up_questions=[],
            model_metadata={"assistant_mode": "mental", "model_called": False},
        )

    lower = combined_text.lower()
    suggestions = []
    if any(word in lower for word in ("stress", "overwhelmed", "exam", "work", "burnout")):
        suggestions.extend([
            "Reduce the next hour to one small task rather than trying to solve everything at once.",
            "Try a short slow-breathing or grounding break, drink some water, and move away from the screen for a few minutes if possible.",
        ])
    if any(word in lower for word in ("sleep", "insomnia", "tired")):
        suggestions.extend([
            "Keep a consistent wake time, reduce late caffeine, and make the last part of the evening lower stimulation.",
            "If sleep problems persist or significantly affect daytime functioning, a clinician can help assess causes and treatment options.",
        ])
    if any(word in lower for word in ("lonely", "alone", "sad", "upset")):
        suggestions.append(
            "Consider contacting one trusted person and saying clearly that you would like company or support; you do not need to explain everything at once."
        )
    if not suggestions:
        suggestions = [
            "Name the main feeling and the situation connected to it, then choose one manageable action for the next 10–20 minutes.",
            "Basic routines such as hydration, food, movement, sleep, and contact with trusted people can support wellbeing while you decide whether professional help would be useful.",
        ]

    message_text = (
        "I can support you with structured wellbeing steps, but I am not a therapist and I will not label you with a mental-health diagnosis. "
        + " ".join(dict.fromkeys(suggestions))
    )
    return IntelligenceResult(
        intent="mental_wellness",
        urgency="routine",
        message=message_text,
        guidance=message_text,
        summary="Mental Wellness AI support",
        follow_up_questions=[
            "What feels hardest right now: stress, sleep, loneliness, studies/work, or something else?",
            "Would you prefer a calming exercise, a small action plan, or help finding professional support?",
        ],
        possible_actions=[
            {"type": "mental_wellness", "label": "Continue wellbeing check-in"},
            {"type": "appointment", "label": "Find professional support"},
        ],
        specialist="Mental health professional when professional care is needed",
        provider="mental_wellness_ai_deterministic",
        next_step="Choose one small next step or tell me what kind of support would help.",
        safety_notice="Mental Wellness AI is supportive guidance, not therapy or a diagnosis.",
        model_metadata={
            "assistant_mode": "mental",
            "model_called": False,
            "conversation_context_used": bool(context_messages),
            "context_messages_used": len(context_messages),
        },
    )


_ACTION_CLAIM_RE = re.compile(
    r"\b(?:i|we|the assistant|zendoc)\s+(?:have\s+)?(?:booked|ordered|sent|shared|uploaded|dispatched|prescribed|confirmed|deleted|paid)\b",
    re.IGNORECASE,
)


def _contains_forbidden_action_key(value, depth: int = 0) -> bool:
    if depth > 6:
        return True
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).strip().lower() in FORBIDDEN_ACTION_KEYS:
                return True
            if _contains_forbidden_action_key(item, depth + 1):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_action_key(item, depth + 1) for item in value[:100])
    return False


def general_assistant_response(message: str, *, router=None, recent_user_messages=None) -> IntelligenceResult:
    """Use the configured model router for non-clinical general assistance.

    PUBLIC/INTERNAL tasks may use a configured cloud provider. PERSONAL data is
    local-only. HEALTH_SENSITIVE/HIGH_RISK requests are redirected to the
    healthcare-specific modes instead of being sent to a general model.
    """
    text = str(message or "").strip()[:4000]
    context_messages = _bounded_context(recent_user_messages)
    safety = SafetyEngine().assess(text)
    if safety["emergency"]:
        return IntelligenceResult(
            intent="emergency",
            urgency="emergency",
            message=f"{safety['reason']} {safety['guidance']}",
            emergency=True,
            provider="deterministic_safety",
            possible_actions=[{"type": "emergency_care", "label": "Seek urgent care now"}],
            follow_up_questions=[],
            model_metadata={"assistant_mode": "assistant", "model_called": False},
        )

    privacy = classify_privacy(text, "general_assistant")
    if privacy in {PrivacyClass.HEALTH_SENSITIVE, PrivacyClass.HIGH_RISK}:
        message_text = (
            "This looks health-related, so I am not sending it through the general assistant. "
            "Use Doctor AI for symptom or medicine guidance, or ZENDOC AI when you want your authorized health context and care workflows."
        )
        return IntelligenceResult(
            intent="general_assistant",
            urgency="routine",
            message=message_text,
            provider="privacy_router",
            success=True,
            possible_actions=[
                {"type": "switch_ai_mode", "mode": "doctor", "label": "Open Doctor AI"},
                {"type": "switch_ai_mode", "mode": "zendoc", "label": "Open ZENDOC AI"},
            ],
            follow_up_questions=[],
            safety_notice="Health-sensitive requests are kept out of the general assistant path.",
            model_metadata={"assistant_mode": "assistant", "model_called": False, "privacy_class": privacy},
        )

    allow_cloud = privacy in {PrivacyClass.PUBLIC, PrivacyClass.INTERNAL}
    prompt = text
    if context_messages:
        context_block = "\n".join(
            f"Earlier user message {index + 1}: {item}"
            for index, item in enumerate(context_messages)
        )
        prompt = (
            "Use the recent same-thread user context only when it is relevant. "
            "Do not infer facts that were not stated.\n"
            f"{context_block}\nCurrent user message: {text}"
        )[:6000]
    response = (router or get_model_router()).route(
        prompt,
        intent="general_assistant",
        task_type="general_assistant",
        privacy_class=privacy,
        risk_class=RiskClass.READ_ONLY,
        allow_cloud=allow_cloud,
        cloud_consent=allow_cloud,
        structured_output_required=True,
        system_prompt=(
            "You are ZENDOC General Assistant, a useful general-purpose assistant for learning, writing, coding, planning and everyday questions. "
            "Do not diagnose or prescribe. Do not claim that you executed code, sent messages, changed records, booked services, paid, or used tools. "
            "Return a concise structured advisory response."
        ),
    )

    output = response.output if isinstance(response.output, dict) else {}
    answer = output.get("text") if isinstance(output.get("text"), str) else ""
    safe = bool(answer.strip()) and not _ACTION_CLAIM_RE.search(answer) and not _contains_forbidden_action_key(output.get("data", {}))
    if not safe:
        answer = (
            "I could not safely use the configured model response. I can still help with ZENDOC navigation, "
            "or you can retry after the local/cloud model runtime is configured and healthy."
        )

    return IntelligenceResult(
        intent="general_assistant",
        urgency="routine",
        message=answer.strip(),
        guidance=answer.strip(),
        summary="General Assistant",
        follow_up_questions=["What would you like to work on next?"],
        possible_actions=[{"type": "assistant", "label": "Continue conversation"}],
        provider=response.provider,
        success=bool(response.success and safe),
        next_step="Continue with a non-clinical question.",
        safety_notice="General Assistant does not execute tools or provide medical diagnosis/prescribing.",
        provider_route={
            "provider": response.provider,
            "model": response.model,
            "routing_reason": response.routing_reason,
            "privacy_class": privacy,
            "fallback_used": response.fallback_used,
            "fallback_reason": response.fallback_reason,
        },
        model_metadata={
            "assistant_mode": "assistant",
            "model_called": response.provider not in {"local_fallback", "deterministic_safety"},
            "structured_output_validated": safe,
            "cloud_allowed_for_this_request": allow_cloud,
            "conversation_context_used": bool(context_messages),
            "context_messages_used": len(context_messages),
        },
    )
