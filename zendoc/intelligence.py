import time

from .ai import assistant_answer, doctor_prediction, mental_health_support
from .ai_provider import LocalFallbackProvider, configured_provider
from .ai_types import IntelligenceResult
from .fitness_coach import FitnessCoach
from .health_analytics import get_health_trend
from .health_profile import get_health_profile
from .health_timeline import list_timeline
from .intent import IntentRouter
from .report_intelligence import explain_report, latest_report
from .safety import SafetyEngine


def row_get(row, key, default=None):
    if not row:
        return default
    if hasattr(row, "keys") and key in row.keys():
        return row[key]
    if isinstance(row, dict):
        return row.get(key, default)
    return default


FUTURE_ACTIONS = {
    "doctor": ("find_healthcare", "Search verified ZENDOC providers or configured external places."),
    "hospital": ("find_healthcare", "Search hospitals through the healthcare finder."),
    "clinic": ("find_healthcare", "Search clinics through the healthcare finder."),
    "pharmacy": ("find_healthcare", "Search pharmacies through the healthcare finder."),
    "medicine": ("medicine_intelligence", "Medicine information and reminders will connect here in a later milestone."),
}

HEALTH_MEMORY_INTENTS = {
    "health_timeline", "health_records", "report_history", "report_intelligence",
    "medical_report", "health_analytics", "health_monitoring", "health_profile",
}

FITNESS_INTENTS = {
    "fitness_coach", "fitness", "workout_plan", "workout_session",
    "exercise_instruction", "exercise", "fitness_video_search",
    "fitness_analytics", "nutrition_general", "nutrition", "hydration",
}

SPECIALTY_KEYWORDS = {
    "cardiologist": "Cardiology",
    "heart": "Cardiology",
    "skin": "Dermatology",
    "dermatologist": "Dermatology",
    "neurologist": "Neurology",
    "bone": "Orthopedics",
    "orthopedic": "Orthopedics",
    "child": "Pediatrics",
    "pediatrician": "Pediatrics",
    "psychiatrist": "Psychiatry",
    "eye": "Ophthalmology",
    "ent": "ENT",
}


class ZendocIntelligence:
    def __init__(self, provider=None, intent_router=None, safety_engine=None):
        self.provider = provider or configured_provider()
        self.intent_router = intent_router or IntentRouter()
        self.safety_engine = safety_engine or SafetyEngine()
        self._fitness_coach = FitnessCoach()

    def respond(self, message, user=None, conversation=None):
        started = time.perf_counter()
        clean_message = (message or "").strip()
        if not clean_message:
            return IntelligenceResult(
                intent="general_assistant",
                urgency="routine",
                message="Tell me what you need help with, such as symptoms, an appointment, reports, stress, fitness, or health monitoring.",
                follow_up_questions=["What would you like help with today?"],
                possible_actions=[],
            ), self._latency(started)
        if len(clean_message) > 4000:
            return IntelligenceResult(
                intent="general_assistant",
                urgency="routine",
                message="That message is too long for one request. Please summarize the main health concern or task.",
                follow_up_questions=["What is the most important thing you want ZENDOC to help with first?"],
                possible_actions=[],
                success=False,
            ), self._latency(started)

        safety = self.safety_engine.assess(clean_message)
        detected_intent = self.intent_router.detect(clean_message)
        previous_intent = row_get(conversation, "last_intent")
        if detected_intent == "general_assistant" and previous_intent in {"symptoms", "mental_wellness", "sleep"}:
            detected_intent = previous_intent
        intent = "emergency" if safety["emergency"] else detected_intent

        # SAFETY ALWAYS FIRST — emergency check NEVER skipped
        if safety["emergency"]:
            result = IntelligenceResult(
                intent=intent,
                urgency="emergency",
                message=f"{safety['reason']} {safety['guidance']}",
                follow_up_questions=[],
                possible_actions=[{"type": "emergency_care", "label": "Seek urgent care now"}, {"type": "future_nearby_emergency", "label": "Find nearby emergency facilities"}],
                specialist="Emergency medicine",
                emergency=True,
                provider="deterministic_safety",
                next_step="Stop chat and seek urgent medical evaluation.",
            )
            return result, self._latency(started)

        context = self._context(user, conversation, intent)
        if intent == "symptoms":
            result = self._symptom_guidance(clean_message, context)
        elif intent == "appointment":
            result = self._appointment_guidance(clean_message)
        elif intent == "mental_wellness" or intent == "sleep":
            result = self._mental_guidance(clean_message, intent)
        elif intent in HEALTH_MEMORY_INTENTS:
            result = self._health_memory_action(intent, clean_message, user)
        elif intent in FITNESS_INTENTS:
            result = self._fitness_action(intent, clean_message, user)
        elif intent in FUTURE_ACTIONS:
            result = self._future_action(intent, clean_message)
        else:
            result = self._provider_guidance(clean_message, context)
        result.conversation_id = row_get(conversation, "id")
        return result, self._latency(started)

    def _symptom_guidance(self, message, context):
        if context.get("recent_topic") == "symptoms" and not any(keyword in message.lower() for keyword in ("fever", "cough", "pain", "rash", "headache", "nausea", "fatigue")):
            return IntelligenceResult(
                intent="symptoms",
                urgency="routine",
                message="Thanks, that timing helps. Symptoms lasting several days can have many causes, so it is worth watching severity, hydration, temperature, and any new symptoms. I cannot confirm a diagnosis from this alone.",
                follow_up_questions=["Do you have fever, cough, pain, rash, vomiting, breathing trouble, or worsening weakness?"],
                possible_actions=[{"type": "appointment", "label": "Book a consultation"}, {"type": "health_monitor", "label": "Record temperature or symptoms"}],
                specialist="Primary care clinician",
                provider="conversation_context",
                next_step="Share associated symptoms or book a consultation if it persists or worsens.",
            )
        prediction = doctor_prediction(message)
        questions = []
        lower = message.lower()
        if not any(word in lower for word in ("day", "days", "hour", "hours", "week")):
            questions.append("How long have you had this?")
        if "fever" in lower and "temperature" not in lower:
            questions.append("Do you know your temperature?")
        if not questions:
            questions.append("Is anything making it better or worse?")
        return IntelligenceResult(
            intent="symptoms",
            urgency=prediction["risk_level"] if prediction["risk_level"] in {"low", "medium"} else "urgent",
            message=f"{prediction['summary']}. This is not a confirmed diagnosis. {prediction['next_steps']}",
            follow_up_questions=questions,
            possible_actions=[{"type": "appointment", "label": "Book a consultation"}, {"type": "medical_records", "label": "Upload related reports"}],
            specialist=self._specialist_for(message),
            provider="deterministic_health_guidance",
            next_step="Share the follow-up details or book an appointment if symptoms persist.",
        )

    def _appointment_guidance(self, message):
        return IntelligenceResult(
            intent="appointment",
            urgency="routine",
            message="You can request an appointment in ZENDOC. Tell me the specialty or provider you prefer, or open Appointments to book directly.",
            follow_up_questions=["What type of doctor or provider do you want to see?"],
            possible_actions=[{"type": "appointment", "label": "Open appointments"}],
            provider="local_orchestrator",
        )

    def _mental_guidance(self, message, intent):
        support = mental_health_support("general", message, 5)
        return IntelligenceResult(
            intent=intent,
            urgency=support["risk_level"],
            message=f"{support['summary']} I am not a therapist, but I can help you organize next steps and track wellbeing.",
            follow_up_questions=["Is this mainly about sleep, studies, work, loneliness, or general stress?"],
            possible_actions=[{"type": "mental_wellness", "label": "Continue mental wellness check-in"}],
            provider="deterministic_wellness_guidance",
            next_step=support["next_steps"],
        )

    def _future_action(self, intent, message=""):
        action_type, detail = FUTURE_ACTIONS[intent]
        category = intent
        if intent == "doctor":
            category = "doctor"
        elif intent == "pharmacy":
            category = "pharmacy"
        return IntelligenceResult(
            intent=intent,
            urgency="routine",
            message=f"I understand this as {intent.replace('_', ' ')}. {detail}",
            follow_up_questions=[],
            possible_actions=[{"type": action_type, "label": detail, "category": category, "specialty": self._specialty_from_text(message) if intent == "doctor" else None}],
            provider="intent_router",
            next_step="This intent is routed and ready for a future specialized service.",
        )

    def _fitness_action(self, intent, message, user):
        """
        Route to FitnessCoach.  Safety check has ALREADY run before this is called.
        Emergency messages never reach here — they return before the routing decision.
        """
        return self._fitness_coach.handle(intent, message, user)

    def _health_memory_action(self, intent, message, user):
        if not user:
            return IntelligenceResult(
                intent=intent,
                urgency="routine",
                message="Log in to access your private ZENDOC health history.",
                follow_up_questions=[],
                possible_actions=[{"type": "login", "label": "Log in"}],
                provider="authorized_health_services",
            )
        try:
            if intent in {"health_timeline", "health_records"}:
                timeline = list_timeline(user, page=1, per_page=5)
                count = timeline["total"]
                message_text = f"Your private health timeline contains {count} event{'s' if count != 1 else ''}."
                if timeline["events"]:
                    latest = timeline["events"][0]
                    message_text += f" The latest is {latest['title']} on {latest['event_at'][:10]}."
                else:
                    message_text += " Appointments, reports, and measurements will appear there as you add them."
                return IntelligenceResult(
                    intent="health_timeline",
                    urgency="routine",
                    message=message_text,
                    follow_up_questions=[],
                    possible_actions=[{"type": "health_timeline", "label": "Open My Health Timeline"}],
                    provider="authorized_health_services",
                    next_step="Open your timeline to search, filter, or review details.",
                )
            if intent in {"report_history", "medical_report"}:
                report = latest_report(user)
                if not report:
                    message_text = "You do not have a medical report stored yet. You can upload one securely from Medical Records."
                else:
                    message_text = f"Your latest stored report is {report['title']} dated {report['document_date'][:10]}."
                return IntelligenceResult(
                    intent="report_history",
                    urgency="routine",
                    message=message_text,
                    follow_up_questions=[],
                    possible_actions=[{"type": "report_history", "label": "Open Medical Records"}],
                    provider="authorized_health_services",
                )
            if intent == "report_intelligence":
                report = latest_report(user, report_type="blood_test") or latest_report(user)
                if not report:
                    message_text = "I cannot explain a report because no authorized report is stored in your account."
                    action = {"type": "report_history", "label": "Upload a report"}
                else:
                    explanation = explain_report(user, report["id"])
                    message_text = f"{report['title']}: {explanation['message']} {explanation['disclaimer']}"
                    action = {"type": "report_intelligence", "label": "View report details", "record_id": report["id"]}
                return IntelligenceResult(
                    intent="report_intelligence",
                    urgency="routine",
                    message=message_text,
                    follow_up_questions=[],
                    possible_actions=[action],
                    provider="authorized_health_services",
                    next_step="Discuss report findings and supplied reference ranges with a qualified clinician.",
                )
            if intent in {"health_analytics", "health_monitoring"}:
                metric_type = self._metric_from_text(message)
                trend = get_health_trend(user, metric_type, period="90d")
                point_count = sum(len(series["points"]) for series in trend["series"])
                message_text = f"I found {point_count} {metric_type.replace('_', ' ')} measurement{'s' if point_count != 1 else ''} in the last 90 days."
                if not point_count:
                    message_text += " Add a measurement to begin a truthful trend view."
                return IntelligenceResult(
                    intent="health_analytics",
                    urgency="routine",
                    message=message_text,
                    follow_up_questions=[],
                    possible_actions=[{"type": "health_analytics", "label": "Open Health Monitoring", "metric_type": metric_type}],
                    provider="authorized_health_services",
                )
            profile = get_health_profile(user)
            medicines = profile["current_medications"]
            if medicines:
                message_text = "Your health profile lists: " + ", ".join(medicines[:10]) + "."
            else:
                message_text = "Your health profile does not list any current medications. This does not mean you have none; update the profile if needed."
            return IntelligenceResult(
                intent="health_profile",
                urgency="routine",
                message=message_text,
                follow_up_questions=[],
                possible_actions=[{"type": "health_profile", "label": "Open My Health Profile"}],
                provider="authorized_health_services",
            )
        except (LookupError, PermissionError, RuntimeError, ValueError):
            return IntelligenceResult(
                intent=intent,
                urgency="routine",
                message="I could not access that private health information for this account. Open the relevant ZENDOC page or check your access permissions.",
                follow_up_questions=[],
                possible_actions=[],
                provider="authorized_health_services",
                success=False,
            )

    def _provider_guidance(self, message, context):
        try:
            provider_response = self.provider.complete(message, context)
        except Exception:
            provider_response = LocalFallbackProvider().complete(message, context)
            provider_response.success = False
        return IntelligenceResult(
            intent=context["intent"],
            urgency="routine",
            message=provider_response.text or assistant_answer(message),
            follow_up_questions=["Would you like help with symptoms, appointments, reports, stress, medicines, fitness, or records?"],
            possible_actions=[{"type": "assistant", "label": "Continue conversation"}],
            provider=provider_response.provider,
            success=provider_response.success,
        )

    def _context(self, user, conversation, intent):
        return {
            "intent": intent,
            "user_age": user["age"] if user and "age" in user.keys() else None,
            "user_role": user["role"] if user and "role" in user.keys() else None,
            "recent_topic": row_get(conversation, "last_intent"),
        }

    def _specialist_for(self, message):
        text = message.lower()
        if "chest" in text or "heart" in text:
            return "Cardiology"
        if "rash" in text or "skin" in text:
            return "Dermatology"
        if "stress" in text or "sleep" in text:
            return "Mental wellness professional"
        return "Primary care clinician"

    def _specialty_from_text(self, message):
        text = message.lower()
        for keyword, specialty in SPECIALTY_KEYWORDS.items():
            if keyword in text:
                return specialty
        return None

    def _metric_from_text(self, message):
        text = message.lower()
        if "blood pressure" in text or " bp" in f" {text}":
            return "blood_pressure"
        if "glucose" in text or "sugar" in text:
            return "blood_glucose"
        if "bmi" in text:
            return "bmi"
        if "sleep" in text:
            return "sleep"
        if "step" in text or "activity" in text:
            return "steps"
        return "weight"

    def _latency(self, started):
        return int((time.perf_counter() - started) * 1000)
