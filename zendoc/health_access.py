import json
from datetime import datetime, timezone

from .db import get_db, now_iso


HEALTH_SCOPES = ("profile", "reports", "appointments", "measurements", "timeline")
PROVIDER_ACCESS_ROLES = ("doctor", "hospital")


def _value(row, key, default=None):
    if row is None:
        return default
    if hasattr(row, "keys") and key in row.keys():
        return row[key]
    return row.get(key, default) if isinstance(row, dict) else default


def _parse_datetime(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Expiration must be a valid ISO date or date-time.") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_scopes(values):
    if isinstance(values, str):
        values = [item.strip() for item in values.split(",")]
    scopes = sorted({str(item).strip().lower() for item in (values or []) if str(item).strip()})
    invalid = [scope for scope in scopes if scope not in HEALTH_SCOPES]
    if invalid:
        raise ValueError(f"Unsupported access scope: {', '.join(invalid)}")
    if not scopes:
        raise ValueError("Select at least one health-data scope.")
    return scopes


def has_active_grant(patient_id, provider_id, scope):
    if scope not in HEALTH_SCOPES:
        return False
    rows = get_db().execute(
        """
        SELECT * FROM health_access_grants
        WHERE patient_id=? AND provider_id=? AND revoked_at IS NULL
        ORDER BY created_at DESC
        """,
        (patient_id, provider_id),
    ).fetchall()
    now = datetime.now(timezone.utc)
    for row in rows:
        try:
            scopes = json.loads(row["scopes"])
        except (TypeError, json.JSONDecodeError):
            scopes = []
        expires_at = _parse_datetime(row["expires_at"]) if row["expires_at"] else None
        if scope in scopes and (expires_at is None or expires_at > now):
            return True
    return False


def authorize_patient(actor, patient_id=None, scope=None):
    actor_id = int(_value(actor, "id", 0) or 0)
    role = _value(actor, "role")
    target_id = int(patient_id or actor_id)
    if not actor_id or not target_id:
        raise PermissionError("Authentication is required.")
    patient = get_db().execute(
        "SELECT id, name, role, active FROM users WHERE id=? AND role='patient' AND active=1",
        (target_id,),
    ).fetchone()
    if not patient:
        raise LookupError("Patient not found.")
    if role == "patient":
        if actor_id != target_id:
            raise PermissionError("You cannot access another patient's health data.")
        return target_id
    if role == "admin":
        return target_id
    if role in PROVIDER_ACCESS_ROLES and scope and has_active_grant(target_id, actor_id, scope):
        return target_id
    raise PermissionError("Patient consent is required for this health-data scope.")


def create_access_grant(patient, data):
    if _value(patient, "role") != "patient":
        raise PermissionError("Only patients can grant access to their health data.")
    try:
        provider_profile_id = int(data.get("provider_profile_id"))
    except (TypeError, ValueError) as error:
        raise ValueError("A valid provider profile is required.") from error
    provider = get_db().execute(
        """
        SELECT pp.id profile_id, pp.user_id, pp.organization, pp.verification_status,
               u.name, u.role, u.active
        FROM provider_profiles pp JOIN users u ON u.id=pp.user_id
        WHERE pp.id=?
        """,
        (provider_profile_id,),
    ).fetchone()
    if not provider or provider["verification_status"] != "verified" or not provider["active"]:
        raise ValueError("Access can only be granted to an active, verified provider.")
    if provider["role"] not in PROVIDER_ACCESS_ROLES:
        raise ValueError("This provider type cannot receive patient health-history access.")
    scopes = normalize_scopes(data.get("scopes"))
    expires_at = _parse_datetime(data.get("expires_at"))
    if expires_at and expires_at <= datetime.now(timezone.utc):
        raise ValueError("Expiration must be in the future.")
    now = now_iso()
    cursor = get_db().execute(
        """
        INSERT INTO health_access_grants
        (patient_id,provider_id,provider_profile_id,scopes,expires_at,revoked_at,created_at,updated_at)
        VALUES (?,?,?,?,?,NULL,?,?)
        """,
        (
            patient["id"],
            provider["user_id"],
            provider_profile_id,
            json.dumps(scopes),
            expires_at.isoformat(timespec="seconds") if expires_at else None,
            now,
            now,
        ),
    )
    return cursor.lastrowid


def list_access_grants(patient_id):
    rows = get_db().execute(
        """
        SELECT hag.*, u.name provider_name, pp.organization, pp.specialty
        FROM health_access_grants hag
        JOIN users u ON u.id=hag.provider_id
        LEFT JOIN provider_profiles pp ON pp.id=hag.provider_profile_id
        WHERE hag.patient_id=? ORDER BY hag.created_at DESC
        """,
        (patient_id,),
    ).fetchall()
    now = datetime.now(timezone.utc)
    grants = []
    for row in rows:
        item = dict(row)
        try:
            item["scopes"] = json.loads(item["scopes"])
        except (TypeError, json.JSONDecodeError):
            item["scopes"] = []
        expires = _parse_datetime(item["expires_at"]) if item["expires_at"] else None
        item["active"] = item["revoked_at"] is None and (expires is None or expires > now)
        grants.append(item)
    return grants


def revoke_access_grant(patient, grant_id):
    if _value(patient, "role") != "patient":
        raise PermissionError("Only the patient can revoke this access grant.")
    row = get_db().execute(
        "SELECT id FROM health_access_grants WHERE id=? AND patient_id=?",
        (grant_id, patient["id"]),
    ).fetchone()
    if not row:
        raise LookupError("Access grant not found.")
    now = now_iso()
    get_db().execute(
        "UPDATE health_access_grants SET revoked_at=?, updated_at=? WHERE id=?",
        (now, now, grant_id),
    )

