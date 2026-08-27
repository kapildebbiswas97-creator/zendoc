"""
Nutrition Coach — general wellness food, meal and hydration tracking.

IMPORTANT DISTINCTIONS:
- This module provides GENERAL WELLNESS guidance only.
- It does NOT provide clinical nutrition advice.
- It does NOT prescribe diets for medical conditions.
- Calorie / protein values are only stored when provided by the user.
  They are NEVER fabricated.
- Hydration suggestions are general wellness guidance, NOT medical
  prescriptions. Individual needs vary.
"""

from datetime import datetime, timezone

from .db import get_db, now_iso


MEAL_TYPES = ("breakfast", "morning_snack", "lunch", "afternoon_snack", "dinner", "post_workout", "other")


def _user_id(user):
    return int(user["id"] if hasattr(user, "__getitem__") else getattr(user, "id", 0))


def _today_iso():
    return datetime.now(timezone.utc).date().isoformat()


# ---------------------------------------------------------------------------
# Food / Nutrition Logging
# ---------------------------------------------------------------------------

def log_food(user, data):
    """
    Log a food / meal entry.

    calories_kcal and protein_g are nullable — never invent values.
    If the user doesn't know them, they stay NULL.
    """
    uid = _user_id(user)
    food_name = str(data.get("food_name") or "").strip()
    if not food_name:
        raise ValueError("food_name is required.")
    if len(food_name) > 200:
        raise ValueError("food_name must be 200 characters or fewer.")

    meal_type = str(data.get("meal_type") or "other").lower()
    if meal_type not in MEAL_TYPES:
        raise ValueError(f"meal_type must be one of: {', '.join(MEAL_TYPES)}")

    def _nullable_float(val, label, lo=0, hi=9999):
        if val is None or str(val).strip() == "":
            return None
        try:
            v = float(val)
        except (TypeError, ValueError) as e:
            raise ValueError(f"{label} must be a number.") from e
        if v < lo or v > hi:
            raise ValueError(f"{label} must be between {lo} and {hi}.")
        return v

    calories = _nullable_float(data.get("calories_kcal"), "calories_kcal", 0, 9999)
    protein = _nullable_float(data.get("protein_g"), "protein_g", 0, 999)
    carbs = _nullable_float(data.get("carbs_g"), "carbs_g", 0, 999)
    fat = _nullable_float(data.get("fat_g"), "fat_g", 0, 999)
    quantity = _nullable_float(data.get("quantity_g"), "quantity_g", 0, 9999)

    logged_at = data.get("logged_at") or now_iso()
    notes = str(data.get("notes") or "")[:400] or None

    db = get_db()
    now = now_iso()
    cursor = db.execute(
        """INSERT INTO nutrition_logs
        (user_id, food_name, meal_type, quantity_g, calories_kcal,
         protein_g, carbs_g, fat_g, notes, logged_at, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (uid, food_name, meal_type, quantity, calories, protein,
         carbs, fat, notes, logged_at, now),
    )
    db.commit()
    return {"id": cursor.lastrowid, "food_name": food_name, "meal_type": meal_type, "logged_at": logged_at}


def list_nutrition_logs(user, date=None, page=1, per_page=50):
    """Return paginated food logs for a given date (today if omitted)."""
    uid = _user_id(user)
    target_date = str(date or _today_iso())
    db = get_db()
    page = max(1, int(page))
    per_page = max(1, min(int(per_page), 100))
    conditions = ["user_id=?", "DATE(logged_at)=?"]
    params = [uid, target_date]
    where = " WHERE " + " AND ".join(conditions)
    total = db.execute(f"SELECT COUNT(*) n FROM nutrition_logs{where}", params).fetchone()["n"]
    rows = db.execute(
        f"SELECT * FROM nutrition_logs{where} ORDER BY logged_at ASC LIMIT ? OFFSET ?",
        params + [per_page, (page - 1) * per_page],
    ).fetchall()
    return {
        "date": target_date,
        "logs": [dict(r) for r in rows],
        "page": page, "per_page": per_page, "total": total,
    }


def get_nutrition_summary(user, date=None):
    """
    Compute daily nutrition totals.
    Only sums values that are NOT NULL — never invents missing data.
    """
    uid = _user_id(user)
    target_date = str(date or _today_iso())
    db = get_db()
    row = db.execute(
        """SELECT
            COUNT(*) entries,
            SUM(calories_kcal) total_calories,
            SUM(protein_g) total_protein_g,
            SUM(carbs_g) total_carbs_g,
            SUM(fat_g) total_fat_g
        FROM nutrition_logs WHERE user_id=? AND DATE(logged_at)=?""",
        (uid, target_date),
    ).fetchone()
    return {
        "date": target_date,
        "entries": row["entries"] or 0,
        "total_calories_kcal": round(row["total_calories"], 1) if row["total_calories"] else None,
        "total_protein_g": round(row["total_protein_g"], 1) if row["total_protein_g"] else None,
        "total_carbs_g": round(row["total_carbs_g"], 1) if row["total_carbs_g"] else None,
        "total_fat_g": round(row["total_fat_g"], 1) if row["total_fat_g"] else None,
        "note": (
            "Totals only include entries where values were provided. "
            "For accurate tracking, enter calorie and macro values when logging food."
        ),
        "wellness_disclaimer": (
            "Nutritional guidance is for general wellness only. "
            "For clinical nutrition advice, consult a qualified dietitian."
        ),
    }


# ---------------------------------------------------------------------------
# Hydration Logging
# ---------------------------------------------------------------------------

def log_water(user, ml):
    """Log a water intake entry. ml must be positive."""
    uid = _user_id(user)
    try:
        ml_val = float(ml)
    except (TypeError, ValueError) as e:
        raise ValueError("ml must be a number.") from e
    if ml_val <= 0 or ml_val > 5000:
        raise ValueError("ml must be between 1 and 5000.")
    now = now_iso()
    cursor = get_db().execute(
        "INSERT INTO hydration_logs (user_id, ml, logged_at, created_at) VALUES (?,?,?,?)",
        (uid, ml_val, now, now),
    )
    get_db().commit()
    return {"id": cursor.lastrowid, "ml": ml_val, "logged_at": now}


def list_hydration_logs(user, date=None):
    """Return all hydration logs for a date (today if omitted)."""
    uid = _user_id(user)
    target_date = str(date or _today_iso())
    rows = get_db().execute(
        "SELECT * FROM hydration_logs WHERE user_id=? AND DATE(logged_at)=? ORDER BY logged_at ASC",
        (uid, target_date),
    ).fetchall()
    return {"date": target_date, "logs": [dict(r) for r in rows]}


def get_hydration_summary(user, date=None):
    """
    Return total water consumed for a date and a general wellness suggestion.
    The suggestion is a GENERAL WELLNESS guideline, NOT a medical prescription.
    Individual requirements differ based on body size, climate, activity, and health.
    """
    uid = _user_id(user)
    target_date = str(date or _today_iso())
    row = get_db().execute(
        "SELECT COUNT(*) entries, SUM(ml) total_ml FROM hydration_logs WHERE user_id=? AND DATE(logged_at)=?",
        (uid, target_date),
    ).fetchone()
    total_ml = round(row["total_ml"] or 0, 0)
    # General wellness suggestion: 2000 ml/day is a commonly referenced guideline
    # We explicitly do NOT claim this is medically correct for the individual
    suggestion_ml = 2000
    return {
        "date": target_date,
        "entries": row["entries"] or 0,
        "total_ml": int(total_ml),
        "total_litres": round(total_ml / 1000, 2),
        "general_suggestion_ml": suggestion_ml,
        "percentage_of_suggestion": round((total_ml / suggestion_ml) * 100) if total_ml else 0,
        "wellness_note": (
            "A common general wellness guideline is approximately 2 litres of water per day for adults. "
            "Your actual needs vary based on body weight, activity level, climate, and health conditions. "
            "This is not a medical prescription."
        ),
    }
