"""Partner-backed non-emergency medical transport fulfilment.

The bridge turns a ZENDOC transport intake record into a scoped partner
assignment only after an owner explicitly assigns an active business client.
It intentionally refuses emergency-urgency requests: emergency dispatch needs
an authority/provider-specific integration and is never delegated to a generic
AI or partner API.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from .business_api import (
    BusinessApiRateLimitError,
    authenticate_business_api_key,
)
from .db import get_db, now_iso
from .partner_audit import record_partner_audit_event
from .routes import require_api_user
from .security import is_owner


bp = Blueprint("transport_partner", __name__)

PARTNER_STATUSES = {
    "assigned",
    "accepted",
    "en_route",
    "arrived",
    "completed",
    "declined",
    "cancelled",
}
PARTNER_TRANSITIONS = {
    "assigned": {"accepted", "declined", "cancelled"},
    "accepted": {"en_route", "cancelled"},
    "en_route": {"arrived", "cancelled"},
    "arrived": {"completed", "cancelled"},
    "completed": set(),
    "declined": set(),
    "cancelled": set(),
}


def ensure_transport_partner_schema() -> None:
    get_db().executescript(
        """
        CREATE TABLE IF NOT EXISTS transport_partner_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL UNIQUE REFERENCES ambulance_requests(id) ON DELETE CASCADE,
            client_id INTEGER NOT NULL REFERENCES business_api_clients(id) ON DELETE RESTRICT,
            status TEXT NOT NULL DEFAULT 'assigned',
            vehicle_reference TEXT,
            eta_minutes INTEGER,
            partner_note TEXT,
            assigned_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            assigned_at TEXT NOT NULL,
            accepted_at TEXT,
            completed_at TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_transport_partner_client_status
            ON transport_partner_assignments(client_id,status,updated_at);
        """
    )


def _assignment_dict(row) -> dict:
    item = dict(row)
    status = str(item.get("status") or "assigned")
    item["provider_confirmed"] = status in {"accepted", "en_route", "arrived", "completed"}
    item["dispatch_confirmed"] = status in {"en_route", "arrived", "completed"}
    item["completed"] = status == "completed"
    item["truth_notice"] = (
        "This state is recorded by the assigned authenticated transport partner. "
        "It does not independently verify clinical capability, equipment, traffic ETA, or emergency-service authority."
    )
    return item


def assign_transport_partner(actor, request_id: int, client_id: int) -> dict:
    if not is_owner(actor):
        raise PermissionError("Owner access is required to assign a transport partner.")
    ensure_transport_partner_schema()
    db = get_db()
    transport = db.execute(
        "SELECT * FROM ambulance_requests WHERE id=?",
        (int(request_id),),
    ).fetchone()
    if not transport:
        raise LookupError("Transport request not found.")
    if str(transport["urgency"] or "").lower() == "emergency":
        raise PermissionError(
            "Emergency transport cannot be assigned through the generic partner bridge. "
            "Use an authority/provider-specific emergency connector or local emergency services."
        )
    client = db.execute(
        "SELECT * FROM business_api_clients WHERE id=? AND status='active'",
        (int(client_id),),
    ).fetchone()
    if not client:
        raise LookupError("Active transport partner client not found.")
    try:
        import json
        scopes = set(json.loads(client["allowed_scopes_json"] or "[]"))
    except Exception:
        scopes = set()
    if "transport_fulfilment.write" not in scopes:
        raise PermissionError("Business client does not have transport fulfilment scope.")

    existing = db.execute(
        "SELECT id FROM transport_partner_assignments WHERE request_id=?",
        (int(request_id),),
    ).fetchone()
    if existing:
        return get_owner_transport_assignment(actor, int(existing["id"]))

    now = now_iso()
    cursor = db.execute(
        """
        INSERT INTO transport_partner_assignments
        (request_id,client_id,status,assigned_by,assigned_at,updated_at)
        VALUES (?,?,'assigned',?,?,?)
        """,
        (int(request_id), int(client_id), int(actor["id"]), now, now),
    )
    db.execute(
        "UPDATE ambulance_requests SET status='partner_assigned' WHERE id=?",
        (int(request_id),),
    )
    record_partner_audit_event(
        event_type="transport_assignment_created",
        actor_type="owner",
        actor_user_id=int(actor["id"]),
        client_id=int(client_id),
        entity_type="transport_partner_assignment",
        entity_id=int(cursor.lastrowid),
        metadata={"request_id": int(request_id), "emergency": False},
    )
    db.commit()
    return get_owner_transport_assignment(actor, int(cursor.lastrowid))


def get_owner_transport_assignment(actor, assignment_id: int) -> dict:
    if not is_owner(actor):
        raise PermissionError("Owner access is required.")
    ensure_transport_partner_schema()
    row = get_db().execute(
        """
        SELECT a.*,c.name partner_name,c.client_uid,
               r.transport_type,r.urgency,r.pickup_address,r.destination_address
        FROM transport_partner_assignments a
        JOIN business_api_clients c ON c.id=a.client_id
        JOIN ambulance_requests r ON r.id=a.request_id
        WHERE a.id=?
        """,
        (int(assignment_id),),
    ).fetchone()
    if not row:
        raise LookupError("Transport partner assignment not found.")
    return _assignment_dict(row)


def list_partner_transport_assignments(identity: dict, limit: int = 100) -> list[dict]:
    ensure_transport_partner_schema()
    limit = max(1, min(int(limit or 100), 500))
    rows = get_db().execute(
        """
        SELECT a.id,a.request_id,a.status,a.vehicle_reference,a.eta_minutes,
               a.partner_note,a.assigned_at,a.accepted_at,a.completed_at,a.updated_at,
               r.transport_type,r.pickup_address,r.destination_address,r.urgency
        FROM transport_partner_assignments a
        JOIN ambulance_requests r ON r.id=a.request_id
        WHERE a.client_id=?
        ORDER BY a.updated_at DESC,a.id DESC
        LIMIT ?
        """,
        (int(identity["client_id"]), limit),
    ).fetchall()
    result = []
    for row in rows:
        item = _assignment_dict(row)
        # The generic partner receives only the minimum routing fields needed
        # for fulfilment. No patient name, medical notes or health record data.
        item["patient_data_access"] = False
        result.append(item)
    return result


def partner_update_transport_assignment(
    identity: dict,
    assignment_id: int,
    *,
    status: str,
    vehicle_reference: str | None = None,
    eta_minutes: int | None = None,
    partner_note: str | None = None,
) -> dict:
    ensure_transport_partner_schema()
    clean = str(status or "").strip().lower()
    if clean not in PARTNER_STATUSES:
        raise ValueError("Unsupported transport partner status.")

    db = get_db()
    row = db.execute(
        """
        SELECT a.*,r.urgency
        FROM transport_partner_assignments a
        JOIN ambulance_requests r ON r.id=a.request_id
        WHERE a.id=? AND a.client_id=?
        """,
        (int(assignment_id), int(identity["client_id"])),
    ).fetchone()
    if not row:
        raise LookupError("Transport partner assignment not found.")
    if str(row["urgency"] or "").lower() == "emergency":
        raise PermissionError("Generic partner bridge cannot advance emergency dispatch.")

    current = str(row["status"] or "assigned").lower()
    if clean != current and clean not in PARTNER_TRANSITIONS.get(current, set()):
        raise ValueError(f"Invalid transport transition: {current} -> {clean}.")

    if eta_minutes not in (None, ""):
        eta_minutes = int(eta_minutes)
        if eta_minutes < 0 or eta_minutes > 1440:
            raise ValueError("eta_minutes must be between 0 and 1440.")
    else:
        eta_minutes = row["eta_minutes"]

    vehicle_reference = (
        str(vehicle_reference).strip()[:120]
        if vehicle_reference not in (None, "")
        else row["vehicle_reference"]
    )
    partner_note = (
        str(partner_note).strip()[:500]
        if partner_note not in (None, "")
        else row["partner_note"]
    )
    now = now_iso()
    accepted_at = row["accepted_at"]
    completed_at = row["completed_at"]
    if clean == "accepted" and not accepted_at:
        accepted_at = now
    if clean == "completed" and not completed_at:
        completed_at = now

    db.execute(
        """
        UPDATE transport_partner_assignments
        SET status=?,vehicle_reference=?,eta_minutes=?,partner_note=?,
            accepted_at=?,completed_at=?,updated_at=?
        WHERE id=? AND client_id=?
        """,
        (
            clean, vehicle_reference, eta_minutes, partner_note,
            accepted_at, completed_at, now,
            int(assignment_id), int(identity["client_id"]),
        ),
    )
    request_status = {
        "assigned": "partner_assigned",
        "accepted": "provider_accepted",
        "en_route": "en_route",
        "arrived": "arrived",
        "completed": "completed",
        "declined": "provider_declined",
        "cancelled": "cancelled",
    }[clean]
    db.execute(
        "UPDATE ambulance_requests SET status=? WHERE id=?",
        (request_status, int(row["request_id"])),
    )
    record_partner_audit_event(
        event_type="transport_status_updated",
        actor_type="partner",
        client_id=int(identity["client_id"]),
        key_id=int(identity["key_id"]),
        entity_type="transport_partner_assignment",
        entity_id=int(assignment_id),
        metadata={"status": clean, "request_id": int(row["request_id"])},
    )
    db.commit()

    refreshed = db.execute(
        """
        SELECT a.id,a.request_id,a.status,a.vehicle_reference,a.eta_minutes,
               a.partner_note,a.assigned_at,a.accepted_at,a.completed_at,a.updated_at,
               r.transport_type,r.pickup_address,r.destination_address,r.urgency
        FROM transport_partner_assignments a
        JOIN ambulance_requests r ON r.id=a.request_id
        WHERE a.id=? AND a.client_id=?
        """,
        (int(assignment_id), int(identity["client_id"])),
    ).fetchone()
    result = _assignment_dict(refreshed)
    result["patient_data_access"] = False
    return result


def patient_transport_partner_state(request_id: int) -> dict | None:
    ensure_transport_partner_schema()
    row = get_db().execute(
        """
        SELECT a.id,a.status,a.vehicle_reference,a.eta_minutes,a.updated_at,
               c.name partner_name
        FROM transport_partner_assignments a
        JOIN business_api_clients c ON c.id=a.client_id
        WHERE a.request_id=?
        """,
        (int(request_id),),
    ).fetchone()
    return _assignment_dict(row) if row else None


@bp.post("/api/v1/admin/transport/requests/<int:request_id>/assign-partner")
def api_assign_transport_partner(request_id):
    actor, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        assignment = assign_transport_partner(
            actor,
            request_id,
            int(data.get("client_id")),
        )
        return jsonify({"assignment": assignment}), 201
    except LookupError as exc:
        return jsonify({"error": {"code": 404, "message": str(exc)}}), 404
    except PermissionError as exc:
        return jsonify({"error": {"code": 403, "message": str(exc)}}), 403
    except (TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400


@bp.get("/api/v1/business/transport/assignments")
def api_partner_transport_assignments():
    raw_key = request.headers.get("X-ZENDOC-Partner-Key", "")
    try:
        identity = authenticate_business_api_key(
            raw_key,
            required_scope="transport_fulfilment.write",
            endpoint="/api/v1/business/transport/assignments",
            method="GET",
        )
        return jsonify({
            "assignments": list_partner_transport_assignments(
                identity, request.args.get("limit", 100)
            )
        })
    except BusinessApiRateLimitError as exc:
        return jsonify({"error": {"code": 429, "message": str(exc)}}), 429
    except PermissionError as exc:
        return jsonify({"error": {"code": 401, "message": str(exc)}}), 401
    except (TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400


@bp.post("/api/v1/business/transport/assignments/<int:assignment_id>/status")
def api_partner_transport_status(assignment_id):
    raw_key = request.headers.get("X-ZENDOC-Partner-Key", "")
    try:
        identity = authenticate_business_api_key(
            raw_key,
            required_scope="transport_fulfilment.write",
            endpoint=f"/api/v1/business/transport/assignments/{assignment_id}/status",
            method="POST",
        )
        data = request.get_json(silent=True) or {}
        assignment = partner_update_transport_assignment(
            identity,
            assignment_id,
            status=data.get("status"),
            vehicle_reference=data.get("vehicle_reference"),
            eta_minutes=data.get("eta_minutes"),
            partner_note=data.get("partner_note"),
        )
        return jsonify({"assignment": assignment})
    except BusinessApiRateLimitError as exc:
        return jsonify({"error": {"code": 429, "message": str(exc)}}), 429
    except LookupError as exc:
        return jsonify({"error": {"code": 404, "message": str(exc)}}), 404
    except PermissionError as exc:
        return jsonify({"error": {"code": 403, "message": str(exc)}}), 403
    except (TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
