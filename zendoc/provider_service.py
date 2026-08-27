from datetime import datetime, timedelta, timezone

from .db import get_db, now_iso


PROVIDER_ROLES = {"doctor", "hospital", "pharmacy"}
VERIFICATION_STATES = {"pending", "verified", "rejected", "suspended"}
SPECIALTIES = [
    "General Medicine",
    "Cardiology",
    "Dermatology",
    "Neurology",
    "Orthopedics",
    "Pediatrics",
    "Gynecology",
    "Psychiatry",
    "ENT",
    "Ophthalmology",
]


def normalize_specialty(value):
    value = (value or "").strip()
    if not value:
        return ""
    known = {item.lower(): item for item in SPECIALTIES}
    return known.get(value.lower(), value.title())


def provider_type_for_role(role):
    if role == "doctor":
        return "doctor"
    if role == "hospital":
        return "hospital"
    if role == "pharmacy":
        return "pharmacy"
    return "provider"


def get_provider_profile_for_user(user_id):
    return get_db().execute("SELECT * FROM provider_profiles WHERE user_id=?", (user_id,)).fetchone()


def upsert_provider_profile(user, data):
    if user["role"] not in PROVIDER_ROLES:
        raise PermissionError("Only provider roles can manage provider profiles.")
    now = now_iso()
    specialty = normalize_specialty(data.get("specialty"))
    existing = get_provider_profile_for_user(user["id"])
    values = (
        provider_type_for_role(user["role"]),
        specialty,
        (data.get("qualifications") or "").strip(),
        (data.get("license_identifier") or "").strip(),
        (data.get("organization") or "").strip(),
        (data.get("address") or "").strip(),
        (data.get("city") or "").strip(),
        (data.get("state") or "").strip(),
        (data.get("postal_code") or "").strip(),
        data.get("latitude") or None,
        data.get("longitude") or None,
        (data.get("public_phone") or "").strip(),
        now,
        user["id"],
    )
    db = get_db()
    if existing:
        db.execute(
            """
            UPDATE provider_profiles
            SET provider_type=?, specialty=?, qualifications=?, license_identifier=?, organization=?,
                address=?, city=?, state=?, postal_code=?, latitude=?, longitude=?, public_phone=?,
                verification_status='pending', updated_at=?
            WHERE user_id=?
            """,
            values,
        )
    else:
        db.execute(
            """
            INSERT INTO provider_profiles
            (user_id, provider_type, specialty, qualifications, license_identifier, organization, address,
             city, state, postal_code, latitude, longitude, public_phone, verification_status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (user["id"], *values[:-1], now),
        )


def search_registered_providers(category=None, specialty=None, location=None):
    params = []
    clauses = ["u.active=1", "p.verification_status='verified'"]
    if category:
        clauses.append("p.provider_type=?")
        params.append(category)
    if specialty:
        clauses.append("LOWER(p.specialty)=LOWER(?)")
        params.append(normalize_specialty(specialty))
    if location:
        clauses.append("(LOWER(p.city) LIKE LOWER(?) OR LOWER(p.address) LIKE LOWER(?))")
        params.extend([f"%{location}%", f"%{location}%"])
    rows = get_db().execute(
        f"""
        SELECT p.*, u.name
        FROM provider_profiles p
        JOIN users u ON u.id=p.user_id
        WHERE {' AND '.join(clauses)}
        ORDER BY p.updated_at DESC
        LIMIT 25
        """,
        params,
    ).fetchall()
    return [public_provider(row) for row in rows]


def public_provider(row):
    return {
        "id": row["id"],
        "name": row["organization"] or row["name"],
        "category": row["provider_type"],
        "specialty": row["specialty"],
        "address": row["address"],
        "city": row["city"],
        "state": row["state"],
        "postal_code": row["postal_code"],
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "phone": row["public_phone"],
        "verification_status": row["verification_status"],
        "source": "zendoc_provider_network",
    }


def create_schedule(user, data):
    profile = get_provider_profile_for_user(user["id"])
    if not profile:
        raise ValueError("Create a provider profile before adding schedule.")
    weekday = int(data.get("weekday"))
    if weekday < 0 or weekday > 6:
        raise ValueError("Weekday must be 0-6.")
    slot_minutes = int(data.get("slot_minutes") or 30)
    if slot_minutes < 10 or slot_minutes > 180:
        raise ValueError("Slot length must be between 10 and 180 minutes.")
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    if not start_time or not end_time or start_time >= end_time:
        raise ValueError("Schedule end time must be after start time.")
    get_db().execute(
        """
        INSERT INTO provider_schedules
        (provider_profile_id, weekday, start_time, end_time, slot_minutes, active, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 1, ?, ?)
        """,
        (profile["id"], weekday, start_time, end_time, slot_minutes, now_iso(), now_iso()),
    )


def available_slots(provider_profile_id, date_text):
    profile = get_db().execute("SELECT * FROM provider_profiles WHERE id=?", (provider_profile_id,)).fetchone()
    if not profile:
        return []
    try:
        date_value = datetime.fromisoformat(date_text).date()
    except ValueError:
        return []
    if date_value < datetime.now(timezone.utc).date():
        return []
    weekday = date_value.weekday()
    schedules = get_db().execute(
        "SELECT * FROM provider_schedules WHERE provider_profile_id=? AND weekday=? AND active=1",
        (provider_profile_id, weekday),
    ).fetchall()
    booked = {
        row["scheduled_for"][:16]
        for row in get_db().execute(
            "SELECT scheduled_for FROM appointments WHERE provider_id=? AND status IN ('requested','confirmed')",
            (profile["user_id"],),
        ).fetchall()
    }
    slots = []
    for schedule in schedules:
        start = datetime.fromisoformat(f"{date_value.isoformat()}T{schedule['start_time']}")
        end = datetime.fromisoformat(f"{date_value.isoformat()}T{schedule['end_time']}")
        cursor = start
        while cursor + timedelta(minutes=schedule["slot_minutes"]) <= end:
            value = cursor.strftime("%Y-%m-%dT%H:%M")
            if value not in booked and cursor.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc):
                slots.append(value)
            cursor += timedelta(minutes=schedule["slot_minutes"])
    return slots


def book_provider_slot(patient, provider_profile_id, scheduled_for, reason):
    profile = get_db().execute("SELECT * FROM provider_profiles WHERE id=?", (provider_profile_id,)).fetchone()
    if not profile:
        raise ValueError("Provider not found.")
    if profile["verification_status"] != "verified":
        raise PermissionError("Provider is not verified for connected booking.")
    slot_key = scheduled_for[:16]
    if slot_key not in available_slots(provider_profile_id, scheduled_for[:10]):
        raise ValueError("Selected slot is unavailable.")
    existing = get_db().execute(
        """
        SELECT id FROM appointments
        WHERE provider_id=? AND substr(scheduled_for, 1, 16)=? AND status IN ('requested','confirmed')
        """,
        (profile["user_id"], slot_key),
    ).fetchone()
    if existing:
        raise ValueError("Selected slot is already booked.")
    get_db().execute(
        """
        INSERT INTO appointments
        (patient_id, provider_id, provider_profile_id, provider_name, specialty, scheduled_for, reason, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'requested', ?, ?)
        """,
        (
            patient["id"],
            profile["user_id"],
            profile["id"],
            profile["organization"] or "ZENDOC Provider",
            profile["specialty"],
            scheduled_for,
            reason,
            now_iso(),
            now_iso(),
        ),
    )
