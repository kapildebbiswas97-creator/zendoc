"""
Saved locations for healthcare search and care requests.

Browser geolocation remains user-initiated in the frontend; this module stores
manual, home, current, and recent locations after the user chooses to save them.
"""

from .db import get_db, now_iso


LOCATION_TYPES = ("home", "current", "recent", "parent_home", "other")


def _user_id(user):
    uid = user["id"] if hasattr(user, "__getitem__") else getattr(user, "id", None)
    return int(uid or 0)


def list_saved_locations(user):
    uid = _user_id(user)
    rows = get_db().execute(
        "SELECT * FROM saved_locations WHERE user_id=? ORDER BY is_default DESC, created_at DESC",
        (uid,),
    ).fetchall()
    return [dict(row) for row in rows]


def save_location(user, data):
    uid = _user_id(user)
    if not uid:
        raise PermissionError("Authentication required.")
    label = str(data.get("label") or "").strip()
    if not label:
        raise ValueError("label is required.")
    address = str(data.get("address") or "").strip()
    if not address:
        raise ValueError("address is required.")
    city = str(data.get("city") or "").strip()
    if not city:
        raise ValueError("city is required.")
    location_type = str(data.get("location_type") or data.get("type") or "other").strip().lower()
    if location_type not in LOCATION_TYPES:
        location_type = "other"
    state = str(data.get("state") or "").strip() or None
    country = str(data.get("country") or "India").strip() or "India"
    latitude = _optional_float(data.get("latitude"), "latitude")
    longitude = _optional_float(data.get("longitude"), "longitude")
    is_default = 1 if data.get("is_default") else 0
    db = get_db()
    if is_default:
        db.execute("UPDATE saved_locations SET is_default=0 WHERE user_id=?", (uid,))
    cursor = db.execute(
        """
        INSERT INTO saved_locations
        (user_id, label, address, city, state, country, latitude, longitude, is_default, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (uid, f"{label} ({location_type})", address, city, state, country, latitude, longitude, is_default, now_iso()),
    )
    db.commit()
    return get_saved_location(user, cursor.lastrowid)


def get_saved_location(user, location_id):
    uid = _user_id(user)
    row = get_db().execute(
        "SELECT * FROM saved_locations WHERE id=? AND user_id=?",
        (location_id, uid),
    ).fetchone()
    if not row:
        raise LookupError("Saved location not found.")
    return dict(row)


def delete_saved_location(user, location_id):
    uid = _user_id(user)
    get_saved_location(user, location_id)
    get_db().execute("DELETE FROM saved_locations WHERE id=? AND user_id=?", (location_id, uid))
    get_db().commit()
    return True


def _optional_float(value, label):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be numeric.") from error
