"""
Fitness Profile — private per-user fitness setup.
Patients only.  No provider cross-access (fitness data is lifestyle data,
not clinical data, so the M4 health-access grant system is not used here).

Fields:
    fitness_goal        — general_fitness | fat_loss | strength | muscle_building |
                          mobility | flexibility | cardio
    experience_level    — beginner | intermediate | advanced
    preferred_workout_type — strength | cardio | yoga | mixed
    workout_location    — home | gym | both
    equipment           — JSON list of available equipment tags
    available_minutes   — typical workout length in minutes
    preferred_days      — JSON list of weekday names
    height_cm           — self-reported (not pulled automatically from health profile)
    weight_kg           — self-reported
    limitations         — free text (injuries, conditions, notes)
    target_weight_kg    — optional goal weight
"""

import json

from .db import get_db, now_iso


FITNESS_GOALS = (
    "general_fitness",
    "fat_loss",
    "strength",
    "muscle_building",
    "mobility",
    "flexibility",
    "cardio",
)

EXPERIENCE_LEVELS = ("beginner", "intermediate", "advanced")

WORKOUT_TYPES = ("strength", "cardio", "yoga", "mixed")

WORKOUT_LOCATIONS = ("home", "gym", "both")

EQUIPMENT_OPTIONS = (
    "none",
    "bodyweight",
    "dumbbell",
    "resistance_band",
    "barbell",
    "cable",
    "machine",
    "pull_up_bar",
    "kettlebell",
    "bench",
)

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _user_id(user):
    uid = user["id"] if hasattr(user, "__getitem__") else getattr(user, "id", None)
    return int(uid or 0)


def _require_patient(user):
    role = user["role"] if hasattr(user, "__getitem__") else getattr(user, "role", None)
    if role != "patient":
        raise PermissionError("Fitness profiles are only available to patients.")
    uid = _user_id(user)
    if not uid:
        raise PermissionError("Authentication is required.")
    return uid


def _validate_profile(data):
    errors = []
    goal = data.get("fitness_goal")
    if goal and goal not in FITNESS_GOALS:
        errors.append(f"fitness_goal must be one of: {', '.join(FITNESS_GOALS)}")
    level = data.get("experience_level")
    if level and level not in EXPERIENCE_LEVELS:
        errors.append(f"experience_level must be one of: {', '.join(EXPERIENCE_LEVELS)}")
    wtype = data.get("preferred_workout_type")
    if wtype and wtype not in WORKOUT_TYPES:
        errors.append(f"preferred_workout_type must be one of: {', '.join(WORKOUT_TYPES)}")
    location = data.get("workout_location")
    if location and location not in WORKOUT_LOCATIONS:
        errors.append(f"workout_location must be one of: {', '.join(WORKOUT_LOCATIONS)}")
    mins = data.get("available_minutes")
    if mins is not None:
        try:
            mins = int(mins)
            if mins < 5 or mins > 300:
                errors.append("available_minutes must be between 5 and 300.")
        except (TypeError, ValueError):
            errors.append("available_minutes must be a number.")
    height = data.get("height_cm")
    if height is not None:
        try:
            h = float(height)
            if h < 50 or h > 300:
                errors.append("height_cm must be between 50 and 300.")
        except (TypeError, ValueError):
            errors.append("height_cm must be a number.")
    weight = data.get("weight_kg")
    if weight is not None:
        try:
            w = float(weight)
            if w < 20 or w > 500:
                errors.append("weight_kg must be between 20 and 500.")
        except (TypeError, ValueError):
            errors.append("weight_kg must be a number.")
    target = data.get("target_weight_kg")
    if target is not None:
        try:
            t = float(target)
            if t < 20 or t > 500:
                errors.append("target_weight_kg must be between 20 and 500.")
        except (TypeError, ValueError):
            errors.append("target_weight_kg must be a number.")
    equip = data.get("equipment")
    if equip is not None:
        if not isinstance(equip, list):
            errors.append("equipment must be a list.")
        else:
            invalid = [e for e in equip if e not in EQUIPMENT_OPTIONS]
            if invalid:
                errors.append(f"Unknown equipment: {', '.join(invalid)}. Options: {', '.join(EQUIPMENT_OPTIONS)}")
    days = data.get("preferred_days")
    if days is not None:
        if not isinstance(days, list):
            errors.append("preferred_days must be a list.")
        else:
            invalid = [d for d in days if d.lower() not in WEEKDAYS]
            if invalid:
                errors.append(f"Unknown days: {', '.join(invalid)}")
    if errors:
        raise ValueError("; ".join(errors))


def get_fitness_profile(user):
    """Return the user's fitness profile dict, or a blank default if not set."""
    uid = _require_patient(user)
    row = get_db().execute(
        "SELECT * FROM fitness_profiles WHERE user_id=?", (uid,)
    ).fetchone()
    if not row:
        return {
            "user_id": uid,
            "fitness_goal": None,
            "experience_level": None,
            "preferred_workout_type": None,
            "workout_location": None,
            "equipment": [],
            "available_minutes": 45,
            "preferred_days": [],
            "height_cm": None,
            "weight_kg": None,
            "limitations": None,
            "target_weight_kg": None,
            "created_at": None,
            "updated_at": None,
        }
    d = dict(row)
    for key in ("equipment", "preferred_days"):
        try:
            d[key] = json.loads(d[key]) if d[key] else []
        except (TypeError, json.JSONDecodeError):
            d[key] = []
    return d


def save_fitness_profile(user, data):
    """Upsert fitness profile.  Returns the saved profile dict."""
    uid = _require_patient(user)
    _validate_profile(data)
    db = get_db()
    now = now_iso()
    existing = db.execute("SELECT user_id FROM fitness_profiles WHERE user_id=?", (uid,)).fetchone()

    def _json(val, default="[]"):
        if val is None:
            return None
        if isinstance(val, list):
            return json.dumps(val)
        return json.dumps(json.loads(val)) if isinstance(val, str) else default

    def _float(val):
        return float(val) if val is not None else None

    def _int(val):
        return int(val) if val is not None else None

    if existing:
        current = dict(db.execute("SELECT * FROM fitness_profiles WHERE user_id=?", (uid,)).fetchone())
        updates = {
            "fitness_goal": data.get("fitness_goal", current.get("fitness_goal")),
            "experience_level": data.get("experience_level", current.get("experience_level")),
            "preferred_workout_type": data.get("preferred_workout_type", current.get("preferred_workout_type")),
            "workout_location": data.get("workout_location", current.get("workout_location")),
            "equipment": _json(data["equipment"]) if "equipment" in data else current.get("equipment"),
            "available_minutes": _int(data["available_minutes"]) if "available_minutes" in data else current.get("available_minutes"),
            "preferred_days": _json(data["preferred_days"]) if "preferred_days" in data else current.get("preferred_days"),
            "height_cm": _float(data["height_cm"]) if "height_cm" in data else current.get("height_cm"),
            "weight_kg": _float(data["weight_kg"]) if "weight_kg" in data else current.get("weight_kg"),
            "limitations": data.get("limitations", current.get("limitations")),
            "target_weight_kg": _float(data["target_weight_kg"]) if "target_weight_kg" in data else current.get("target_weight_kg"),
        }
        db.execute(
            """UPDATE fitness_profiles SET
            fitness_goal=?, experience_level=?, preferred_workout_type=?,
            workout_location=?, equipment=?, available_minutes=?,
            preferred_days=?, height_cm=?, weight_kg=?, limitations=?,
            target_weight_kg=?, updated_at=?
            WHERE user_id=?""",
            (
                updates["fitness_goal"], updates["experience_level"],
                updates["preferred_workout_type"], updates["workout_location"],
                updates["equipment"], updates["available_minutes"],
                updates["preferred_days"], updates["height_cm"],
                updates["weight_kg"], updates["limitations"],
                updates["target_weight_kg"], now, uid,
            ),
        )
    else:
        db.execute(
            """INSERT INTO fitness_profiles
            (user_id, fitness_goal, experience_level, preferred_workout_type,
             workout_location, equipment, available_minutes, preferred_days,
             height_cm, weight_kg, limitations, target_weight_kg, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                uid,
                data.get("fitness_goal"),
                data.get("experience_level"),
                data.get("preferred_workout_type"),
                data.get("workout_location"),
                _json(data.get("equipment", [])),
                _int(data.get("available_minutes", 45)),
                _json(data.get("preferred_days", [])),
                _float(data.get("height_cm")),
                _float(data.get("weight_kg")),
                data.get("limitations"),
                _float(data.get("target_weight_kg")),
                now, now,
            ),
        )
    db.commit()
    return get_fitness_profile(user)
