import json
from datetime import date

from .db import get_db, now_iso
from .health_access import authorize_patient


BLOOD_GROUPS = ("A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-")
SEX_OPTIONS = ("female", "male", "intersex", "other", "prefer_not_to_say")
LIST_FIELDS = (
    "allergies",
    "current_medications",
    "chronic_conditions",
    "previous_conditions",
    "surgeries",
    "vaccinations",
    "health_goals",
)


def _actor_value(actor, key):
    if hasattr(actor, "keys") and key in actor.keys():
        return actor[key]
    return actor.get(key) if isinstance(actor, dict) else None


def _clean_list(value):
    if isinstance(value, list):
        parts = value
    else:
        parts = str(value or "").replace("\r", "\n").replace(",", "\n").split("\n")
    return [str(item).strip()[:200] for item in parts if str(item).strip()][:100]


def _optional_number(value, label, minimum, maximum):
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be a number.") from error
    if not minimum <= number <= maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}.")
    return round(number, 2)


def _validate_date(value):
    if not value:
        return None
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError as error:
        raise ValueError("Date of birth must be a valid date.") from error
    if parsed > date.today():
        raise ValueError("Date of birth cannot be in the future.")
    return parsed.isoformat()


def empty_health_profile(patient_id):
    profile = {
        "patient_id": patient_id,
        "date_of_birth": None,
        "sex_at_birth": None,
        "blood_group": None,
        "height_cm": None,
        "baseline_weight_kg": None,
        "lifestyle_notes": None,
        "emergency_contact_name": None,
        "emergency_contact_phone": None,
        "emergency_contact_relationship": None,
        "created_at": None,
        "updated_at": None,
    }
    for field in LIST_FIELDS:
        profile[field] = []
    return profile


def serialize_health_profile(row, patient_id):
    if not row:
        return empty_health_profile(patient_id)
    item = dict(row)
    for field in LIST_FIELDS:
        try:
            item[field] = json.loads(item.get(field) or "[]")
        except (TypeError, json.JSONDecodeError):
            item[field] = []
    return item


def get_health_profile(actor, patient_id=None):
    target_id = authorize_patient(actor, patient_id, "profile")
    row = get_db().execute(
        "SELECT * FROM patient_health_profiles WHERE patient_id=?",
        (target_id,),
    ).fetchone()
    return serialize_health_profile(row, target_id)


def save_health_profile(actor, data, patient_id=None):
    target_id = authorize_patient(actor, patient_id, "profile")
    if _actor_value(actor, "role") != "admin" and int(_actor_value(actor, "id")) != target_id:
        raise PermissionError("Providers cannot modify a patient's personal health profile.")
    blood_group = str(data.get("blood_group") or "").strip().upper() or None
    if blood_group and blood_group not in BLOOD_GROUPS:
        raise ValueError("Select a valid blood group or leave it blank.")
    sex_at_birth = str(data.get("sex_at_birth") or "").strip().lower() or None
    if sex_at_birth and sex_at_birth not in SEX_OPTIONS:
        raise ValueError("Select a valid optional sex value.")
    values = {
        "date_of_birth": _validate_date(data.get("date_of_birth")),
        "sex_at_birth": sex_at_birth,
        "blood_group": blood_group,
        "height_cm": _optional_number(data.get("height_cm"), "Height", 20, 300),
        "baseline_weight_kg": _optional_number(data.get("baseline_weight_kg"), "Weight", 1, 500),
        "lifestyle_notes": str(data.get("lifestyle_notes") or "").strip()[:2000] or None,
        "emergency_contact_name": str(data.get("emergency_contact_name") or "").strip()[:120] or None,
        "emergency_contact_phone": str(data.get("emergency_contact_phone") or "").strip()[:40] or None,
        "emergency_contact_relationship": str(data.get("emergency_contact_relationship") or "").strip()[:80] or None,
    }
    for field in LIST_FIELDS:
        values[field] = json.dumps(_clean_list(data.get(field)))
    now = now_iso()
    db = get_db()
    existing = db.execute("SELECT patient_id FROM patient_health_profiles WHERE patient_id=?", (target_id,)).fetchone()
    columns = [
        "date_of_birth", "sex_at_birth", "blood_group", "height_cm", "baseline_weight_kg",
        *LIST_FIELDS, "lifestyle_notes", "emergency_contact_name", "emergency_contact_phone",
        "emergency_contact_relationship",
    ]
    if existing:
        assignments = ",".join(f"{column}=?" for column in columns)
        db.execute(
            f"UPDATE patient_health_profiles SET {assignments}, updated_at=? WHERE patient_id=?",
            tuple(values[column] for column in columns) + (now, target_id),
        )
    else:
        placeholders = ",".join("?" for _ in columns)
        db.execute(
            f"INSERT INTO patient_health_profiles (patient_id,{','.join(columns)},created_at,updated_at) VALUES (?,{placeholders},?,?)",
            (target_id,) + tuple(values[column] for column in columns) + (now, now),
        )
    return get_health_profile(actor, target_id)

