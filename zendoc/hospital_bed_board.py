"""Tenant-scoped hospital bed-board foundation (no patient identity or admission claims).

This is an *internal, operator-attested* occupancy ledger. It must never be
used as a public live-bed directory, a patient admission, an ambulance dispatch,
or proof of bed availability without hospital-side validation.
"""
from __future__ import annotations

import re
from typing import Any

from .db import get_db, is_integrity_error, now_iso
from .provider_service import get_provider_profile_for_user


VALID_STATES = {"available", "occupied", "cleaning", "maintenance"}
ALLOWED_TRANSITIONS = {
    "available": {"occupied", "maintenance"},
    "occupied": {"cleaning"},
    "cleaning": {"available", "maintenance"},
    "maintenance": {"cleaning"},
}
MAX_BEDS_PER_HOSPITAL = 10000

# Constrain the audit reason to operational codes. Never accept free-text
# patient names, medical details or personally identifying incident notes.
TRANSITION_REASONS = {
    ("available", "occupied"): "operator_attested_occupancy",
    ("occupied", "cleaning"): "operator_attested_vacancy",
    ("cleaning", "available"): "cleaning_completed",
    ("available", "maintenance"): "maintenance_requested",
    ("cleaning", "maintenance"): "maintenance_requested",
    ("maintenance", "cleaning"): "maintenance_completed",
}



def ensure_hospital_bed_schema() -> None:
    get_db().executescript(
        """
        CREATE TABLE IF NOT EXISTS hospital_beds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_profile_id INTEGER NOT NULL REFERENCES provider_profiles(id) ON DELETE CASCADE,
            ward_name TEXT NOT NULL,
            bed_code TEXT NOT NULL,
            occupancy_state TEXT NOT NULL DEFAULT 'available'
                CHECK(occupancy_state IN ('available','occupied','cleaning','maintenance')),
            version INTEGER NOT NULL DEFAULT 0,
            created_by INTEGER NOT NULL REFERENCES users(id),
            updated_by INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(provider_profile_id,ward_name,bed_code)
        );
        CREATE INDEX IF NOT EXISTS idx_hospital_beds_tenant_state
            ON hospital_beds(provider_profile_id,occupancy_state);
        CREATE TABLE IF NOT EXISTS hospital_bed_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bed_id INTEGER NOT NULL REFERENCES hospital_beds(id) ON DELETE CASCADE,
            previous_state TEXT NOT NULL,
            next_state TEXT NOT NULL,
            reason TEXT NOT NULL,
            changed_by INTEGER NOT NULL REFERENCES users(id),
            occurred_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_hospital_bed_events_bed_time
            ON hospital_bed_events(bed_id,occurred_at);
        """
    )


def _value(actor: Any, key: str):
    if isinstance(actor, dict):
        return actor.get(key)
    return actor[key] if actor is not None and hasattr(actor, "keys") and key in actor.keys() else None


def _hospital_profile(actor: Any) -> int:
    """Use exact account ownership, never a client-supplied hospital/tenant ID."""
    if _value(actor, "role") != "hospital" or not _value(actor, "id"):
        raise PermissionError("Only verified hospital accounts may manage their private bed board.")
    user_id = int(_value(actor, "id"))
    account = get_db().execute(
        "SELECT role,active FROM users WHERE id=?", (user_id,)
    ).fetchone()
    if not account or account["role"] != "hospital" or int(account["active"] or 0) != 1:
        raise PermissionError("Hospital account is not active.")
    profile = get_provider_profile_for_user(user_id)
    if (not profile or profile["provider_type"] != "hospital"
            or profile["verification_status"] != "verified"):
        raise PermissionError("A verified hospital profile is required for inpatient operations.")
    return int(profile["id"])


def _strict_keys(payload: dict, allowed: set[str]) -> None:
    extras = set(payload) - allowed
    if extras:
        # Deliberately do not reflect any possibly sensitive key or value.
        raise ValueError("Unexpected bed-board fields. Patient data is not accepted here.")


def _label(value: Any, *, field: str, max_length: int) -> str:
    label = str(value or "").strip()
    if not (1 <= len(label) <= max_length) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._/-]*", label):
        raise ValueError(f"{field} must be 1–{max_length} characters using letters, numbers or ._/-")
    return label


def _bed_dict(row: Any) -> dict:
    keys = ("id", "ward_name", "bed_code", "occupancy_state", "version", "updated_at")
    return {key: row[key] for key in keys}


def list_hospital_beds(actor: Any, *, limit: int = 200) -> dict:
    profile_id = _hospital_profile(actor)
    try:
        safe_limit = max(1, min(int(limit), 500))
    except (ValueError, TypeError):
        raise ValueError("Invalid bed limit.") from None
    db = get_db()
    counts = {
        row["occupancy_state"]: int(row["bed_count"])
        for row in db.execute(
            """SELECT occupancy_state,COUNT(*) AS bed_count FROM hospital_beds
               WHERE provider_profile_id=? GROUP BY occupancy_state""",
            (profile_id,),
        ).fetchall()
    }
    rows = db.execute(
        """SELECT id,ward_name,bed_code,occupancy_state,version,updated_at
           FROM hospital_beds WHERE provider_profile_id=?
           ORDER BY ward_name,bed_code LIMIT ?""",
        (profile_id, safe_limit),
    ).fetchall()
    return {
        "status": "OPERATOR_ATTESTED_ONLY",
        "live_public_availability_verified": False,
        "counts": {state: counts.get(state, 0) for state in sorted(VALID_STATES)},
        "beds": [_bed_dict(row) for row in rows],
        "privacy_notice": "No patient or admission information is stored in the bed board.",
    }


def create_hospital_bed(actor: Any, payload: dict) -> dict:
    profile_id = _hospital_profile(actor)
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object.")
    _strict_keys(payload, {"ward_name", "bed_code"})
    ward = _label(payload.get("ward_name"), field="ward_name", max_length=80)
    code = _label(payload.get("bed_code"), field="bed_code", max_length=40)
    db = get_db()
    existing = db.execute(
        """SELECT id FROM hospital_beds
           WHERE provider_profile_id=? AND ward_name=? AND bed_code=?""",
        (profile_id, ward, code),
    ).fetchone()
    if existing:
        raise ValueError("This ward and bed code already exist in the hospital.")
    current = db.execute(
        "SELECT COUNT(*) AS n FROM hospital_beds WHERE provider_profile_id=?",
        (profile_id,),
    ).fetchone()
    if int(current["n"]) >= MAX_BEDS_PER_HOSPITAL:
        raise ValueError("Bed board limit reached; contact operations for review.")
    now = now_iso()
    user_id = int(_value(actor, "id"))
    try:
        cursor = db.execute(
            """INSERT INTO hospital_beds
               (provider_profile_id,ward_name,bed_code,occupancy_state,version,
                created_by,updated_by,created_at,updated_at)
               VALUES (?,?,?,'available',0,?,?,?,?)""",
            (profile_id, ward, code, user_id, user_id, now, now),
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        if is_integrity_error(exc):
            raise ValueError("This ward and bed code already exist in the hospital.") from exc
        raise
    row = db.execute(
        "SELECT * FROM hospital_beds WHERE id=? AND provider_profile_id=?",
        (int(cursor.lastrowid), profile_id),
    ).fetchone()
    return _bed_dict(row)


def change_hospital_bed_state(actor: Any, bed_id: int, payload: dict) -> dict:
    profile_id = _hospital_profile(actor)
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object.")
    _strict_keys(payload, {"state", "reason", "expected_version"})
    target = str(payload.get("state") or "").strip().lower()
    if target not in VALID_STATES:
        raise ValueError("Unknown bed occupancy state.")
    reason = str(payload.get("reason") or "").strip()
    if reason not in set(TRANSITION_REASONS.values()):
        raise ValueError("A predefined operational reason code is required; do not enter patient information.")
    version_value = payload.get("expected_version")
    if isinstance(version_value, bool) or not isinstance(version_value, int) or version_value < 0:
        raise ValueError("An integer expected_version is required for concurrency safety.")
    db = get_db()
    row = db.execute(
        "SELECT * FROM hospital_beds WHERE id=? AND provider_profile_id=?",
        (int(bed_id), profile_id),
    ).fetchone()
    if not row:
        raise LookupError("Hospital bed not found.")
    before = str(row["occupancy_state"])
    if int(row["version"]) != version_value:
        raise RuntimeError("Bed board changed. Refresh and retry with the latest version.")
    if target not in ALLOWED_TRANSITIONS.get(before, set()):
        raise ValueError(f"Unsupported bed transition from {before} to {target}.")
    if reason != TRANSITION_REASONS.get((before, target)):
        raise ValueError("Operational reason code does not match the requested state transition.")
    now = now_iso()
    user_id = int(_value(actor, "id"))
    result = db.execute(
        """UPDATE hospital_beds SET occupancy_state=?,version=version+1,updated_by=?,updated_at=?
           WHERE id=? AND provider_profile_id=? AND version=? AND occupancy_state=?""",
        (target, user_id, now, int(bed_id), profile_id, version_value, before),
    )
    if result.rowcount != 1:
        db.rollback()
        raise RuntimeError("Bed board changed concurrently; please refresh.")
    db.execute(
        """INSERT INTO hospital_bed_events
           (bed_id,previous_state,next_state,reason,changed_by,occurred_at)
           VALUES (?,?,?,?,?,?)""",
        (int(bed_id), before, target, reason, user_id, now),
    )
    db.commit()
    latest = db.execute(
        "SELECT * FROM hospital_beds WHERE id=? AND provider_profile_id=?",
        (int(bed_id), profile_id),
    ).fetchone()
    return _bed_dict(latest)


def bed_state_history(actor: Any, bed_id: int) -> list[dict]:
    profile_id = _hospital_profile(actor)
    row = get_db().execute(
        "SELECT id FROM hospital_beds WHERE id=? AND provider_profile_id=?",
        (int(bed_id), profile_id),
    ).fetchone()
    if not row:
        raise LookupError("Hospital bed not found.")
    history = get_db().execute(
        """SELECT previous_state,next_state,reason,changed_by,occurred_at
           FROM hospital_bed_events WHERE bed_id=? ORDER BY id DESC LIMIT 100""",
        (int(bed_id),),
    ).fetchall()
    return [dict(item) for item in history]
