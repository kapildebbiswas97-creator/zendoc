"""IoT Health Device Hub truth boundary.

This module can store a user's device inventory today. Registering a record is
not proof that a physical device is paired or that ZENDOC has a manufacturer
integration. Public/browser/API callers cannot create trusted device provenance
without a separately verified device-ingestion adapter.
"""

from .db import get_db, now_iso


DEVICE_TYPES = [
    {"type": "blood_pressure_monitor", "name": "Blood Pressure Monitor", "metrics": ["blood_pressure"], "icon": "heartbeat"},
    {"type": "glucometer", "name": "Smart Glucometer", "metrics": ["blood_glucose"], "icon": "tint"},
    {"type": "pulse_oximeter", "name": "Pulse Oximeter", "metrics": ["oxygen_saturation", "heart_rate"], "icon": "wave-square"},
    {"type": "smartwatch", "name": "Smartwatch / Fitness Band", "metrics": ["heart_rate", "steps", "sleep"], "icon": "stopwatch"},
    {"type": "smart_scale", "name": "Smart Weight Scale", "metrics": ["weight", "bmi"], "icon": "weight"},
    {"type": "thermometer", "name": "Digital Thermometer", "metrics": ["temperature"], "icon": "thermometer-half"},
    {"type": "ecg_monitor", "name": "Portable ECG Device", "metrics": ["ecg_rhythm"], "icon": "microchip"},
]


def _user_id(user):
    uid = user["id"] if hasattr(user, "__getitem__") else getattr(user, "id", None)
    return int(uid or 0)


def list_supported_device_types():
    """Return supported device catalog."""
    return DEVICE_TYPES


def connect_device(user, data):
    """Register a device record without claiming a live device connection."""
    uid = _user_id(user)
    if not uid:
        raise PermissionError("Authentication required.")

    name = str(data.get("device_name") or "").strip()
    if not name:
        raise ValueError("device_name is required.")

    device_type = str(data.get("device_type") or "smartwatch").strip().lower()
    known_types = {item["type"] for item in DEVICE_TYPES}
    if device_type not in known_types:
        raise ValueError("Unsupported device_type.")

    manufacturer = str(data.get("manufacturer") or "").strip() or None
    model = str(data.get("model") or "").strip() or None
    device_identifier = str(data.get("device_identifier") or "").strip() or None

    now = now_iso()
    db = get_db()
    cursor = db.execute(
        """INSERT INTO health_devices
        (user_id, device_name, device_type, manufacturer, model, device_identifier, status, last_synced_at, created_at)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (uid, name, device_type, manufacturer, model, device_identifier, "registered", None, now),
    )
    db.commit()
    result = get_device(user, cursor.lastrowid)
    result["live_device_sync"] = False
    result["integration_status"] = "integration_required"
    result["truth_notice"] = (
        "This is a user-registered device record only. It does not prove pairing, "
        "manufacturer connectivity, or automatic measurement sync."
    )
    return result


def list_devices(user):
    """List registered health-device records for the user."""
    uid = _user_id(user)
    rows = get_db().execute(
        "SELECT * FROM health_devices WHERE user_id=? ORDER BY created_at DESC",
        (uid,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_device(user, device_id):
    """Get one registered device record owned by the user."""
    uid = _user_id(user)
    row = get_db().execute(
        "SELECT * FROM health_devices WHERE id=? AND user_id=?",
        (device_id, uid),
    ).fetchone()
    if not row:
        raise LookupError("Device not found.")
    return dict(row)


def sync_device_measurement(user, device_id, metric_type, metric_value, unit=None, recorded_at=None, notes=None):
    """Fail closed until a real authenticated device-ingestion adapter exists.

    Historically this public helper accepted typed values and stamped them as
    trusted device evidence. That is not truthful device provenance, so public
    callers are no longer allowed to use this route. Users can enter values
    through Health Monitoring, where they remain manual/user-reported.
    """
    get_device(user, device_id)
    raise ValueError(
        "Automatic device sync is Integration Required. This registered device record is not a live connection. "
        "Enter measurements through Health Monitoring so they remain manual/user-reported."
    )
