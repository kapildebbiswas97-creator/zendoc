"""Provider-scoped operational activity timeline for the ZENDOC web app.

This view intentionally reads only records already assigned to the authenticated
provider. It does not expose unrelated patient data and it never claims external
execution for lab, pharmacy, or home-health work.
"""
from __future__ import annotations

from flask import Blueprint, abort, g, render_template, request

from .db import get_db
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

    notification_rows = db.execute(
        "SELECT id,title,message,is_read,created_at FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 80",
        (provider_id,),
    ).fetchall()
    for row in notification_rows:
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
        appointment_rows = db.execute(
            """
            SELECT a.id,a.status,a.scheduled_for,a.created_at,u.name AS patient_name
            FROM appointments a
            JOIN users u ON u.id=a.patient_id
            WHERE a.provider_id=?
            ORDER BY a.scheduled_for DESC,a.id DESC
            LIMIT 120
            """,
            (provider_id,),
        ).fetchall()
        for row in appointment_rows:
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

        diagnostic_rows = db.execute(
            """
            SELECT b.id,b.status,b.scheduled_date,b.created_at,u.name AS patient_name,dc.name AS test_name
            FROM diagnostic_bookings b
            JOIN users u ON u.id=b.patient_id
            JOIN diagnostic_catalog dc ON dc.id=b.test_id
            WHERE b.lab_id=?
            ORDER BY b.created_at DESC,b.id DESC
            LIMIT 120
            """,
            (provider_id,),
        ).fetchall()
        for row in diagnostic_rows:
            events.append(
                _event(
                    "diagnostic",
                    row["created_at"],
                    f"{row['test_name']} · {row['patient_name']}",
                    f"Scheduled {row['scheduled_date'] or 'date not set'} in ZENDOC.",
                    row["status"],
                    row["patient_name"],
                    "/operations/fulfilment",
                    int(row["id"]),
                )
            )

        home_rows = db.execute(
            """
            SELECT h.id,h.status,h.service_type,h.scheduled_date,h.created_at,u.name AS patient_name
            FROM home_health_requests h
            JOIN home_health_assignments a ON a.request_id=h.id
            JOIN users u ON u.id=h.patient_id
            WHERE a.provider_id=?
            ORDER BY h.created_at DESC,h.id DESC
            LIMIT 120
            """,
            (provider_id,),
        ).fetchall()
        for row in home_rows:
            title = str(row["service_type"] or "home health").replace("_", " ").title()
            events.append(
                _event(
                    "home_health",
                    row["created_at"],
                    f"{title} · {row['patient_name']}",
                    f"Assigned home-health request for {row['scheduled_date'] or 'date not set'}.",
                    row["status"],
                    row["patient_name"],
                    "/operations/fulfilment",
                    int(row["id"]),
                )
            )

    if role == "pharmacy":
        order_rows = db.execute(
            """
            SELECT mo.id,mo.status,mo.created_at,u.name AS patient_name
            FROM medicine_orders mo
            JOIN users u ON u.id=mo.patient_id
            WHERE mo.pharmacy_id=?
            ORDER BY mo.created_at DESC,mo.id DESC
            LIMIT 120
            """,
            (provider_id,),
        ).fetchall()
        for row in order_rows:
            events.append(
                _event(
                    "pharmacy",
                    row["created_at"],
                    f"Medicine order · {row['patient_name']}",
                    "Assigned ZENDOC pharmacy order. Stock, payment, dispensing and courier execution are not implied by this timeline.",
                    row["status"],
                    row["patient_name"],
                    "/pharmacy",
                    int(row["id"]),
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
