"""
Fitness Coach — AI orchestrator for all Milestone 5 fitness intents.

Called from intelligence.py when intent is in FITNESS_INTENTS.
Uses ONLY minimum-necessary context:
  - user's fitness profile
  - recent workout history
Never sends medical data to external services.
Emergency routing ALWAYS takes precedence (handled before this is called).
"""

from .ai_types import IntelligenceResult
from .exercise_library import get_exercise, list_exercises
from .fitness_analytics import get_fitness_progress
from .fitness_profile import get_fitness_profile
from .video_provider import search_fitness_video
from .workout_engine import get_latest_plan, list_plans
from .workout_tracking import list_sessions


_WORKOUT_DISCLAIMER = (
    "This is general wellness guidance only. Consult a qualified fitness professional "
    "or physician before starting any new exercise programme, especially if you have "
    "any medical conditions, injuries, or have been inactive for a prolonged period."
)

_NUTRITION_DISCLAIMER = (
    "This is general wellness information only. For clinical nutrition advice, "
    "consult a qualified dietitian or your healthcare provider."
)


def _fitness_profile_summary(fp):
    if not fp or not fp.get("fitness_goal"):
        return "No fitness profile set yet."
    goal = fp.get("fitness_goal", "").replace("_", " ")
    level = fp.get("experience_level", "unset")
    location = fp.get("workout_location", "unset")
    mins = fp.get("available_minutes", 45)
    return f"Goal: {goal} | Level: {level} | Location: {location} | {mins} min/session"


def _extract_exercise_name(message):
    """Simple heuristic: extract a likely exercise name from the message."""
    lower = message.lower()
    exercise_keywords = [
        "squat", "push-up", "pushup", "push up", "deadlift", "lunge", "plank",
        "crunch", "pull-up", "pullup", "pull up", "chin-up", "chinup",
        "bench press", "shoulder press", "lateral raise", "bicep curl",
        "tricep dip", "glute bridge", "mountain climber", "burpee",
        "downward dog", "warrior", "pigeon", "cat cow", "cat-cow",
        "russian twist", "leg raise", "hollow body", "superman",
        "high knees", "jumping jack", "jump rope",
        "hip flexor", "hamstring stretch", "world's greatest stretch",
        "goblet squat", "romanian deadlift", "dumbbell row",
    ]
    for kw in exercise_keywords:
        if kw in lower:
            return kw
    # Fall back: look for quoted word or last noun-ish word
    return None


def _find_exercise_by_name(query):
    """Search exercise library for a matching exercise."""
    if not query:
        return None
    result = list_exercises(q=query, limit=1)
    exercises = result.get("exercises", [])
    return exercises[0] if exercises else None


class FitnessCoach:

    def handle(self, intent, message, user):
        """
        Route fitness intent to the appropriate handler.
        Returns IntelligenceResult.
        Safety check is done BEFORE this is called (in intelligence.py).
        """
        try:
            if intent == "fitness_coach":
                return self._handle_general(message, user)
            if intent == "workout_plan":
                return self._handle_workout_plan(message, user)
            if intent == "workout_session":
                return self._handle_workout_session(message, user)
            if intent == "exercise_instruction":
                return self._handle_exercise_instruction(message, user)
            if intent == "fitness_video_search":
                return self._handle_video_search(message, user)
            if intent == "fitness_analytics":
                return self._handle_analytics(message, user)
            if intent == "nutrition_general":
                return self._handle_nutrition(message, user)
            if intent == "hydration":
                return self._handle_hydration(message, user)
        except (PermissionError, LookupError, ValueError) as exc:
            return IntelligenceResult(
                intent=intent,
                urgency="routine",
                message=f"I could not complete that fitness request: {exc}",
                follow_up_questions=["Would you like to set up your fitness profile first?"],
                possible_actions=[{"type": "fitness_profile", "label": "Set up fitness profile"}],
                provider="fitness_coach",
                success=False,
            )
        return self._handle_general(message, user)

    # ── General fitness coaching ──────────────────────────────────────────

    def _handle_general(self, message, user):
        if not user:
            return self._require_login("fitness_coach")
        fp = get_fitness_profile(user)
        summary = _fitness_profile_summary(fp)
        has_profile = bool(fp.get("fitness_goal"))
        if has_profile:
            msg = (
                f"Your current fitness setup: {summary}. "
                "I can create a personalised workout plan, show exercises, "
                "find tutorial videos, track your sessions, or give nutrition guidance. "
                "What would you like to do?"
            )
            actions = [
                {"type": "workout_plan", "label": "View / Generate My Plan"},
                {"type": "fitness_exercises", "label": "Browse Exercise Library"},
                {"type": "fitness_progress", "label": "View My Progress"},
            ]
        else:
            msg = (
                "Welcome to ZENDOC Fitness! To get started, set up your fitness profile "
                "so I can personalise your plan. Tell me your goal "
                "(e.g. lose weight, build muscle, get fit at home) and I'll take it from there."
            )
            actions = [{"type": "fitness_profile", "label": "Set Up Fitness Profile"}]
        return IntelligenceResult(
            intent="fitness_coach",
            urgency="routine",
            message=f"{msg}\n\n{_WORKOUT_DISCLAIMER}",
            follow_up_questions=[
                "What is your main fitness goal right now?",
                "Do you prefer home or gym workouts?",
            ],
            possible_actions=actions,
            provider="fitness_coach",
        )

    # ── Workout plan ──────────────────────────────────────────────────────

    def _handle_workout_plan(self, message, user):
        if not user:
            return self._require_login("workout_plan")
        fp = get_fitness_profile(user)
        plan = get_latest_plan(user)
        if plan:
            days = plan.get("plan_data", {}).get("days", [])
            n_days = len(days)
            goal = plan.get("goal", "general fitness").replace("_", " ")
            msg = (
                f"Your current plan is a {goal} programme with {n_days} day{'s' if n_days != 1 else ''} per week. "
                f"Open My Plan to see the exercises, sets, and reps for each session."
            )
            actions = [
                {"type": "fitness_plan", "label": "Open My Workout Plan"},
                {"type": "workout_session", "label": "Start Today's Workout"},
            ]
        else:
            if fp.get("fitness_goal"):
                msg = (
                    "You do not have a plan yet. I'll generate one based on your fitness profile. "
                    f"Your goal is {fp['fitness_goal'].replace('_', ' ')} at {fp.get('experience_level','beginner')} level. "
                    "Open Fitness > My Plan to generate it now."
                )
            else:
                msg = (
                    "To generate a personalised workout plan I need your fitness profile. "
                    "Set your goal, experience level, and available time first."
                )
            actions = [
                {"type": "fitness_profile", "label": "Set Up Fitness Profile"},
                {"type": "fitness_plan", "label": "Generate Plan"},
            ]
        return IntelligenceResult(
            intent="workout_plan",
            urgency="routine",
            message=f"{msg}\n\n{_WORKOUT_DISCLAIMER}",
            follow_up_questions=[],
            possible_actions=actions,
            provider="fitness_coach",
        )

    # ── Workout session ───────────────────────────────────────────────────

    def _handle_workout_session(self, message, user):
        if not user:
            return self._require_login("workout_session")
        recent = list_sessions(user, page=1, per_page=1)
        total = recent.get("total", 0)
        if total:
            last = recent["sessions"][0]
            last_date = str(last.get("started_at", ""))[:10]
            msg = (
                f"You have completed {total} workout session{'s' if total != 1 else ''}. "
                f"Your most recent was on {last_date}. "
                "Open Start Workout to begin a new session from your plan or an ad-hoc workout."
            )
        else:
            msg = (
                "You have not recorded a workout session yet. "
                "Open Start Workout to begin your first session!"
            )
        return IntelligenceResult(
            intent="workout_session",
            urgency="routine",
            message=msg,
            follow_up_questions=[],
            possible_actions=[
                {"type": "workout_session", "label": "Start Workout"},
                {"type": "fitness_progress", "label": "View Progress"},
            ],
            provider="fitness_coach",
        )

    # ── Exercise instruction ───────────────────────────────────────────────

    def _handle_exercise_instruction(self, message, user):
        query = _extract_exercise_name(message)
        ex = _find_exercise_by_name(query) if query else None
        if ex:
            msg = (
                f"**{ex['name']}** ({ex['category'].title()} — {ex['difficulty']})\n"
                f"Muscles: {ex['muscle_group']}\n\n"
                f"**How to do it:** {ex['instructions']}\n\n"
                f"**Common mistakes:** {ex.get('common_mistakes', 'N/A')}\n"
                f"**Easier:** {ex.get('easier_variation', 'N/A')}\n"
                f"**Harder:** {ex.get('harder_variation', 'N/A')}"
            )
            actions = [
                {"type": "exercise_detail", "label": f"See full detail", "exercise_id": ex["id"]},
                {"type": "fitness_video_search", "label": f"Find {ex['name']} tutorial video", "query": ex["name"]},
            ]
        elif query:
            msg = (
                f"I could not find a specific exercise called '{query}' in the library. "
                "Browse the full Exercise Library to find what you need."
            )
            actions = [{"type": "fitness_exercises", "label": "Browse Exercise Library"}]
        else:
            msg = "Which exercise would you like instructions for? For example: squat, push-up, plank, deadlift."
            actions = [{"type": "fitness_exercises", "label": "Browse Exercise Library"}]
        return IntelligenceResult(
            intent="exercise_instruction",
            urgency="routine",
            message=msg,
            follow_up_questions=[],
            possible_actions=actions,
            provider="fitness_coach",
        )

    # ── Video search ──────────────────────────────────────────────────────

    def _handle_video_search(self, message, user):
        # Extract a search query from the message
        query = _extract_exercise_name(message) or message.strip()[:100]
        video_result = search_fitness_video(query)
        if video_result.get("available") and video_result.get("results"):
            count = len(video_result["results"])
            titles = ", ".join(r["title"][:40] for r in video_result["results"][:2])
            msg = f"Found {count} video{'s' if count != 1 else ''} for '{query}'. Top results include: {titles}. Open Videos to view and play them."
        elif video_result.get("available") is False:
            msg = (
                f"Video discovery is not currently configured. "
                f"{video_result.get('reason', '')} "
                "You can still access written exercise instructions in the Exercise Library."
            )
        else:
            msg = f"No videos found for '{query}'. Try a different search term or browse the Exercise Library for written instructions."
        return IntelligenceResult(
            intent="fitness_video_search",
            urgency="routine",
            message=msg,
            follow_up_questions=[],
            possible_actions=[
                {"type": "fitness_videos", "label": "Open Video Search", "query": query},
                {"type": "fitness_exercises", "label": "Browse Exercise Library"},
            ],
            provider="fitness_coach",
        )

    # ── Fitness analytics ─────────────────────────────────────────────────

    def _handle_analytics(self, message, user):
        if not user:
            return self._require_login("fitness_analytics")
        progress = get_fitness_progress(user, period="30d")
        count = progress["workouts_completed"]
        if count:
            msg = (
                f"In the last 30 days you completed {count} workout{'s' if count != 1 else ''}, "
                f"totalling {progress['total_duration_minutes']} minutes. "
                f"Current streak: {progress['current_streak_days']} day{'s' if progress['current_streak_days'] != 1 else ''}. "
                "Open Progress to see your full activity history."
            )
        else:
            msg = (
                "No workout sessions recorded in the last 30 days. "
                "Complete your first session and it will appear here and on your Health Timeline."
            )
        return IntelligenceResult(
            intent="fitness_analytics",
            urgency="routine",
            message=msg,
            follow_up_questions=[],
            possible_actions=[{"type": "fitness_progress", "label": "View Fitness Progress"}],
            provider="fitness_coach",
        )

    # ── Nutrition ─────────────────────────────────────────────────────────

    def _handle_nutrition(self, message, user):
        lower = message.lower()
        if "after" in lower and ("workout" in lower or "train" in lower):
            msg = (
                "After exercise, a meal or snack containing protein and carbohydrates can support "
                "muscle recovery and replenish glycogen. Common choices include: a protein shake with fruit, "
                "chicken with rice, eggs with toast, or Greek yogurt with banana. "
                "The optimal timing and quantities depend on your goal, body weight, and training intensity. "
                "Log your meal in ZENDOC Nutrition to track what works for you."
            )
        elif "protein" in lower:
            msg = (
                "Protein supports muscle repair and satiety. Common general wellness guidance suggests "
                "0.8–1.6 g per kg of body weight per day for active individuals, though needs vary. "
                "High-protein foods include eggs, chicken, fish, lentils, tofu, Greek yogurt, and cottage cheese. "
                "Track your intake using the Nutrition Log."
            )
        else:
            msg = (
                "ZENDOC Nutrition helps you log meals, track protein and calories, and get general "
                "wellness guidance around food. Open Nutrition to log a meal or view your daily summary."
            )
        return IntelligenceResult(
            intent="nutrition_general",
            urgency="routine",
            message=f"{msg}\n\n{_NUTRITION_DISCLAIMER}",
            follow_up_questions=["Would you like to log a meal or view today's nutrition summary?"],
            possible_actions=[{"type": "fitness_nutrition", "label": "Open Nutrition Tracker"}],
            provider="fitness_coach",
        )

    # ── Hydration ─────────────────────────────────────────────────────────

    def _handle_hydration(self, message, user):
        msg = (
            "Staying hydrated supports energy levels, focus, and physical performance. "
            "ZENDOC tracks your daily water intake. Log water from the Hydration page "
            "to see your daily total and progress toward the general wellness guideline. "
            "Your actual needs depend on body size, climate, and activity level."
        )
        return IntelligenceResult(
            intent="hydration",
            urgency="routine",
            message=msg,
            follow_up_questions=[],
            possible_actions=[{"type": "fitness_hydration", "label": "Open Hydration Tracker"}],
            provider="fitness_coach",
        )

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _require_login(intent):
        return IntelligenceResult(
            intent=intent,
            urgency="routine",
            message="Log in to access ZENDOC Fitness.",
            follow_up_questions=[],
            possible_actions=[{"type": "login", "label": "Log in"}],
            provider="fitness_coach",
        )
