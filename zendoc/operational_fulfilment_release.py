"""Release hardening for diagnostic/lab and home-health fulfilment.

Adds provider work queues, truthful diagnostic report linking, patient-visible
operational queues, and provider capability introspection without claiming any
external LIS, dispatch, payment, courier, or agency execution.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from .care_graph import record_care_continuity_event
from .db import get_db, now_iso
from .operational_fulfilment import (
    DIAGNOSTIC_STATUS_TO_ACTION,
    HOME_HEALTH_STATUS_TO_ACTION,
    HOME_HEALTH_SERVICE_IDS,
    _actor_id,
    _diagnostic_access,
    _verified_provider,
    get_diagnostic_booking,
    get_home_health_fulfilment,
)
from .routes import audit, require_api_user
from .security import is_owner


bp = Blueprint("operational_fulfilment_release", __name__)

_DIAGNOSTIC_PROVIDER_TYPES = {"diagnostic_centre", "diagnostic_center", "lab", "hospital"}


def _normalize_status(value, allowed):
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text not in allowed:
        raise ValueError("Unsupported status filter.")
    return text


def list_diagnostic_provider_requests(actor, status: str | None = None) -> list[dict]:
    """Return only bookings assigned to this active verified diagnostic provider."""
    actor_id = _actor_id(actor)
    provider = _verified_provider(actor_id)
    if not provider or str(provider["provider_type"] or "").lower() not in _DIAGNOSTIC_PROVIDER_TYPES:
        raise PermissionError("Only an active verified diagnostic provider may view its assigned diagnostic requests.")
    status = _normalize_status(status, DIAGNOSTIC_STATUS_TO_ACTION)
    params = [actor_id]
    where = "b.lab_id=?"
    if status:
        where += " AND LOWER(b.status)=?"
        params.append(status)
    rows = get_db().execute(
        f"""
        SELECT b.id
        FROM diagnostic_bookings b
        WHERE {where}
        ORDER BY b.created_at DESC,b.id DESC
        """,
        params,
    ).fetchall()
    return [get_diagnostic_booking(actor, int(row["id"])) for row in rows]


def list_patient_diagnostic_requests(actor, status: str | None = None) -> list[dict]:
    actor_id = _actor_id(actor)
    if not actor_id:
        raise PermissionError("Authentication required.")
    status = _normalize_status(status, DIAGNOSTIC_STATUS_TO_ACTION)
    params = [actor_id, actor_id]
    where = "(b.patient_id=? OR b.booked_by=?)"
    if status:
        where += " AND LOWER(b.status)=?"
        params.append(status)
    rows = get_db().execute(
        f"SELECT b.id FROM diagnostic_bookings b WHERE {where} ORDER BY b.created_at DESC,b.id DESC",
        params,
    ).fetchall()
    return [get_diagnostic_booking(actor, int(row["id"])) for row in rows]


def link_diagnostic_report(actor, booking_id: int, record_id: int) -> dict:
    """Link a real patient-owned medical record to a completed diagnostic booking.

    A verified assigned lab may link only a record it uploaded itself. ZENDOC
    owner access is retained for recovery. No extraction result or clinical
    interpretation is generated here.
    """
    row, lab_verified, owner_admin, _patient_side = _diagnostic_access(actor, int(booking_id))
    if not (lab_verified or owner_admin):
        raise PermissionError("Only the assigned verified lab or ZENDOC owner may link a provider diagnostic report.")
    if str(row["status"] or "").lower() != "completed":
        raise ValueError("A diagnostic report can be linked only after the booking is completed.")

    db = get_db()
    record = db.execute(
        "SELECT id,owner_id,uploaded_by,title,category,created_at FROM medical_records WHERE id=?",
        (int(record_id),),
    ).fetchone()
    if not record:
        raise LookupError("Medical record not found.")
    if int(record["owner_id"]) != int(row["patient_id"]):
        raise PermissionError("The report record belongs to a different patient.")
    if lab_verified and int(record["uploaded_by"]) != int(row["lab_id"]):
        raise PermissionError("The assigned lab may link only a report record it uploaded for this patient.")

    existing = row["report_record_id"]
    if existing and int(existing) != int(record_id):
        raise ValueError("This diagnostic booking already has a different linked report record.")
    if existing and int(existing) == int(record_id):
        result = get_diagnostic_booking(actor, int(booking_id))
        result["report_link_idempotent_replay"] = True
        return result

    db.execute(
        "UPDATE diagnostic_bookings SET report_record_id=?,updated_at=? WHERE id=? AND status='completed'",
        (int(record_id), now_iso(), int(booking_id)),
    )
    source = "PROVIDER_RECORDED" if lab_verified else "OWNER_RECORDED"
    record_care_continuity_event(
        patient_id=int(row["patient_id"]),
        event_type="DIAGNOSTIC_REPORT_LINKED",
        title="Diagnostic Report Linked",
        summary="A real patient-owned medical record was linked to the completed diagnostic booking; no clinical interpretation was generated.",
        source=source,
        source_ref=f"diagnostic:{int(booking_id)}",
        actor_id=_actor_id(actor),
        metadata={
            "booking_id": int(booking_id),
            "report_record_id": int(record_id),
            "lab_id": int(row["lab_id"]),
            "source": source,
        },
    )
    db.commit()
    result = get_diagnostic_booking(actor, int(booking_id))
    result["report_record"] = dict(record)
    result["report_truth_notice"] = (
        "The linked record is evidence stored in ZENDOC. Linking it does not verify an external LIS, payment, sample chain-of-custody, or clinical interpretation."
    )
    return result


def list_my_home_health_capabilities(actor) -> list[dict]:
    actor_id = _actor_id(actor)
    provider = _verified_provider(actor_id)
    if not provider or str(provider["role"] or "") not in {"doctor", "hospital"}:
        raise PermissionError("Only an active verified doctor/hospital provider may view home-health capabilities.")
    rows = get_db().execute(
        """
        SELECT id,provider_id,service_type,active,observed_at,created_at,updated_at
        FROM home_health_provider_services
        WHERE provider_id=?
        ORDER BY service_type,id
        """,
        (actor_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def list_patient_home_health_requests(actor, status: str | None = None) -> list[dict]:
    actor_id = _actor_id(actor)
    if not actor_id:
        raise PermissionError("Authentication required.")
    status = _normalize_status(status, HOME_HEALTH_STATUS_TO_ACTION)
    params = [actor_id, actor_id]
    where = "(h.patient_id=? OR h.requested_by=?)"
    if status:
        where += " AND LOWER(h.status)=?"
        params.append(status)
    rows = get_db().execute(
        f"SELECT h.id FROM home_health_requests h WHERE {where} ORDER BY h.created_at DESC,h.id DESC",
        params,
    ).fetchall()
    return [get_home_health_fulfilment(actor, int(row["id"])) for row in rows]


def release_readiness(actor) -> dict:
    """Small owner-only operational snapshot for release verification."""
    if not is_owner(actor):
        raise PermissionError("Only the ZENDOC owner may view fulfilment release readiness.")
    db = get_db()
    diagnostic_counts = {
        row["status"]: int(row["count"])
        for row in db.execute("SELECT status,COUNT(*) AS count FROM diagnostic_bookings GROUP BY status").fetchall()
    }
    home_counts = {
        row["status"]: int(row["count"])
        for row in db.execute("SELECT status,COUNT(*) AS count FROM home_health_requests GROUP BY status").fetchall()
    }
    return {
        "diagnostics": diagnostic_counts,
        "home_health": home_counts,
        "external_execution": False,
        "truth_notice": (
            "Release readiness covers ZENDOC-internal verified-provider workflow only. External LIS, dispatch, courier, payment and agency integrations remain false until real connectors are configured."
        ),
    }


def _api_error(error):
    if isinstance(error, PermissionError):
        status = 403
    elif isinstance(error, LookupError):
        status = 404
    elif isinstance(error, ValueError):
        status = 409 if "already" in str(error).lower() else 400
    else:
        status = 400
    return jsonify({"error": {"code": status, "message": str(error)}}), status


@bp.get("/api/v1/connected-care/diagnostics/provider/requests")
def api_diagnostic_provider_requests():
    user, error = require_api_user()
    if error:
        return error
    try:
        return jsonify({
            "bookings": list_diagnostic_provider_requests(user, request.args.get("status")),
            "external_execution": False,
        })
    except (LookupError, PermissionError, ValueError) as exc:
        return _api_error(exc)


@bp.get("/api/v1/connected-care/diagnostics/patient/requests")
def api_diagnostic_patient_requests():
    user, error = require_api_user()
    if error:
        return error
    try:
        return jsonify({"bookings": list_patient_diagnostic_requests(user, request.args.get("status"))})
    except (LookupError, PermissionError, ValueError) as exc:
        return _api_error(exc)


@bp.post("/api/v1/connected-care/diagnostics/<int:booking_id>/report-link")
def api_link_diagnostic_report(booking_id):
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        record_id = int(data.get("record_id") or 0)
        if not record_id:
            raise ValueError("record_id is required.")
        booking = link_diagnostic_report(user, booking_id, record_id)
        audit("connected_care.diagnostic.report_link", "diagnostic_bookings", str(booking_id), actor=user)
        get_db().commit()
        return jsonify({"booking": booking})
    except (TypeError, LookupError, PermissionError, ValueError) as exc:
        return _api_error(exc)


@bp.get("/api/v1/home-health/provider/capabilities")
def api_my_home_health_capabilities():
    user, error = require_api_user()
    if error:
        return error
    try:
        return jsonify({
            "capabilities": list_my_home_health_capabilities(user),
            "supported_service_ids": sorted(HOME_HEALTH_SERVICE_IDS),
        })
    except (LookupError, PermissionError, ValueError) as exc:
        return _api_error(exc)


@bp.get("/api/v1/home-health/patient/requests")
def api_patient_home_health_requests():
    user, error = require_api_user()
    if error:
        return error
    try:
        return jsonify({"home_health_requests": list_patient_home_health_requests(user, request.args.get("status"))})
    except (LookupError, PermissionError, ValueError) as exc:
        return _api_error(exc)


@bp.get("/api/v1/operations/fulfilment-release-readiness")
def api_fulfilment_release_readiness():
    user, error = require_api_user()
    if error:
        return error
    try:
        return jsonify(release_readiness(user))
    except (LookupError, PermissionError, ValueError) as exc:
        return _api_error(exc)
