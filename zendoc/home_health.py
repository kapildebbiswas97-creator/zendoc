"""Home-health request intake.

The catalog describes request categories, not guaranteed service availability.
A request is not provider-confirmed until the verified connected-provider
fulfilment workflow records assignment and provider acceptance.
"""

from .db import get_db, now_iso
from .family_care import authorize_family_patient


HOME_HEALTH_SERVICES = [
    {
        "id": "doctor_visit",
        "title": "Doctor Home Visit",
        "category": "Medical Care",
        "description": "Request category for a doctor home visit; provider availability is not assumed.",
        "status_badge": "Request Intake",
        "icon": "user-md",
    },
    {
        "id": "nurse_visit",
        "title": "Nursing Care & Dressing",
        "category": "Nursing",
        "description": "Request category for nursing support; provider availability and clinical scope require confirmation.",
        "status_badge": "Request Intake",
        "icon": "user-nurse",
    },
    {
        "id": "physiotherapy",
        "title": "Home Physiotherapy",
        "category": "Rehabilitation",
        "description": "Request category for home physiotherapy; a provider must separately accept the request.",
        "status_badge": "Request Intake",
        "icon": "running",
    },
    {
        "id": "elder_care",
        "title": "Elder Care Attendant",
        "category": "Caregiving",
        "description": "Request category for elder-care assistance; no attendant is assumed available.",
        "status_badge": "Request Intake",
        "icon": "heart",
    },
    {
        "id": "sample_collection",
        "title": "Diagnostic Sample Collection",
        "category": "Diagnostics",
        "description": "Request category for home sample collection; lab/provider fulfilment requires confirmation.",
        "status_badge": "Request Intake",
        "icon": "vial",
    },
    {
        "id": "equipment_rental",
        "title": "Medical Equipment Rental",
        "category": "Equipment",
        "description": "Request category for equipment rental; inventory, price and delivery are not confirmed here.",
        "status_badge": "Request Intake",
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
    allowed_types = {item["id"] for item in HOME_HEALTH_SERVICES}
    if service_type not in allowed_types:
        raise ValueError("Unsupported home-health service_type.")

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
    result = get_home_health_request(user, cursor.lastrowid)
    result["provider_confirmed"] = False
    result["fulfilment_status"] = "request_recorded_unconfirmed"
    result["truth_notice"] = (
        "This ZENDOC request record does not confirm a home-care provider, booking, price or external fulfilment."
    )
    return result


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
    result = []
    for row in rows:
        item = dict(row)
        item["provider_confirmed"] = False
        item["fulfilment_status"] = "request_recorded_unconfirmed"
        result.append(item)
    return result


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
