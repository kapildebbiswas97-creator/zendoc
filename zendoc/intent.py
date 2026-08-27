INTENT_KEYWORDS = {
    "emergency": ("emergency", "urgent", "ambulance", "chest pain", "shortness of breath", "stroke"),
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
    "mental_wellness": ("stress", "anxiety", "exam", "burnout", "lonely", "mental"),
    "sleep": ("sleep", "insomnia", "tired"),
    "health_monitoring": ("weight", "blood pressure", "glucose", "bp", "monitor"),
}


class IntentRouter:
    def detect(self, message):
        text = (message or "").lower()
        for intent, keywords in INTENT_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                return intent
        return "general_assistant"
