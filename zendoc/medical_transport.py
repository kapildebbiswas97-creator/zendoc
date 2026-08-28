"""
Medical Transport & Ambulance Service.

Provides emergency ambulance, BLS, ALS, wheelchair, and hospital transfer options.
Safety rule: Emergency guidance always fires first for acute symptoms.
"""

from .db import get_db, now_iso
from .family_care import authorize_family_patient
from .safety import SafetyEngine


TRANSPORT_TYPES = [
    {
        "id": "emergency_ambulance",
        "name": "Emergency Ambulance (108 / Urgent)",
        "description": "Fast response medical transport for acute health emergencies.",
        "badge": "Emergency First",
        "is_emergency": True,
    },
    {
        "id": "bls_ambulance",
        "name": "Basic Life Support (BLS)",
        "description": "Equipped with oxygen, stretcher, and basic first-aid for stable patients.",
        "badge": "Standard",
        "is_emergency": False,
    },
    {
        "id": "als_ambulance",
        "name": "Advanced Life Support (ALS / ICU)",
        "description": "Mobile ICU with ventilator, ECG monitor, defibrillator, and paramedic.",
        "badge": "ICU Equipped",
        "is_emergency": True,
    },
    {
        "id": "patient_transport",
        "name": "Non-Emergency Patient Transport",
        "description": "Scheduled transport for hospital appointments and clinic visits.",
        "badge": "Scheduled",
        "is_emergency": False,
    },
    {
        "id": "wheelchair_transport",
        "name": "Wheelchair Accessible Van",
        "description": "Ramp-equipped vehicle for mobility-impaired patients.",
        "badge": "Accessible",
        "is_emergency": False,
    },
    {
        "id": "hospital_transfer",
        "name": "Inter-Hospital Transfer",
        "description": "Coordinated transfer between medical facilities with medical escort.",
        "badge": "Inter-Facility",
        "is_emergency": False,
    },
]


def _user_id(user):
    uid = user["id"] if hasattr(user, "__getitem__") else getattr(user, "id", None)
    return int(uid or 0)


def list_transport_types():
    """Return medical transport types."""
    return TRANSPORT_TYPES


def create_transport_request(user, data):
    """
    Create an ambulance / medical transport request.
    Checks safety engine: if emergency symptoms mentioned, returns emergency warning flag.
    """
    uid = _user_id(user)
    if not uid:
        raise PermissionError("Authentication required.")

    pickup = str(data.get("pickup_address") or "").strip()
    if not pickup:
        raise ValueError("pickup_address is required.")

    transport_type = str(data.get("transport_type") or "emergency_ambulance").strip().lower()
    destination = str(data.get("destination_address") or "").strip() or None
    notes = str(data.get("notes") or "").strip() or None

    # Safety check on notes / text
    safety_assessment = SafetyEngine().assess(notes or "")
    urgency = "emergency" if safety_assessment["emergency"] or transport_type == "emergency_ambulance" else "routine"

    patient_id = data.get("patient_id")
    target_patient_id = authorize_family_patient(user, patient_id, "transport")

    now = now_iso()
    db = get_db()
    cursor = db.execute(
        """INSERT INTO ambulance_requests
        (patient_id, requested_by, transport_type, pickup_address, destination_address, urgency, status, notes, created_at)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (target_patient_id, uid, transport_type, pickup, destination, urgency, "requested", notes, now),
    )
    db.commit()

    result = get_transport_request(user, cursor.lastrowid)
    result["safety_warning"] = safety_assessment["guidance"] if safety_assessment["emergency"] else None
    return result


def list_transport_requests(user):
    """List transport requests for user or dependent."""
    uid = _user_id(user)
    rows = get_db().execute(
        """SELECT ar.*, u.name patient_name
           FROM ambulance_requests ar
           JOIN users u ON u.id=ar.patient_id
           WHERE ar.requested_by=? OR ar.patient_id=?
           ORDER BY ar.created_at DESC""",
        (uid, uid),
    ).fetchall()
    return [dict(r) for r in rows]


def get_transport_request(user, request_id):
    """Get details for a single transport request."""
    uid = _user_id(user)
    row = get_db().execute(
        """SELECT ar.*, u.name patient_name
           FROM ambulance_requests ar
           JOIN users u ON u.id=ar.patient_id
           WHERE ar.id=? AND (ar.requested_by=? OR ar.patient_id=?)""",
        (request_id, uid, uid),
    ).fetchone()
    if not row:
        raise LookupError("Transport request not found.")
    return dict(row)
