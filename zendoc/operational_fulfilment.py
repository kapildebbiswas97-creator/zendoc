"""Truthful operational fulfilment for diagnostics and home-health services.

This module deliberately separates ZENDOC-internal operational state from any
external provider system.  A workflow is marked internally integrated only
when a real, active, verified ZENDOC provider is assigned.  Source records are
committed before CareLoop mirroring so ledger bookkeeping can never fabricate
or roll back provider activity.
"""
from __future__ import annotations

import json

from flask import Blueprint, current_app, jsonify, request

from .care_action_ledger import ALLOWED_TRANSITIONS, create_action, ensure_care_action_ledger_schema
from .care_journey_store import create_persisted_journey
from .care_graph import record_care_continuity_event
from .db import get_db, now_iso
from .home_health import HOME_HEALTH_SERVICES
from .organization_service import assert_resource_tenant
from .routes import audit, require_api_user
from .security import is_owner


bp = Blueprint("operational_fulfilment", __name__)

DIAGNOSTIC_STATUS_TO_ACTION = {
    "requested": "STAGED",
    "accepted": "CONFIRMED",
    "sample_collected": "IN_PROGRESS",
    "processing": "IN_PROGRESS",
    "completed": "COMPLETED",
    "cancelled": "CANCELLED",
    "declined": "BLOCKED",
}
DIAGNOSTIC_TRANSITIONS = {
    "requested": {"accepted", "declined", "cancelled"},
    "accepted": {"sample_collected", "processing", "completed", "cancelled"},
    "sample_collected": {"processing", "completed", "cancelled"},
    "processing": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
    "declined": set(),
}

HOME_HEALTH_STATUS_TO_ACTION = {
    "requested": "STAGED",
    "accepted": "CONFIRMED",
    "in_progress": "IN_PROGRESS",
    "completed": "COMPLETED",
    "cancelled": "CANCELLED",
    "declined": "BLOCKED",
}
HOME_HEALTH_TRANSITIONS = {
    "requested": {"accepted", "declined", "cancelled"},
    "accepted": {"in_progress", "cancelled"},
    "in_progress": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
    "declined": set(),
}
HOME_HEALTH_SERVICE_IDS = {str(item["id"]) for item in HOME_HEALTH_SERVICES}
HOME_HEALTH_SERVICE_TITLES = {str(item["id"]): str(item["title"]) for item in HOME_HEALTH_SERVICES}


def ensure_operational_fulfilment_schema():
    """Create additive provider-capability and assignment tables."""
    get_db().executescript(
        """
        CREATE TABLE IF NOT EXISTS home_health_provider_services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            service_type TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            observed_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(provider_id, service_type)
        );
        CREATE INDEX IF NOT EXISTS idx_home_health_services_lookup
            ON home_health_provider_services(service_type,active,provider_id);

        CREATE TABLE IF NOT EXISTS home_health_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL UNIQUE REFERENCES home_health_requests(id) ON DELETE CASCADE,
            provider_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider_profile_id INTEGER NOT NULL REFERENCES provider_profiles(id) ON DELETE CASCADE,
            assigned_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_home_health_assignments_provider
            ON home_health_assignments(provider_id,request_id);
        """
    )


def _actor_id(actor) -> int:
    try:
        return int(actor["id"])
    except Exception:
        return 0


def _actor_from_user_id(user_id: int):
    return get_db().execute("SELECT * FROM users WHERE id=? AND active=1", (int(user_id),)).fetchone()


def _verified_provider(provider_id: int):
    return get_db().execute(
        """
        SELECT u.id,u.name,u.role,u.active,pp.id AS provider_profile_id,
               pp.provider_type,pp.organization,pp.city,pp.verification_status
        FROM users u
        JOIN provider_profiles pp ON pp.user_id=u.id
        WHERE u.id=? AND u.active=1 AND LOWER(pp.verification_status)='verified'
        """,
        (int(provider_id),),
    ).fetchone()


def _care_action_by_ref(service_ref: str, patient_id: int):
    ensure_care_action_ledger_schema()
    return get_db().execute(
        "SELECT * FROM care_actions WHERE service_ref=? AND patient_id=? ORDER BY id DESC LIMIT 1",
        (service_ref, int(patient_id)),
    ).fetchone()


def _append_care_event(action_id, previous, target, event_type, note, actor_id, provenance):
    get_db().execute(
        """
        INSERT INTO care_action_events
        (action_id,previous_status,status,event_type,note,actor_id,provenance_json,created_at)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            int(action_id), previous, target, event_type, note, actor_id,
            json.dumps(provenance or {}, sort_keys=True, separators=(",", ":")), now_iso(),
        ),
    )


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def ensure_diagnostic_careloop_link(booking_id: int):
    """Idempotently link a provider-backed diagnostic request to CareLoop."""
    ensure_care_action_ledger_schema()
    db = get_db()
    booking = db.execute(
        """
        SELECT b.*, lab.name AS lab_name, lab.active AS lab_active,
               pp.id AS provider_profile_id,pp.provider_type,pp.verification_status,
               dc.name AS test_name
        FROM diagnostic_bookings b
        JOIN users lab ON lab.id=b.lab_id
        JOIN provider_profiles pp ON pp.user_id=lab.id
        JOIN diagnostic_catalog dc ON dc.id=b.test_id
        WHERE b.id=?
        """,
        (int(booking_id),),
    ).fetchone()
    if not booking or not booking["lab_id"]:
        return None
    if not bool(booking["lab_active"]) or str(booking["verification_status"] or "").lower() != "verified":
        return None
    if str(booking["provider_type"] or "").lower() not in {"diagnostic_centre", "diagnostic_center", "lab", "hospital"}:
        return None

    service_ref = f"zendoc_diagnostic_booking:{int(booking_id)}"
    existing = _care_action_by_ref(service_ref, int(booking["patient_id"]))
    if existing:
        return int(existing["id"])

    source_actor = _actor_from_user_id(int(booking["booked_by"]))
    if not source_actor:
        return None
    journey = create_persisted_journey(
        source_actor,
        patient_id=int(booking["patient_id"]),
        provenance={
            "source": "zendoc_verified_diagnostic_booking",
            "diagnostic_booking_id": int(booking_id),
            "lab_id": int(booking["lab_id"]),
        },
    )
    action = create_action(
        source_actor,
        int(journey["id"]),
        {
            "action_type": "diagnostic_service",
            "title": f"{booking['test_name']} with {booking['lab_name']}",
            "rationale": "Patient explicitly requested a fresh verified ZENDOC lab offer.",
            "status": "STAGED",
            "human_confirmation_required": True,
            "owner_type": "patient",
            "owner_id": int(booking["patient_id"]),
            "provider_name": booking["lab_name"],
            "service_ref": service_ref,
            "estimated_cost": booking["price_inr"],
            "evidence": {
                "source_type": "zendoc_diagnostic_booking",
                "diagnostic_booking_id": int(booking_id),
                "provider_acknowledgement_required": True,
            },
            "provenance": {
                "source": "zendoc_verified_diagnostic_booking",
                "diagnostic_booking_id": int(booking_id),
                "lab_id": int(booking["lab_id"]),
                "provider_profile_id": int(booking["provider_profile_id"]),
                "provider_verification_status": booking["verification_status"],
            },
        },
    )
    return int(action["id"])


def _diagnostic_access(actor, booking_id: int):
    db = get_db()
    row = db.execute(
        """
        SELECT b.*,lab.name AS lab_name,lab.active AS lab_active,
               pp.id AS provider_profile_id,pp.verification_status,pp.provider_type,
               dc.name AS test_name
        FROM diagnostic_bookings b
        JOIN users lab ON lab.id=b.lab_id
        LEFT JOIN provider_profiles pp ON pp.user_id=lab.id
        JOIN diagnostic_catalog dc ON dc.id=b.test_id
        WHERE b.id=?
        """,
        (int(booking_id),),
    ).fetchone()
    if not row:
        raise LookupError("Diagnostic booking not found.")
    actor_id = _actor_id(actor)
    assigned_lab = actor_id == int(row["lab_id"] or 0)
    lab_verified = assigned_lab and bool(row["lab_active"]) and str(row["verification_status"] or "").lower() == "verified"
    owner_admin = is_owner(actor)
    patient_side = actor_id in {int(row["patient_id"]), int(row["booked_by"])}
    if not (lab_verified or owner_admin or patient_side):
        raise PermissionError("This diagnostic booking belongs to another patient/provider relationship.")
    if lab_verified:
        assert_resource_tenant(actor, dict(row))
    return row, lab_verified, owner_admin, patient_side


def get_diagnostic_booking(actor, booking_id: int) -> dict:
    row, lab_verified, owner_admin, patient_side = _diagnostic_access(actor, booking_id)
    result = dict(row)
    result["provider_authorized"] = bool(lab_verified or owner_admin)
    result["patient_authorized"] = bool(patient_side)
    result["external_execution"] = False
    result["truth_notice"] = (
        "Status represents this verified lab's ZENDOC workflow. It does not independently verify "
        "an external LIS, sample chain-of-custody, payment, or clinical interpretation."
    )
    return result


def update_diagnostic_booking_status(actor, booking_id: int, target_status: str, note: str | None = None) -> dict:
    """Advance a diagnostic booking with provider tenancy and patient-cancel protection."""
    row, lab_verified, owner_admin, patient_side = _diagnostic_access(actor, booking_id)
    current = str(row["status"] or "requested").strip().lower()
    target = str(target_status or "").strip().lower()
    if target not in DIAGNOSTIC_STATUS_TO_ACTION:
        raise ValueError("Unsupported diagnostic booking status.")
    if target == current:
        return get_diagnostic_booking(actor, booking_id)
    if target not in DIAGNOSTIC_TRANSITIONS.get(current, set()):
        raise ValueError(f"Invalid diagnostic booking transition: {current} -> {target}.")

    if not (lab_verified or owner_admin):
        if not (patient_side and target == "cancelled"):
            raise PermissionError("Only the assigned verified lab may advance this diagnostic workflow.")

    # A provider that has become inactive/unverified cannot advance care. Owner
    # access is retained for administrative recovery, with distinct provenance.
    if not lab_verified and not owner_admin and target != "cancelled":
        raise PermissionError("The assigned diagnostic provider is not currently verified and active.")

    # Ensure the STAGED link exists before the source transition. Failure to
    # mirror must never block the source provider workflow.
    try:
        ensure_diagnostic_careloop_link(booking_id)
    except Exception:
        current_app.logger.exception("Diagnostic CareLoop pre-link failed for booking %s", booking_id)

    source = "PROVIDER_RECORDED" if lab_verified else "OWNER_RECORDED" if owner_admin else "USER_REPORTED"
    now = now_iso()
    db = get_db()
    update = db.execute(
        "UPDATE diagnostic_bookings SET status=?,updated_at=? WHERE id=? AND status=?",
        (target, now, int(booking_id), current),
    )
    if update.rowcount != 1:
        raise ValueError("Diagnostic booking changed concurrently; refresh before retrying.")

    event_type = {
        "accepted": "DIAGNOSTIC_ACCEPTED",
        "sample_collected": "DIAGNOSTIC_SAMPLE_COLLECTED",
        "processing": "DIAGNOSTIC_PROCESSING",
        "completed": "DIAGNOSTIC_COMPLETED",
        "cancelled": "DIAGNOSTIC_CANCELLED",
        "declined": "DIAGNOSTIC_DECLINED",
    }[target]
    summary = str(note or "").strip()[:2000] or {
        "accepted": "Assigned lab acknowledged the diagnostic request in ZENDOC.",
        "sample_collected": "Assigned lab recorded sample collection in ZENDOC.",
        "processing": "Assigned lab recorded that the diagnostic workflow is processing in ZENDOC.",
        "completed": "Assigned lab recorded completion in ZENDOC; no clinical interpretation was generated.",
        "cancelled": "Diagnostic booking was cancelled in ZENDOC.",
        "declined": "Assigned lab declined the diagnostic request in ZENDOC.",
    }[target]
    record_care_continuity_event(
        patient_id=int(row["patient_id"]),
        event_type=event_type,
        title=event_type.replace("_", " ").title(),
        summary=summary,
        source=source,
        source_ref=f"diagnostic:{int(booking_id)}",
        actor_id=_actor_id(actor),
        metadata={
            "booking_id": int(booking_id),
            "lab_id": int(row["lab_id"]),
            "status": target,
            "source": source,
        },
    )
    db.commit()

    try:
        sync_diagnostic_careloop_status(actor, booking_id, target)
    except Exception:
        current_app.logger.exception("Diagnostic CareLoop sync failed after source commit for booking %s", booking_id)
    return get_diagnostic_booking(actor, booking_id)


def sync_diagnostic_careloop_status(actor, booking_id: int, target_status: str):
    db = get_db()
    row = db.execute("SELECT * FROM diagnostic_bookings WHERE id=?", (int(booking_id),)).fetchone()
    if not row:
        raise LookupError("Diagnostic booking not found.")
    action = _care_action_by_ref(f"zendoc_diagnostic_booking:{int(booking_id)}", int(row["patient_id"]))
    if not action:
        return None
    target = DIAGNOSTIC_STATUS_TO_ACTION[str(target_status).lower()]
    current = str(action["status"])
    provenance = {
        "source": "zendoc_verified_diagnostic_booking",
        "diagnostic_booking_id": int(booking_id),
        "lab_id": int(row["lab_id"]),
        "diagnostic_status": str(target_status).lower(),
    }
    note = {
        "CONFIRMED": "Assigned verified ZENDOC lab acknowledged the diagnostic request.",
        "IN_PROGRESS": "Assigned verified ZENDOC lab advanced its diagnostic workflow.",
        "COMPLETED": "Assigned verified ZENDOC lab marked its ZENDOC diagnostic booking completed.",
        "CANCELLED": "Linked ZENDOC diagnostic booking was cancelled.",
        "BLOCKED": "Assigned verified ZENDOC lab declined the diagnostic request.",
        "STAGED": "Diagnostic request is awaiting lab acknowledgement.",
    }[target]
    if current == target:
        _append_care_event(
            int(action["id"]), current, target, "INTERNAL_DIAGNOSTIC_PROGRESS", note,
            _actor_id(actor), provenance,
        )
        db.commit()
        return dict(action)
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise ValueError(f"Linked diagnostic action cannot transition {current} -> {target}.")
    db.execute("UPDATE care_actions SET status=?,updated_at=? WHERE id=?", (target, now_iso(), int(action["id"])))
    _append_care_event(
        int(action["id"]), current, target, "INTERNAL_DIAGNOSTIC_SYNC", note,
        _actor_id(actor), provenance,
    )
    db.commit()
    return dict(db.execute("SELECT * FROM care_actions WHERE id=?", (int(action["id"]),)).fetchone())


# ---------------------------------------------------------------------------
# Home health provider capability + fulfilment
# ---------------------------------------------------------------------------

def publish_home_health_service(actor, service_type: str, active: bool = True) -> dict:
    ensure_operational_fulfilment_schema()
    provider_id = _actor_id(actor)
    if not provider_id:
        raise PermissionError("Authentication required.")
    service_type = str(service_type or "").strip().lower()
    if service_type not in HOME_HEALTH_SERVICE_IDS:
        raise ValueError("Unsupported home-health service type.")
    provider = _verified_provider(provider_id)
    if not provider or str(provider["role"]) not in {"doctor", "hospital"}:
        raise PermissionError("Only an active verified doctor/hospital provider may publish home-health services.")
    if str(provider["role"]) == "doctor" and service_type != "doctor_visit":
        raise PermissionError("Doctor accounts may publish only doctor home-visit capability; other services require an organization provider.")

    db = get_db()
    now = now_iso()
    existing = db.execute(
        "SELECT id FROM home_health_provider_services WHERE provider_id=? AND service_type=?",
        (provider_id, service_type),
    ).fetchone()
    if existing:
        db.execute(
            "UPDATE home_health_provider_services SET active=?,observed_at=?,updated_at=? WHERE id=?",
            (1 if active else 0, now, now, int(existing["id"])),
        )
        service_id = int(existing["id"])
    else:
        cursor = db.execute(
            """
            INSERT INTO home_health_provider_services
            (provider_id,service_type,active,observed_at,created_at,updated_at)
            VALUES (?,?,?,?,?,?)
            """,
            (provider_id, service_type, 1 if active else 0, now, now, now),
        )
        service_id = int(cursor.lastrowid)
    db.commit()
    return dict(db.execute("SELECT * FROM home_health_provider_services WHERE id=?", (service_id,)).fetchone())


def list_home_health_providers(service_type: str, city: str | None = None) -> list[dict]:
    ensure_operational_fulfilment_schema()
    service_type = str(service_type or "").strip().lower()
    if service_type not in HOME_HEALTH_SERVICE_IDS:
        raise ValueError("Unsupported home-health service type.")
    params = [service_type]
    city_sql = ""
    if city:
        city_sql = " AND (LOWER(pp.city) LIKE ? OR LOWER(u.city) LIKE ?)"
        text = f"%{str(city).strip().lower()}%"
        params.extend([text, text])
    rows = get_db().execute(
        f"""
        SELECT s.id AS service_listing_id,s.service_type,s.observed_at,
               u.id AS provider_id,u.name AS provider_name,u.role,
               pp.id AS provider_profile_id,pp.provider_type,pp.organization,pp.city,pp.public_phone,
               pp.verification_status
        FROM home_health_provider_services s
        JOIN users u ON u.id=s.provider_id AND u.active=1
        JOIN provider_profiles pp ON pp.user_id=u.id AND LOWER(pp.verification_status)='verified'
        WHERE s.service_type=? AND s.active=1 {city_sql}
        ORDER BY COALESCE(pp.organization,u.name),u.name
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def assign_home_health_provider(actor, request_id: int, provider_id: int) -> dict:
    ensure_operational_fulfilment_schema()
    db = get_db()
    source = db.execute("SELECT * FROM home_health_requests WHERE id=?", (int(request_id),)).fetchone()
    if not source:
        raise LookupError("Home-health request not found.")
    actor_id = _actor_id(actor)
    if actor_id not in {int(source["patient_id"]), int(source["requested_by"])} and not is_owner(actor):
        raise PermissionError("Only the patient/requester or ZENDOC owner may assign a home-health provider.")
    if str(source["status"] or "requested").lower() != "requested":
        raise ValueError("A provider can be assigned only while the home-health request is requested.")

    existing = db.execute("SELECT * FROM home_health_assignments WHERE request_id=?", (int(request_id),)).fetchone()
    if existing:
        if int(existing["provider_id"]) == int(provider_id):
            result = dict(existing)
            result["idempotent_replay"] = True
            return result
        raise ValueError("This home-health request is already assigned to another provider.")

    provider = _verified_provider(int(provider_id))
    if not provider:
        raise LookupError("Selected home-health provider is not active and verified.")
    capability = db.execute(
        """
        SELECT * FROM home_health_provider_services
        WHERE provider_id=? AND service_type=? AND active=1
        """,
        (int(provider_id), str(source["service_type"])),
    ).fetchone()
    if not capability:
        raise ValueError("Selected provider has not explicitly published this home-health service capability.")

    now = now_iso()
    cursor = db.execute(
        """
        INSERT INTO home_health_assignments
        (request_id,provider_id,provider_profile_id,assigned_by,created_at,updated_at)
        VALUES (?,?,?,?,?,?)
        """,
        (
            int(request_id), int(provider_id), int(provider["provider_profile_id"]),
            actor_id, now, now,
        ),
    )
    assignment_id = int(cursor.lastrowid)
    db.commit()
    try:
        ensure_home_health_careloop_link(request_id)
    except Exception:
        current_app.logger.exception("Home-health CareLoop link failed after assignment commit for request %s", request_id)
    result = dict(db.execute("SELECT * FROM home_health_assignments WHERE id=?", (assignment_id,)).fetchone())
    result["provider_name"] = provider["name"]
    result["service_type"] = source["service_type"]
    return result


def ensure_home_health_careloop_link(request_id: int):
    ensure_operational_fulfilment_schema()
    ensure_care_action_ledger_schema()
    db = get_db()
    row = db.execute(
        """
        SELECT h.*,a.provider_id,a.assigned_by,a.provider_profile_id,
               p.name AS provider_name,p.active AS provider_active,
               pp.verification_status
        FROM home_health_requests h
        JOIN home_health_assignments a ON a.request_id=h.id
        JOIN users p ON p.id=a.provider_id
        JOIN provider_profiles pp ON pp.id=a.provider_profile_id AND pp.user_id=p.id
        WHERE h.id=?
        """,
        (int(request_id),),
    ).fetchone()
    if not row or not bool(row["provider_active"]) or str(row["verification_status"] or "").lower() != "verified":
        return None
    service_ref = f"zendoc_home_health_request:{int(request_id)}"
    existing = _care_action_by_ref(service_ref, int(row["patient_id"]))
    if existing:
        return int(existing["id"])
    source_actor = _actor_from_user_id(int(row["assigned_by"]))
    if not source_actor:
        return None
    journey = create_persisted_journey(
        source_actor,
        patient_id=int(row["patient_id"]),
        provenance={
            "source": "zendoc_verified_home_health_assignment",
            "home_health_request_id": int(request_id),
            "provider_id": int(row["provider_id"]),
        },
    )
    title = HOME_HEALTH_SERVICE_TITLES.get(str(row["service_type"]), str(row["service_type"]).replace("_", " ").title())
    action = create_action(
        source_actor,
        int(journey["id"]),
        {
            "action_type": "home_health_service",
            "title": f"{title} with {row['provider_name']}",
            "rationale": "Patient/requester assigned a verified ZENDOC provider that explicitly published this service capability.",
            "status": "STAGED",
            "human_confirmation_required": True,
            "owner_type": "patient",
            "owner_id": int(row["patient_id"]),
            "provider_name": row["provider_name"],
            "service_ref": service_ref,
            "due_at": row["scheduled_date"],
            "evidence": {
                "source_type": "zendoc_home_health_request",
                "home_health_request_id": int(request_id),
                "provider_acknowledgement_required": True,
            },
            "provenance": {
                "source": "zendoc_verified_home_health_assignment",
                "home_health_request_id": int(request_id),
                "provider_id": int(row["provider_id"]),
                "provider_profile_id": int(row["provider_profile_id"]),
                "provider_verification_status": row["verification_status"],
            },
        },
    )
    return int(action["id"])


def _home_health_access(actor, request_id: int):
    ensure_operational_fulfilment_schema()
    row = get_db().execute(
        """
        SELECT h.*,a.id AS assignment_id,a.provider_id,a.provider_profile_id,a.assigned_by,
               p.name AS provider_name,p.active AS provider_active,
               pp.verification_status,pp.provider_type
        FROM home_health_requests h
        LEFT JOIN home_health_assignments a ON a.request_id=h.id
        LEFT JOIN users p ON p.id=a.provider_id
        LEFT JOIN provider_profiles pp ON pp.id=a.provider_profile_id
        WHERE h.id=?
        """,
        (int(request_id),),
    ).fetchone()
    if not row:
        raise LookupError("Home-health request not found.")
    actor_id = _actor_id(actor)
    provider_side = bool(row["provider_id"]) and actor_id == int(row["provider_id"])
    provider_verified = provider_side and bool(row["provider_active"]) and str(row["verification_status"] or "").lower() == "verified"
    patient_side = actor_id in {int(row["patient_id"]), int(row["requested_by"])}
    owner_admin = is_owner(actor)
    if not (provider_verified or patient_side or owner_admin):
        raise PermissionError("This home-health request belongs to another patient/provider relationship.")
    return row, provider_verified, patient_side, owner_admin


def get_home_health_fulfilment(actor, request_id: int) -> dict:
    row, provider_verified, patient_side, owner_admin = _home_health_access(actor, request_id)
    result = dict(row)
    result["provider_authorized"] = bool(provider_verified or owner_admin)
    result["patient_authorized"] = bool(patient_side)
    result["actually_integrated"] = bool(row["assignment_id"] and row["provider_id"])
    result["external_execution"] = False
    result["truth_notice"] = (
        "Status represents the assigned provider's ZENDOC home-health workflow only. "
        "It does not claim dispatch, arrival, service completion, payment, or activity inside an external agency system."
    )
    return result


def list_assigned_home_health_requests(actor) -> list[dict]:
    ensure_operational_fulfilment_schema()
    actor_id = _actor_id(actor)
    provider = _verified_provider(actor_id)
    if not provider or str(provider["role"]) not in {"doctor", "hospital"}:
        raise PermissionError("Only an active verified provider may view assigned home-health requests.")
    rows = get_db().execute(
        """
        SELECT h.id
        FROM home_health_requests h
        JOIN home_health_assignments a ON a.request_id=h.id
        WHERE a.provider_id=?
        ORDER BY h.created_at DESC
        """,
        (actor_id,),
    ).fetchall()
    return [get_home_health_fulfilment(actor, int(row["id"])) for row in rows]


def update_home_health_request_status(actor, request_id: int, target_status: str, note: str | None = None) -> dict:
    row, provider_verified, patient_side, owner_admin = _home_health_access(actor, request_id)
    if not row["assignment_id"]:
        raise ValueError("Home-health request has no assigned verified provider.")
    current = str(row["status"] or "requested").strip().lower()
    target = str(target_status or "").strip().lower()
    if target not in HOME_HEALTH_STATUS_TO_ACTION:
        raise ValueError("Unsupported home-health request status.")
    if target == current:
        return get_home_health_fulfilment(actor, request_id)
    if target not in HOME_HEALTH_TRANSITIONS.get(current, set()):
        raise ValueError(f"Invalid home-health transition: {current} -> {target}.")
    if not (provider_verified or owner_admin):
        if not (patient_side and target == "cancelled"):
            raise PermissionError("Only the assigned verified provider may advance this home-health workflow.")

    db = get_db()
    now = now_iso()
    update = db.execute(
        "UPDATE home_health_requests SET status=? WHERE id=? AND status=?",
        (target, int(request_id), current),
    )
    if update.rowcount != 1:
        raise ValueError("Home-health request changed concurrently; refresh before retrying.")
    db.execute("UPDATE home_health_assignments SET updated_at=? WHERE request_id=?", (now, int(request_id)))
    source = "PROVIDER_RECORDED" if provider_verified else "OWNER_RECORDED" if owner_admin else "USER_REPORTED"
    summary = str(note or "").strip()[:2000] or {
        "accepted": "Assigned provider accepted the home-health request in ZENDOC.",
        "in_progress": "Assigned provider marked the home-health service in progress in ZENDOC.",
        "completed": "Assigned provider marked the ZENDOC home-health request completed.",
        "cancelled": "Home-health request was cancelled in ZENDOC.",
        "declined": "Assigned provider declined the home-health request in ZENDOC.",
    }[target]
    record_care_continuity_event(
        patient_id=int(row["patient_id"]),
        event_type=f"HOME_HEALTH_{target.upper()}",
        title=f"Home Health {target.replace('_', ' ').title()}",
        summary=summary,
        source=source,
        source_ref=f"home_health:{int(request_id)}",
        actor_id=_actor_id(actor),
        metadata={
            "home_health_request_id": int(request_id),
            "provider_id": int(row["provider_id"]),
            "service_type": row["service_type"],
            "status": target,
        },
    )
    db.commit()
    try:
        sync_home_health_careloop_status(actor, request_id, target)
    except Exception:
        current_app.logger.exception("Home-health CareLoop sync failed after source commit for request %s", request_id)
    return get_home_health_fulfilment(actor, request_id)


def sync_home_health_careloop_status(actor, request_id: int, target_status: str):
    db = get_db()
    row = db.execute("SELECT * FROM home_health_requests WHERE id=?", (int(request_id),)).fetchone()
    if not row:
        raise LookupError("Home-health request not found.")
    action = _care_action_by_ref(f"zendoc_home_health_request:{int(request_id)}", int(row["patient_id"]))
    if not action:
        return None
    target = HOME_HEALTH_STATUS_TO_ACTION[str(target_status).lower()]
    current = str(action["status"])
    if current == target:
        return dict(action)
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise ValueError(f"Linked home-health action cannot transition {current} -> {target}.")
    assignment = db.execute("SELECT provider_id FROM home_health_assignments WHERE request_id=?", (int(request_id),)).fetchone()
    provenance = {
        "source": "zendoc_verified_home_health_assignment",
        "home_health_request_id": int(request_id),
        "provider_id": int(assignment["provider_id"]) if assignment else None,
        "home_health_status": str(target_status).lower(),
    }
    note = {
        "CONFIRMED": "Assigned verified ZENDOC provider accepted the home-health request.",
        "IN_PROGRESS": "Assigned verified ZENDOC provider marked the home-health service in progress.",
        "COMPLETED": "Assigned verified ZENDOC provider marked its ZENDOC home-health request completed.",
        "CANCELLED": "Linked ZENDOC home-health request was cancelled.",
        "BLOCKED": "Assigned verified ZENDOC provider declined the home-health request.",
        "STAGED": "Home-health request is awaiting provider acknowledgement.",
    }[target]
    db.execute("UPDATE care_actions SET status=?,updated_at=? WHERE id=?", (target, now_iso(), int(action["id"])))
    _append_care_event(
        int(action["id"]), current, target, "INTERNAL_HOME_HEALTH_SYNC", note,
        _actor_id(actor), provenance,
    )
    db.commit()
    return dict(db.execute("SELECT * FROM care_actions WHERE id=?", (int(action["id"]),)).fetchone())


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def _api_error(error):
    if isinstance(error, PermissionError):
        status = 403
    elif isinstance(error, LookupError):
        status = 404
    elif isinstance(error, ValueError):
        status = 409 if "transition" in str(error).lower() or "already assigned" in str(error).lower() else 400
    else:
        status = 400
    return jsonify({"error": {"code": status, "message": str(error)}}), status


@bp.get("/api/v1/connected-care/diagnostics/<int:booking_id>")
def api_diagnostic_booking_detail(booking_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        return jsonify({"booking": get_diagnostic_booking(user, booking_id)})
    except (LookupError, PermissionError, ValueError) as exc:
        return _api_error(exc)


@bp.post("/api/v1/connected-care/diagnostics/<int:booking_id>/status")
def api_diagnostic_booking_status(booking_id):
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        booking = update_diagnostic_booking_status(user, booking_id, data.get("status"), data.get("note"))
        audit("connected_care.diagnostic.status", "diagnostic_bookings", str(booking_id), actor=user)
        get_db().commit()
        return jsonify({"booking": booking})
    except (LookupError, PermissionError, ValueError) as exc:
        return _api_error(exc)


@bp.post("/api/v1/home-health/provider-services")
def api_publish_home_health_service():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        service = publish_home_health_service(user, data.get("service_type"), data.get("active", True) is not False)
        audit("publish", "home_health_provider_service", str(service["id"]), actor=user)
        get_db().commit()
        return jsonify({"provider_service": service}), 201
    except (LookupError, PermissionError, ValueError) as exc:
        return _api_error(exc)


@bp.get("/api/v1/home-health/provider-services")
def api_list_home_health_providers():
    user, error = require_api_user()
    if error:
        return error
    try:
        return jsonify({
            "providers": list_home_health_providers(request.args.get("service_type", ""), request.args.get("city")),
            "truth_notice": "Results are active verified ZENDOC providers that explicitly published this service capability.",
        })
    except ValueError as exc:
        return _api_error(exc)


@bp.post("/api/v1/home-health/requests/<int:request_id>/assign")
def api_assign_home_health_provider(request_id):
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        provider_id = int(data.get("provider_id") or 0)
        if not provider_id:
            raise ValueError("provider_id is required.")
        assignment = assign_home_health_provider(user, request_id, provider_id)
        audit("assign", "home_health_request", str(request_id), actor=user)
        get_db().commit()
        return jsonify({
            "assignment": assignment,
            "truth_notice": "Assignment is internal to ZENDOC and awaits provider acceptance; no external dispatch is claimed.",
        }), 201
    except (TypeError, LookupError, PermissionError, ValueError) as exc:
        return _api_error(exc)


@bp.get("/api/v1/home-health/provider/requests")
def api_provider_home_health_requests():
    user, error = require_api_user()
    if error:
        return error
    try:
        return jsonify({"home_health_requests": list_assigned_home_health_requests(user)})
    except (LookupError, PermissionError, ValueError) as exc:
        return _api_error(exc)


@bp.get("/api/v1/home-health/requests/<int:request_id>/fulfilment")
def api_home_health_fulfilment_detail(request_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        return jsonify({"home_health_request": get_home_health_fulfilment(user, request_id)})
    except (LookupError, PermissionError, ValueError) as exc:
        return _api_error(exc)


@bp.post("/api/v1/home-health/requests/<int:request_id>/status")
def api_home_health_status(request_id):
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        result = update_home_health_request_status(user, request_id, data.get("status"), data.get("note"))
        audit("update_status", "home_health_request", str(request_id), actor=user)
        get_db().commit()
        return jsonify({"home_health_request": result})
    except (LookupError, PermissionError, ValueError) as exc:
        return _api_error(exc)


def finish_operational_careloop_request(response):
    """Post-commit mirror for existing diagnostic booking creation endpoint."""
    if request.endpoint != "connected_care.api_book_diagnostic" or response.status_code not in {200, 201}:
        return response
    try:
        payload = response.get_json(silent=True) or {}
        booking = payload.get("booking") if isinstance(payload, dict) else None
        if isinstance(booking, dict):
            booking_id = booking.get("booking_id") or booking.get("id")
            if booking_id:
                ensure_diagnostic_careloop_link(int(booking_id))
    except Exception:
        current_app.logger.exception("Diagnostic CareLoop post-commit link failed.")
    return response
