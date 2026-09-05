"""Deterministic intent routing for ZENDOC.

Emergency handling belongs to SafetyEngine and runs before this router in the
central intelligence path.  This router therefore focuses on selecting the most
specific product workflow rather than treating words such as "ambulance" as an
automatic medical emergency.
"""
from __future__ import annotations

import re


INTENT_KEYWORDS = {
    "emergency": ("medical emergency", "life threatening emergency", "life-threatening emergency"),
    "orchestration_request": (
        "prescribed these medicines",
        "prescribed medicines",
        "best available way to get them",
        "get them near her home",
        "get them near his home",
        "get them near my home",
        "get them near home",
        "find the best available way",
        "orchestrate care",
        "fulfil my prescription",
        "fulfill my prescription",
        "fulfil prescription",
        "fulfill prescription",
        "order prescribed medicines",
        "find prescribed",
    ),
    "report_intelligence": (
        "explain my blood", "explain my report", "explain my latest report",
        "explain my lab", "interpret my report",
    ),
    "report_history": ("show my latest report", "show my report", "report history"),
    "health_timeline": ("show my health history", "my health history", "health timeline", "show my timeline"),
    "health_analytics": ("weight trend", "bmi trend", "glucose trend", "blood pressure history", "measurement trend"),
    "health_profile": ("what medicines am i taking", "my medications", "current medications", "my allergies"),
    "telehealth": ("video consultation", "voice call", "doctor chat", "request doctor chat", "telehealth", "consultation request"),
    "family_care": ("family", "my father", "my mother", "my parent", "my parents", "remote parent", "parent care", "dependent"),
    "home_health": ("nurse", "physiotherapy", "elder care", "home visit", "home health", "nurse for my", "doctor home visit"),
    "ambulance": ("ambulance", "transport", "icu van", "wheelchair van", "hospital transfer", "patient transport"),
    "pharmacy": ("pharmacy", "chemist", "medicine delivery", "refill", "prescribe", "pill"),
    "appointment": ("appointment", "book", "schedule", "visit"),
    "doctor": ("doctor", "specialist", "cardiologist", "dermatologist", "physician"),
    "hospital": ("hospital", "emergency room", "nearest hospital"),
    "clinic": ("clinic",),
    "medicine": ("medicine", "medication", "tablet", "drug", "prescription"),
    "medical_report": ("report", "blood test", "lab", "scan", "xray", "mri"),
    "health_records": ("records", "history", "previous reports"),
    "workout_plan": (
        "make a workout", "create a plan", "give me a plan", "workout plan",
        "generate plan", "my plan", "new plan", "today's workout", "todays workout",
        "workout for today", "beginner workout", "home workout plan",
        "gym workout plan", "plan for me",
    ),
    "workout_session": (
        "start workout", "begin workout", "record workout", "log workout",
        "i worked out", "just finished workout", "completed workout",
        "done with workout", "i trained", "did my workout",
    ),
    "exercise_instruction": (
        "how to squat", "how to do", "show me how", "explain squat",
        "teach me", "squat form", "push-up form", "pushup form",
        "deadlift form", "how do i do", "correct form", "tutorial",
        "exercise instructions", "how to plank",
    ),
    "fitness_video_search": (
        "find a video", "show me a video", "video for", "workout video",
        "find squat video", "find a yoga video", "fitness video",
        "exercise video", "tutorial video", "youtube workout",
    ),
    "fitness_analytics": (
        "how many workouts", "workout history", "fitness progress",
        "my workouts", "training history", "what did i train",
        "weekly workout", "workout streak", "activity this week",
    ),
    "nutrition_general": (
        "what should i eat", "after workout food", "post workout meal",
        "pre workout meal", "diet advice", "protein intake", "calorie goal",
        "meal plan", "healthy eating", "what to eat", "food after",
        "best food for", "nutrition tips",
    ),
    "hydration": (
        "water intake", "hydration", "log water", "drink water",
        "how much water", "daily water", "i drank", "water today",
    ),
    "fitness": (
        "fitness", "lose weight", "get fit", "muscle building", "fat loss", "weight loss",
        "build muscle", "stay active", "fitness coach", "fitness goal", "want to get fit",
    ),
    "exercise": ("squat", "push-up", "pushup", "plank", "lunge", "exercise", "pull-up", "pullup", "deadlift", "bench press"),
    "nutrition": ("food", "diet", "calorie", "protein", "nutrition", "meal"),
    "iot_hub": ("connect device", "smartwatch", "fitness band", "bp monitor", "glucometer", "oximeter", "smart scale"),
    "video_intelligence": ("educational video", "health video", "device setup video", "training video"),
    "core_agent": (
        "core agent", "agentic care", "agentic workflow", "run agent",
        "coordinate this workflow", "handle this workflow",
        "operations summary", "failed operations", "human attention", "platform activity",
    ),
    "mental_wellness": ("stress", "anxiety", "exam", "burnout", "lonely", "mental"),
    "sleep": ("sleep", "insomnia", "tired"),
    "health_monitoring": ("weight", "blood pressure", "glucose", "bp", "monitor"),
    "symptoms": ("fever", "cough", "pain", "headache", "rash", "nausea", "fatigue", "symptom", "sick"),
}

# Lower number wins when two intents have an equally specific match.
INTENT_PRIORITY = (
    "emergency",
    "orchestration_request",
    "report_intelligence",
    "report_history",
    "health_timeline",
    "health_analytics",
    "health_profile",
    "telehealth",
    "fitness_video_search",
    "workout_plan",
    "workout_session",
    "exercise_instruction",
    "family_care",
    "home_health",
    "ambulance",
    "appointment",
    "doctor",
    "hospital",
    "clinic",
    "pharmacy",
    "medicine",
    "medical_report",
    "health_records",
    "fitness_analytics",
    "nutrition_general",
    "hydration",
    "iot_hub",
    "video_intelligence",
    "mental_wellness",
    "sleep",
    "health_monitoring",
    "fitness",
    "exercise",
    "nutrition",
    "symptoms",
    "core_agent",
)
_PRIORITY = {intent: index for index, intent in enumerate(INTENT_PRIORITY)}


def _normalize(message: str) -> str:
    return re.sub(r"\s+", " ", str(message or "").strip().lower())


class IntentRouter:
    def detect(self, message):
        text = _normalize(message)
        # Explicit user invocation of the Agentic Care OS wins over ordinary
        # workflow keywords. The Core Agent still re-plans the underlying goal
        # through deterministic safety, permissions, tools, and approvals.
        if any(
            phrase in text
            for phrase in (
                "use agentic care",
                "agentic care to",
                "run agent",
                "agentic workflow",
                "coordinate this workflow",
                "handle this workflow",
            )
        ):
            return "core_agent"
        candidates = []
        for intent, keywords in INTENT_KEYWORDS.items():
            matched = [keyword for keyword in keywords if keyword in text]
            if not matched:
                continue
            longest_words = max(len(keyword.split()) for keyword in matched)
            longest_chars = max(len(keyword) for keyword in matched)
            # Specific phrases beat generic one-word matches. Multiple matches
            # add useful evidence without making the router probabilistic.
            score = (longest_words, longest_chars, len(matched))
            candidates.append((score, -_PRIORITY.get(intent, 10_000), intent))

        if not candidates:
            return "general_assistant"
        candidates.sort(reverse=True)
        return candidates[0][2]
