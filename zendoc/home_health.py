"""
Home Healthcare Service.

Services include doctor home visits, nurse visits, physiotherapy, elder care,
sample collection, and medical equipment rental.
Transparent status tracking without fabricated doctors or prices.
"""

from .db import get_db, now_iso
from .family_care import authorize_family_patient


HOME_HEALTH_SERVICES = [
    {
        "id": "doctor_visit",
        "title": "Doctor Home Visit",
        "category": "Medical Care",
        "description": "General physician or specialist visit at your doorstep.",
        "status_badge": "Integration Required",
        "icon": "user-md",
    },
    {
        "id": "nurse_visit",
        "title": "Nursing Care & Dressing",
        "category": "Nursing",
        "description": "Wound dressing, injections, IV fluids, and vital checks.",
        "status_badge": "Beta",
        "icon": "user-nurse",
    },
    {
        "id": "physiotherapy",
        "title": "Home Physiotherapy",
        "category": "Rehabilitation",
        "description": "Post-op recovery, joint mobility, stroke rehab, and pain management.",
        "status_badge": "Beta",
        "icon": "running",
    },
    {
        "id": "elder_care",
        "title": "Elder Care Attendant",
        "category": "Caregiving",
        "description": "Full-day or part-day trained attendant for elderly assistance.",
        "status_badge": "Integration Required",
        "icon": "heart",
    },
    {
        "id": "sample_collection",
        "title": "Diagnostic Sample Collection",
        "category": "Diagnostics",
        "description": "Blood and urine sample collection at home for lab testing.",
        "status_badge": "Integration Required",
        "icon": "vial",
    },
    {
        "id": "equipment_rental",
        "title": "Medical Equipment Rental",
        "category": "Equipment",
        "description": "Oxygen concentrators, hospital beds, wheelchairs, and CPAP machines.",
        "status_badge": "Integration Required",
        "icon": "wheelchair",
    },
]


def _user_id(user):
    uid = user["id"] if hasattr(user, "__getitem__") else getattr(user, "id", None)
    return int(uid or 0)


def list_home_health_services():
    """Return available home healthcare service categories."""
    return HOME_HEALTH_SERVICES


def create_home_health_request(user, data):
    """Create a home healthcare request."""
    uid = _user_id(user)
    if not uid:
        raise PermissionError("Authentication required.")

    service_type = str(data.get("service_type") or "").strip()
    if not service_type:
        raise ValueError("service_type is required.")

    scheduled_date = str(data.get("scheduled_date") or "").strip()
    if not scheduled_date:
        raise ValueError("scheduled_date is required.")

    address = str(data.get("address") or "").strip()
    if not address:
        raise ValueError("address is required.")

    city = str(data.get("city") or (user.get("city") if hasattr(user, "get") else None) or "Unknown").strip()
    notes = str(data.get("notes") or "").strip() or None

    patient_id = data.get("patient_id")
    target_patient_id = authorize_family_patient(user, patient_id, "home_health")

    now = now_iso()
    db = get_db()
    cursor = db.execute(
        """INSERT INTO home_health_requests
        (patient_id, requested_by, service_type, scheduled_date, address, city, status, notes, created_at)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (target_patient_id, uid, service_type, scheduled_date, address, city, "requested", notes, now),
    )
    db.commit()
    return get_home_health_request(user, cursor.lastrowid)


def list_home_health_requests(user):
    """List home healthcare requests for user or dependent."""
    uid = _user_id(user)
    rows = get_db().execute(
        """SELECT hhr.*, u.name patient_name
           FROM home_health_requests hhr
           JOIN users u ON u.id=hhr.patient_id
           WHERE hhr.requested_by=? OR hhr.patient_id=?
           ORDER BY hhr.created_at DESC""",
        (uid, uid),
    ).fetchall()
    return [dict(r) for r in rows]


def get_home_health_request(user, request_id):
    """Get single home health request."""
    uid = _user_id(user)
    row = get_db().execute(
        """SELECT hhr.*, u.name patient_name
           FROM home_health_requests hhr
           JOIN users u ON u.id=hhr.patient_id
           WHERE hhr.id=? AND (hhr.requested_by=? OR hhr.patient_id=?)""",
        (request_id, uid, uid),
    ).fetchone()
    if not row:
        raise LookupError("Home health request not found.")
    return dict(row)
