"""Provider-scoped operational activity timeline for the ZENDOC web app.

Every event comes from a record already visible to the authenticated provider.
The timeline is informational: it never claims external LIS, courier, payment,
dispatch, arrival, or agency execution.
"""
from __future__ import annotations

from flask import Blueprint, abort, g, render_template, request

from .db import get_db
from .operational_fulfilment import list_assigned_home_health_requests
from .operational_fulfilment_release import list_diagnostic_provider_requests
from .pharmacy_service import list_medicine_orders
from .security import login_required


bp = Blueprint("activity_center", __name__)
_PROVIDER_ROLES = {"doctor", "hospital", "pharmacy"}
_ALLOWED_KINDS = {"all", "appointment", "diagnostic", "home_health", "pharmacy", "notification"}


def _event(kind, event_at, title, summary, status=None, patient_name=None, details_url=None, item_id=None):
    return {
        "kind": kind,
        "event_at": str(event_at or ""),
        "title": str(title or "Activity"),
        "summary": str(summary or ""),
        "status": str(status or "").lower() or None,
        "patient_name": patient_name,
        "details_url": details_url,
        "item_id": item_id,
        "external_execution": False,
    }


def _patient_name(patient_id):
    if not patient_id:
        return None
    row = get_db().execute("SELECT name FROM users WHERE id=?", (int(patient_id),)).fetchone()
    return row["name"] if row else None


def list_provider_activity(actor, kind: str = "all", limit: int = 120) -> list[dict]:
    role = str(actor.get("role") or "").lower()
    provider_id = int(actor.get("id") or 0)
    if role not in _PROVIDER_ROLES or not provider_id:
        raise PermissionError("Only an authenticated doctor, hospital, or pharmacy provider may view this activity timeline.")

    kind = str(kind or "all").strip().lower()
    if kind not in _ALLOWED_KINDS:
        raise ValueError("Unsupported activity filter.")

    db = get_db()
    events: list[dict] = []

    for row in db.execute(
        "SELECT id,title,message,is_read,created_at FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 80",
        (provider_id,),
    ).fetchall():
        events.append(
            _event(
                "notification",
                row["created_at"],
                row["title"],
                row["message"],
                "read" if bool(row["is_read"]) else "unread",
                details_url="/notifications",
                item_id=int(row["id"]),
            )
        )

    if role in {"doctor", "hospital"}:
        for row in db.execute(
            """
            SELECT a.id,a.status,a.scheduled_for,a.created_at,u.name AS patient_name
            FROM appointments a
            JOIN users u ON u.id=a.patient_id
            WHERE a.provider_id=?
            ORDER BY a.scheduled_for DESC,a.id DESC
            LIMIT 120
            """,
            (provider_id,),
        ).fetchall():
            events.append(
                _event(
                    "appointment",
                    row["scheduled_for"] or row["created_at"],
                    f"Appointment with {row['patient_name']}",
                    "Assigned ZENDOC appointment in your provider workspace.",
                    row["status"],
                    row["patient_name"],
                    "/appointments",
                    int(row["id"]),
                )
            )

        try:
            diagnostic_rows = list_diagnostic_provider_requests(actor)
        except PermissionError:
            diagnostic_rows = []
        for item in diagnostic_rows:
            patient_name = _patient_name(item.get("patient_id"))
            events.append(
                _event(
                    "diagnostic",
                    item.get("updated_at") or item.get("created_at"),
                    f"{item.get('test_name') or 'Diagnostic request'}{f' · {patient_name}' if patient_name else ''}",
                    "Verified provider workflow recorded inside ZENDOC. External LIS, payment, sample chain and interpretation are not implied.",
                    item.get("status"),
                    patient_name,
                    "/operations/fulfilment",
                    item.get("id"),
                )
            )

        try:
            home_rows = list_assigned_home_health_requests(actor)
        except PermissionError:
            home_rows = []
        for item in home_rows:
            patient_name = _patient_name(item.get("patient_id"))
            service = str(item.get("service_type") or "Home health").replace("_", " ").title()
            events.append(
                _event(
                    "home_health",
                    item.get("updated_at") or item.get("created_at") or item.get("scheduled_date"),
                    f"{service}{f' · {patient_name}' if patient_name else ''}",
                    "Assigned verified-provider workflow inside ZENDOC. External dispatch, arrival, payment and agency execution are not implied.",
                    item.get("status"),
                    patient_name,
                    "/operations/fulfilment",
                    item.get("id"),
                )
            )

    if role == "pharmacy":
        for item in list_medicine_orders(actor):
            if int(item.get("pharmacy_id") or 0) != provider_id:
                continue
            events.append(
                _event(
                    "pharmacy",
                    item.get("created_at"),
                    f"Medicine order · {item.get('patient_name') or 'patient'}",
                    "Assigned ZENDOC pharmacy order. Stock, payment, dispensing and courier execution are not implied.",
                    item.get("status"),
                    item.get("patient_name"),
                    "/pharmacy",
                    item.get("id"),
                )
            )

    if kind != "all":
        events = [item for item in events if item["kind"] == kind]
    events.sort(key=lambda item: (item.get("event_at") or "", int(item.get("item_id") or 0)), reverse=True)
    return events[: max(1, min(int(limit or 120), 250))]


def provider_activity_summary(events: list[dict]) -> dict:
    active_statuses = {"requested", "pending", "accepted", "confirmed", "preparing", "processing", "sample_collected", "in_progress", "unread"}
    return {
        "total": len(events),
        "active": sum(1 for item in events if str(item.get("status") or "").lower() in active_statuses),
        "completed": sum(1 for item in events if str(item.get("status") or "").lower() == "completed"),
        "notifications": sum(1 for item in events if item.get("kind") == "notification"),
    }


@bp.get("/provider/activity")
@login_required
def provider_activity_page():
    actor = dict(g.user)
    if str(actor.get("role") or "").lower() not in _PROVIDER_ROLES:
        abort(403)
    kind = request.args.get("type", "all")
    try:
        all_events = list_provider_activity(actor, "all")
        events = all_events if kind == "all" else list_provider_activity(actor, kind)
    except ValueError:
        abort(400)
    return render_template(
        "provider_activity.html",
        events=events,
        summary=provider_activity_summary(all_events),
        selected_type=kind,
        activity_types=("all", "appointment", "diagnostic", "home_health", "pharmacy", "notification"),
    )
