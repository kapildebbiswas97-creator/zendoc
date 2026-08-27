"""
Workout Engine — builds personalised workout plans deterministically.

No external API required.  Plans are generated from the exercise library
using the user's fitness profile as constraints.

Architecture is designed so Milestone 6 can add:
    workout_session.session_items  →  pose detection  →  auto rep counting
without rewriting this module.
"""

import json

from .db import get_db, now_iso
from .exercise_library import get_exercises_for_plan
from .fitness_profile import (
    EXPERIENCE_LEVELS,
    FITNESS_GOALS,
    get_fitness_profile,
)


# Sets/reps/rest templates by goal and experience
_PLAN_TEMPLATES = {
    # goal: {experience: {sets, reps_or_time, rest_seconds}}
    "general_fitness": {
        "beginner":     {"sets": 2, "reps": "10-12", "rest": 60},
        "intermediate": {"sets": 3, "reps": "12-15", "rest": 45},
        "advanced":     {"sets": 4, "reps": "15-20", "rest": 30},
    },
    "fat_loss": {
        "beginner":     {"sets": 2, "reps": "15", "rest": 45},
        "intermediate": {"sets": 3, "reps": "15-20", "rest": 30},
        "advanced":     {"sets": 4, "reps": "20", "rest": 20},
    },
    "strength": {
        "beginner":     {"sets": 3, "reps": "5-8", "rest": 120},
        "intermediate": {"sets": 4, "reps": "4-6", "rest": 150},
        "advanced":     {"sets": 5, "reps": "3-5", "rest": 180},
    },
    "muscle_building": {
        "beginner":     {"sets": 3, "reps": "8-10", "rest": 90},
        "intermediate": {"sets": 4, "reps": "8-12", "rest": 75},
        "advanced":     {"sets": 4, "reps": "10-15", "rest": 60},
    },
    "mobility": {
        "beginner":     {"sets": 1, "reps": "45s hold", "rest": 30},
        "intermediate": {"sets": 2, "reps": "60s hold", "rest": 30},
        "advanced":     {"sets": 2, "reps": "60-90s hold", "rest": 20},
    },
    "flexibility": {
        "beginner":     {"sets": 1, "reps": "30s hold", "rest": 20},
        "intermediate": {"sets": 2, "reps": "45s hold", "rest": 20},
        "advanced":     {"sets": 3, "reps": "60s hold", "rest": 15},
    },
    "cardio": {
        "beginner":     {"sets": 1, "reps": "30s on, 30s off", "rest": 60},
        "intermediate": {"sets": 3, "reps": "40s on, 20s off", "rest": 45},
        "advanced":     {"sets": 4, "reps": "45s on, 15s off", "rest": 30},
    },
    "home_workout": {
        "beginner":     {"sets": 2, "reps": "10-12", "rest": 60},
        "intermediate": {"sets": 3, "reps": "12-15", "rest": 45},
        "advanced":     {"sets": 3, "reps": "15-20", "rest": 30},
    },
    "gym_workout": {
        "beginner":     {"sets": 3, "reps": "8-10", "rest": 90},
        "intermediate": {"sets": 4, "reps": "8-12", "rest": 75},
        "advanced":     {"sets": 4, "reps": "10-12", "rest": 60},
    },
}


def _user_id(user):
    return int(user["id"] if hasattr(user, "__getitem__") else getattr(user, "id", 0))


def _template(goal, level):
    goal_tmpl = _PLAN_TEMPLATES.get(goal, _PLAN_TEMPLATES["general_fitness"])
    return goal_tmpl.get(level, goal_tmpl.get("beginner", {"sets": 3, "reps": "10", "rest": 60}))


def generate_plan_data(fitness_profile):
    """
    Build a plan structure from a fitness profile dict.
    Returns a dict with days list — does NOT write to DB.
    """
    goal = fitness_profile.get("fitness_goal") or "general_fitness"
    level = fitness_profile.get("experience_level") or "beginner"
    location = fitness_profile.get("workout_location") or "home"
    equipment = fitness_profile.get("equipment") or []
    available_minutes = int(fitness_profile.get("available_minutes") or 45)
    preferred_days = fitness_profile.get("preferred_days") or []

    # Validate goal/level against known values
    if goal not in FITNESS_GOALS:
        goal = "general_fitness"
    if level not in EXPERIENCE_LEVELS:
        level = "beginner"

    tmpl = _template(goal, level)
    exercises = get_exercises_for_plan(goal, location, equipment, level, available_minutes)

    # Determine number of workout days (3 default, respect preferred_days)
    n_days = min(len(preferred_days), 5) if preferred_days else 3
    n_days = max(n_days, 1)

    # Distribute exercises across days
    days = []
    for day_idx in range(n_days):
        day_label = preferred_days[day_idx] if day_idx < len(preferred_days) else f"Day {day_idx + 1}"
        # Stagger exercises across days: each day gets a slice
        chunk_size = max(3, len(exercises) // n_days)
        start = (day_idx * chunk_size) % max(len(exercises), 1)
        day_exercises = exercises[start: start + chunk_size] or exercises[:chunk_size]
        days.append({
            "day": day_idx + 1,
            "label": day_label.capitalize(),
            "exercises": [
                {
                    "exercise_id": ex["id"],
                    "name": ex["name"],
                    "category": ex["category"],
                    "muscle_group": ex["muscle_group"],
                    "difficulty": ex["difficulty"],
                    "sets": tmpl["sets"],
                    "reps": tmpl["reps"],
                    "rest_seconds": tmpl["rest"],
                    "instructions": ex["instructions"],
                    "order": idx + 1,
                }
                for idx, ex in enumerate(day_exercises)
            ],
        })

    estimated_minutes = len(days[0]["exercises"]) * 4 if days else 0

    return {
        "goal": goal,
        "experience_level": level,
        "workout_location": location,
        "estimated_minutes_per_session": estimated_minutes,
        "days": days,
        "disclaimer": (
            "This plan is for general wellness purposes only. "
            "Consult a qualified fitness professional or physician before starting if you have "
            "any medical conditions, injuries, or have been inactive for an extended period."
        ),
    }


def create_plan(user, label=None, fitness_profile=None):
    """Generate and persist a workout plan. Returns plan dict with DB id."""
    uid = _user_id(user)
    if fitness_profile is None:
        fitness_profile = get_fitness_profile(user)
    plan_data = generate_plan_data(fitness_profile)
    db = get_db()
    now = now_iso()
    name = label or f"{plan_data['goal'].replace('_', ' ').title()} Plan"
    cursor = db.execute(
        """INSERT INTO workout_plans
        (user_id, name, goal, experience_level, workout_location,
         estimated_minutes, plan_data, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            uid, name, plan_data["goal"], plan_data["experience_level"],
            plan_data["workout_location"], plan_data["estimated_minutes_per_session"],
            json.dumps(plan_data), now, now,
        ),
    )
    plan_id = cursor.lastrowid

    # Persist plan items for each day
    for day in plan_data["days"]:
        for item in day["exercises"]:
            db.execute(
                """INSERT INTO workout_plan_items
                (plan_id, exercise_id, day_number, order_in_day, sets, reps, rest_seconds, created_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (
                    plan_id, item["exercise_id"], day["day"], item["order"],
                    item["sets"], item["reps"], item["rest_seconds"], now,
                ),
            )
    db.commit()
    return get_plan(user, plan_id)


def get_plan(user, plan_id):
    """Return plan dict with full item list. Raises LookupError / PermissionError."""
    uid = _user_id(user)
    db = get_db()
    row = db.execute("SELECT * FROM workout_plans WHERE id=?", (plan_id,)).fetchone()
    if not row:
        raise LookupError("Workout plan not found.")
    if row["user_id"] != uid:
        raise PermissionError("You cannot access another user's workout plan.")
    plan = dict(row)
    try:
        plan["plan_data"] = json.loads(plan["plan_data"])
    except (TypeError, json.JSONDecodeError):
        plan["plan_data"] = {}
    items = db.execute(
        """SELECT wpi.*, e.name exercise_name, e.category, e.muscle_group,
                  e.difficulty, e.instructions, e.camera_ready
           FROM workout_plan_items wpi
           JOIN exercises e ON e.id=wpi.exercise_id
           WHERE wpi.plan_id=?
           ORDER BY wpi.day_number, wpi.order_in_day""",
        (plan_id,),
    ).fetchall()
    plan["items"] = [dict(i) for i in items]
    return plan


def list_plans(user, limit=10):
    """Return most recent plans for user."""
    uid = _user_id(user)
    rows = get_db().execute(
        "SELECT id, name, goal, experience_level, estimated_minutes, created_at FROM workout_plans WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
        (uid, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_latest_plan(user):
    """Return the most recent plan, or None."""
    uid = _user_id(user)
    row = get_db().execute(
        "SELECT id FROM workout_plans WHERE user_id=? ORDER BY created_at DESC LIMIT 1",
        (uid,),
    ).fetchone()
    if not row:
        return None
    return get_plan(user, row["id"])
