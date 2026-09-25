INTENT_KEYWORDS = {
    "emergency": ("emergency", "ambulance", "chest pain", "shortness of breath", "stroke"),
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
        "fulfil prescription",
        "order prescribed medicines",
        "find prescribed",
    ),
    "symptoms": ("fever", "cough", "pain", "headache", "rash", "nausea", "fatigue", "symptom", "sick"),
    "report_intelligence": ("explain my blood", "explain my report", "explain my latest report", "explain my lab", "interpret my report"),
    "report_history": ("show my latest report", "show my report", "report history"),
    "health_timeline": ("show my health history", "my health history", "health timeline", "show my timeline"),
    "health_analytics": ("weight trend", "bmi trend", "glucose trend", "blood pressure history", "measurement trend"),
    "health_profile": ("what medicines am i taking", "my medications", "current medications", "my allergies"),
    "doctor": ("doctor", "specialist", "cardiologist", "dermatologist", "physician"),
    "hospital": ("hospital", "emergency room", "nearest hospital"),
    "clinic": ("clinic",),
    "pharmacy": ("pharmacy", "chemist"),
    "medicine": ("medicine", "medication", "tablet", "drug", "prescription"),
    "appointment": ("appointment", "book", "schedule", "visit"),
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
    "exercise": (
        "squat", "push-up", "pushup", "plank", "lunge", "exercise",
        "pull-up", "pullup", "deadlift", "bench press",
    ),
    "nutrition": ("food", "diet", "calorie", "protein", "nutrition", "meal"),
    "family_care": ("family", "my father", "my mother", "my parent", "my parents", "remote parent", "parent care", "dependent"),
    "home_health": ("nurse", "physiotherapy", "elder care", "home visit", "home health", "nurse for my", "doctor home visit"),
    "ambulance": ("ambulance", "transport", "icu van", "wheelchair van", "hospital transfer"),
    "pharmacy": ("pharmacy", "medicine delivery", "refill", "chemist", "prescribe", "pill"),
    "iot_hub": ("connect device", "smartwatch", "fitness band", "bp monitor", "glucometer", "oximeter", "smart scale"),
    "telehealth": ("video consultation", "voice call", "doctor chat", "request doctor chat", "telehealth", "consultation request"),
    "video_intelligence": ("educational video", "exercise video", "health video", "device setup video", "training video", "find a video"),
    "core_agent": ("core agent", "operations summary", "failed operations", "human attention", "platform activity"),
    "mental_wellness": ("stress", "anxiety", "exam", "burnout", "lonely", "mental"),
    "sleep": ("sleep", "insomnia", "tired"),
    "health_monitoring": ("weight", "blood pressure", "glucose", "bp", "monitor"),
}


def is_multi_step_care_goal(message):
    """Detect clearly multi-step care coordination without routing ordinary questions."""
    text = " ".join(str(message or "").lower().split())
    if not text:
        return False

    action_families = (
        ("find ", "search ", "locate "),
        ("request ", "book ", "schedule ", "arrange "),
        ("check ", "review ", "show ", "look at "),
        ("organize ", "coordinate ", "plan ", "follow up", "follow-up", "next safe action", "next step"),
    )
    domain_families = (
        ("doctor", "specialist", "provider", "hospital", "clinic"),
        ("appointment", "consultation", "telehealth"),
        ("record", "report", "health memory", "timeline"),
        ("prescription", "medicine", "medication", "pharmacy"),
        ("diagnostic", "lab", "test"),
        ("mother", "father", "parent", "family", "dependent"),
        ("home health", "home care", "transport", "ambulance"),
    )

    action_count = sum(1 for family in action_families if any(term in text for term in family))
    domain_count = sum(1 for family in domain_families if any(term in text for term in family))
    explicit_coordination = any(
        marker in text
        for marker in (
            "organize the",
            "organise the",
            "coordinate",
            "next safe action",
            "next safe step",
            "help me organize",
            "help me organise",
        )
    )
    sequential = any(marker in text for marker in (" and ", " then ", ";", " after that ", " also "))

    return (
        domain_count >= 2
        and (
            action_count >= 2
            or (explicit_coordination and action_count >= 1)
            or (sequential and action_count >= 2)
        )
    )


class IntentRouter:
    def detect(self, message):
        text = (message or "").lower()

        # Fulfilment/service intents must win over incidental destination words.
        # Example: "patient transport for a routine clinic visit" is a transport
        # request, not merely a clinic-search query. Emergency safety assessment
        # still runs separately and can override this routing decision.
        priority_intents = ("ambulance", "home_health", "telehealth", "iot_hub")
        for intent in priority_intents:
            if any(keyword in text for keyword in INTENT_KEYWORDS.get(intent, ())):
                return intent

        # Preserve the established prescription/fulfilment orchestrator phrases.
        if any(keyword in text for keyword in INTENT_KEYWORDS.get("orchestration_request", ())):
            return "orchestration_request"

        # Broader multi-step care goals enter the bounded specialist Agent OS.
        # Ordinary one-step health questions stay on their normal intent path.
        if is_multi_step_care_goal(text):
            return "agent_os_request"

        for intent, keywords in INTENT_KEYWORDS.items():
            if intent in priority_intents or intent == "orchestration_request":
                continue
            if any(keyword in text for keyword in keywords):
                return intent
        return "general_assistant"
