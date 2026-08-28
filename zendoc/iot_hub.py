"""
IoT Health Device Hub.

Connects smartwatches, BP monitors, glucometers, pulse oximeters, ECG devices,
and smart scales to ZENDOC. Records measurement provenance as 'device'.
"""

from .db import get_db, now_iso
from .health_analytics import create_measurement


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
    """Register a new health device."""
    uid = _user_id(user)
    if not uid:
        raise PermissionError("Authentication required.")

    name = str(data.get("device_name") or "").strip()
    if not name:
        raise ValueError("device_name is required.")

    device_type = str(data.get("device_type") or "smartwatch").strip().lower()
    manufacturer = str(data.get("manufacturer") or "").strip() or None
    model = str(data.get("model") or "").strip() or None
    device_identifier = str(data.get("device_identifier") or f"DEV-{uid}-{now_iso()[:19]}").strip()

    now = now_iso()
    db = get_db()
    cursor = db.execute(
        """INSERT INTO health_devices
        (user_id, device_name, device_type, manufacturer, model, device_identifier, status, last_synced_at, created_at)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (uid, name, device_type, manufacturer, model, device_identifier, "connected", now, now),
    )
    db.commit()
    return get_device(user, cursor.lastrowid)


def list_devices(user):
    """List connected health devices for user."""
    uid = _user_id(user)
    rows = get_db().execute(
        "SELECT * FROM health_devices WHERE user_id=? ORDER BY created_at DESC",
        (uid,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_device(user, device_id):
    """Get single connected device."""
    uid = _user_id(user)
    row = get_db().execute(
        "SELECT * FROM health_devices WHERE id=? AND user_id=?",
        (device_id, uid),
    ).fetchone()
    if not row:
        raise LookupError("Device not found.")
    return dict(row)


def sync_device_measurement(user, device_id, metric_type, metric_value, unit=None, recorded_at=None, notes=None):
    """
    Log a measurement synced from a connected device.
    Sets provenance source='device' and notes device_identifier.
    """
    device = get_device(user, device_id)
    now = now_iso()

    # Update last_synced_at timestamp on device
    get_db().execute("UPDATE health_devices SET last_synced_at=? WHERE id=?", (now, device_id))
    get_db().commit()

    # Delegate measurement storage to authoritative health_analytics module with provenance
    measurement_notes = f"Synced from {device['device_name']} ({device['device_identifier']}). {notes or ''}".strip()
    measurement_id = create_measurement(
        user,
        {
            "metric_type": metric_type,
            "metric_value": metric_value,
            "unit": unit,
            "recorded_at": recorded_at or now,
            "source": "device",
            "notes": measurement_notes,
        },
        trusted_source=True,
    )
    return dict(get_db().execute("SELECT * FROM health_metrics WHERE id=?", (measurement_id,)).fetchone())
