"""
Pharmacy & Medicine Services.

Supports medicine search, nearby pharmacy discovery, medicine delivery requests,
prescription linking, and refill reminders.
Never invents stock availability.
"""

import json

from .db import get_db, now_iso
from .family_care import authorize_family_patient


# Seed catalog of essential medicines (general reference)
MEDICINE_CATALOG = [
    {"name": "Paracetamol 500mg", "category": "Analgesic / Antipyretic", "rx_required": False, "uses": "Fever and mild to moderate pain relief."},
    {"name": "Ibuprofen 400mg", "category": "NSAID / Anti-inflammatory", "rx_required": False, "uses": "Pain, inflammation, and fever."},
    {"name": "Amoxicillin 500mg", "category": "Antibiotic", "rx_required": True, "uses": "Bacterial infections. Requires prescription."},
    {"name": "Cetirizine 10mg", "category": "Antihistamine", "rx_required": False, "uses": "Allergies, runny nose, sneezing, and hives."},
    {"name": "Metformin 500mg", "category": "Antidiabetic", "rx_required": True, "uses": "Type 2 diabetes blood sugar management."},
    {"name": "Amlodipine 5mg", "category": "Antihypertensive", "rx_required": True, "uses": "High blood pressure and angina."},
    {"name": "Omeprazole 20mg", "category": "Proton Pump Inhibitor", "rx_required": False, "uses": "Acid reflux, heartburn, and stomach ulcers."},
    {"name": "Azithromycin 500mg", "category": "Antibiotic", "rx_required": True, "uses": "Respiratory and skin infections."},
    {"name": "ORAL REHYDRATION SALTS (ORS)", "category": "Electrolytes", "rx_required": False, "uses": "Dehydration from diarrhea, vomiting, or sweating."},
    {"name": "Pantoprazole 40mg", "category": "Antacid", "rx_required": False, "uses": "Gastric acidity and GERD."},
]


def _user_id(user):
    uid = user["id"] if hasattr(user, "__getitem__") else getattr(user, "id", None)
    return int(uid or 0)


def search_medicines(query=None):
    """Search medicine reference catalog."""
    if not query:
        return MEDICINE_CATALOG
    text = str(query).strip().lower()
    return [
        m for m in MEDICINE_CATALOG
        if text in m["name"].lower() or text in m["category"].lower() or text in m["uses"].lower()
    ]


def list_nearby_pharmacies(city=None):
    """List verified pharmacy providers from the database."""
    db = get_db()
    conditions = ["u.role='pharmacy'", "u.active=1", "LOWER(pp.verification_status)='verified'"]
    params = []
    if city:
        conditions.append("(LOWER(pp.city) LIKE ? OR LOWER(u.city) LIKE ?)")
        text = f"%{str(city).strip().lower()}%"
        params.extend([text, text])

    where = " WHERE " + " AND ".join(conditions)
    rows = db.execute(
        f"""SELECT pp.*, u.name pharmacy_name, u.phone, u.city user_city
           FROM provider_profiles pp
           JOIN users u ON u.id=pp.user_id
           {where} ORDER BY pp.verification_status DESC, u.name""",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def create_medicine_order(user, data):
    """Place a medicine delivery request."""
    uid = _user_id(user)
    if not uid:
        raise PermissionError("Authentication required.")

    items = data.get("items")
    if not items:
        raise ValueError("Order must contain at least one medicine item.")

    address = str(data.get("delivery_address") or "").strip()
    if not address:
        raise ValueError("delivery_address is required.")

    pharmacy_id = data.get("pharmacy_id")
    prescription_record_id = data.get("prescription_record_id")
    patient_id = authorize_family_patient(user, data.get("patient_id"), "pharmacy")

    now = now_iso()
    db = get_db()
    cursor = db.execute(
        """INSERT INTO medicine_orders
        (patient_id, ordered_by, pharmacy_id, items_json, delivery_address, status, prescription_record_id, created_at)
        VALUES (?,?,?,?,?,?,?,?)""",
        (patient_id, uid, pharmacy_id, json.dumps(items), address, "pending", prescription_record_id, now),
    )
    db.commit()
    return get_medicine_order(user, cursor.lastrowid)


def list_medicine_orders(user):
    """List medicine orders for user."""
    uid = _user_id(user)
    rows = get_db().execute(
        """SELECT mo.*, u.name patient_name, pharm.name pharmacy_name
           FROM medicine_orders mo
           JOIN users u ON u.id=mo.patient_id
           LEFT JOIN users pharm ON pharm.id=mo.pharmacy_id
           WHERE mo.ordered_by=? OR mo.patient_id=?
           ORDER BY mo.created_at DESC""",
        (uid, uid),
    ).fetchall()
    result = []
    for r in rows:
        item = dict(r)
        try:
            item["items"] = json.loads(item["items_json"])
        except Exception:
            item["items"] = []
        result.append(item)
    return result


def get_medicine_order(user, order_id):
    """Get single medicine order."""
    uid = _user_id(user)
    row = get_db().execute(
        """SELECT mo.*, u.name patient_name
           FROM medicine_orders mo
           JOIN users u ON u.id=mo.patient_id
           WHERE mo.id=? AND (mo.ordered_by=? OR mo.patient_id=?)""",
        (order_id, uid, uid),
    ).fetchone()
    if not row:
        raise LookupError("Medicine order not found.")
    item = dict(row)
    try:
        item["items"] = json.loads(item["items_json"])
    except Exception:
        item["items"] = []
    return item


# ---------------------------------------------------------------------------
# Medicine Reminders
# ---------------------------------------------------------------------------

def create_medicine_reminder(user, data):
    """Create a medicine refill / dosage reminder."""
    uid = _user_id(user)
    name = str(data.get("medicine_name") or "").strip()
    if not name:
        raise ValueError("medicine_name is required.")

    time_str = str(data.get("reminder_time") or "08:00").strip()
    dosage = str(data.get("dosage") or "").strip() or None
    frequency = str(data.get("frequency") or "daily").strip().lower()

    now = now_iso()
    cursor = get_db().execute(
        """INSERT INTO medicine_reminders
        (user_id, medicine_name, dosage, frequency, reminder_time, active, created_at)
        VALUES (?,?,?,?,?,1,?)""",
        (uid, name, dosage, frequency, time_str, now),
    )
    get_db().commit()
    return dict(get_db().execute("SELECT * FROM medicine_reminders WHERE id=?", (cursor.lastrowid,)).fetchone())


def list_medicine_reminders(user):
    """List active medicine reminders."""
    uid = _user_id(user)
    rows = get_db().execute(
        "SELECT * FROM medicine_reminders WHERE user_id=? AND active=1 ORDER BY reminder_time ASC",
        (uid,),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_medicine_reminder(user, reminder_id):
    """Deactivate a medicine reminder."""
    uid = _user_id(user)
    get_db().execute("UPDATE medicine_reminders SET active=0 WHERE id=? AND user_id=?", (reminder_id, uid))
    get_db().commit()
    return True
