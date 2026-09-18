"""Medical-transport request intake.

The catalog describes transport request categories only. ZENDOC does not
dispatch vehicles from this module, and recording a request is never presented
as provider acceptance or emergency-service confirmation.
"""

from .db import get_db, now_iso
from .family_care import authorize_family_patient
from .safety import SafetyEngine


TRANSPORT_TYPES = [
    {
        "id": "emergency_ambulance",
        "name": "Emergency Ambulance (108 / Urgent)",
        "description": "Emergency transport request category. ZENDOC does not dispatch this vehicle; contact local emergency services directly.",
        "badge": "Emergency Guidance",
        "is_emergency": True,
    },
    {
        "id": "bls_ambulance",
        "name": "Basic Life Support (BLS)",
        "description": "Request category for BLS-capable transport. Equipment and provider availability require separate confirmation.",
        "badge": "Request Intake",
        "is_emergency": False,
    },
    {
        "id": "als_ambulance",
        "name": "Advanced Life Support (ALS / ICU)",
        "description": "Request category for ALS/ICU-capable transport. ZENDOC does not claim such a vehicle is available or dispatched.",
        "badge": "Emergency Guidance",
        "is_emergency": True,
    },
    {
        "id": "patient_transport",
        "name": "Non-Emergency Patient Transport",
        "description": "Request category for scheduled non-emergency transport; fulfilment requires provider confirmation.",
        "badge": "Request Intake",
        "is_emergency": False,
    },
    {
        "id": "wheelchair_transport",
        "name": "Wheelchair Accessible Van",
        "description": "Request category for wheelchair-accessible transport; vehicle features require provider confirmation.",
        "badge": "Request Intake",
        "is_emergency": False,
    },
    {
        "id": "hospital_transfer",
        "name": "Inter-Hospital Transfer",
        "description": "Request category for inter-facility transfer; coordination and medical escort are not assumed.",
        "badge": "Request Intake",
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
    transport_catalog = {item["id"]: item for item in TRANSPORT_TYPES}
    if transport_type not in transport_catalog:
        raise ValueError("Unsupported medical transport_type.")
    destination = str(data.get("destination_address") or "").strip() or None
    notes = str(data.get("notes") or "").strip() or None

    # Safety check on notes / text
    safety_assessment = SafetyEngine().assess(notes or "")
    type_is_emergency = bool(transport_catalog[transport_type].get("is_emergency"))
    urgency = "emergency" if safety_assessment["emergency"] or type_is_emergency else "routine"

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
    if safety_assessment["emergency"]:
        safety_warning = safety_assessment["guidance"]
    elif type_is_emergency:
        safety_warning = (
            "This is an emergency transport category, but ZENDOC did not dispatch a vehicle. "
            "Contact the appropriate local emergency service directly if urgent care is needed."
        )
    else:
        safety_warning = None
    result["safety_warning"] = safety_warning
    result["dispatch_confirmed"] = False
    result["provider_confirmed"] = False
    result["fulfilment_status"] = "request_recorded_unconfirmed"
    result["truth_notice"] = (
        "This ZENDOC request record does not confirm dispatch, a vehicle, equipment, price, ETA or provider acceptance."
    )
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
    result = []
    for row in rows:
        item = dict(row)
        item["dispatch_confirmed"] = False
        item["provider_confirmed"] = False
        item["fulfilment_status"] = "request_recorded_unconfirmed"
        result.append(item)
    return result


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
