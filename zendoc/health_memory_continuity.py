"""
ZENDOC Health Memory Continuity & Next Safe Action Engine — Milestone 10
Maintains longitudinal medical continuity with explicit provenance and generates
safe, non-clinical logistical next steps.

INVARIANTS:
1. Provenance: USER_REPORTED | DOCUMENT_EXTRACTED | PROVIDER_RECORDED | DEVICE_RECORDED
2. Casual AI chat is never stored as a verified medical fact.
3. Next Safe Actions provide proactive continuity (reminders, sharing, pharmacy search)
   without giving autonomous medical directives.
"""
from __future__ import annotations

from typing import Any

from .db import get_db, now_iso


def _user_id(actor: Any) -> int:
    if actor is None:
        return 0
    if isinstance(actor, (int, float)):
        return int(actor)
    try:
        val = actor["id"]
        if val is not None:
            return int(val)
    except Exception:
        pass
    try:
        val = getattr(actor, "id", None)
        if val is not None:
            return int(val)
    except Exception:
        pass
    return 0


def get_health_memory_provenance_summary(patient_id: int | Any, actor: Any = None) -> dict[str, Any]:
    """
    Assemble the patient's longitudinal Health Memory with explicit provenance separation.
    """
    if not isinstance(patient_id, (int, float)):
        if actor is None:
            actor = patient_id
        patient_id = _user_id(patient_id)
    if actor is None:
        actor = patient_id

    from .context_engine import verify_context_authorization
    verify_context_authorization(actor, int(patient_id), "health_memory_view")

    db = get_db()
    # Fetch timeline events
    events = db.execute(
        """
        SELECT * FROM health_timeline_events
        WHERE patient_id=?
        ORDER BY event_at DESC LIMIT 30
        """,
        (patient_id,),
    ).fetchall()

    by_provenance: dict[str, list[dict[str, Any]]] = {
        "PROVIDER_RECORDED": [],
        "DOCUMENT_EXTRACTED": [],
        "DEVICE_RECORDED": [],
        "USER_REPORTED": [],
    }

    for ev in events:
        item = dict(ev)
        src = item.get("source", "USER_REPORTED")
        by_provenance.setdefault(src, []).append(item)

    return {
        "patient_id": patient_id,
        "total_events": len(events),
        "by_provenance": by_provenance,
        "recent_events": [dict(e) for e in events[:10]],
    }


def determine_next_safe_actions(patient_id: int | Any, actor: Any = None) -> list[dict[str, Any]]:
    """
    Context-aware Next Safe Action generator:
    Inspects active care objects and returns prioritized, actionable, non-clinical next steps.
    """
    if not isinstance(patient_id, (int, float)):
        if actor is None:
            actor = patient_id
        patient_id = _user_id(patient_id)
    if actor is None:
        actor = patient_id

    from .context_engine import verify_context_authorization
    verify_context_authorization(actor, int(patient_id), "next_safe_action")

    db = get_db()
    actions: list[dict[str, Any]] = []

    # 1. Check for newly delivered orders -> Prompt dosage / refill reminder
    delivered_order = db.execute(
        """
        SELECT * FROM medicine_orders
        WHERE patient_id=? AND tracking_status='DELIVERED'
        ORDER BY updated_at DESC LIMIT 1
        """,
        (patient_id,),
    ).fetchone()
    if delivered_order:
        actions.append({
            "action_type": "SET_MEDICINE_REMINDER",
            "title": "Set Delivery & Refill Reminders",
            "description": f"Medicines for order #{delivered_order['id']} were delivered. Set reminders using the schedule you choose.",
            "button_label": "Set Reminders",
            "cta_label": "Set Reminders",
            "target_url": f"/connected-care/reminders?order_id={delivered_order['id']}",
            "cta_url": f"/connected-care/reminders?order_id={delivered_order['id']}",
            "priority": "high",
            "urgency": "high",
        })

    # 2. Check for active prescription without fulfilment order -> Prompt pharmacy fulfilment
    active_presc = db.execute(
        """
        SELECT p.* FROM prescriptions p
        LEFT JOIN medicine_orders mo ON mo.prescription_id=p.id
        WHERE p.patient_id=? AND p.status='active' AND mo.id IS NULL
        ORDER BY p.issue_date DESC LIMIT 1
        """,
        (patient_id,),
    ).fetchone()
    if active_presc:
        actions.append({
            "action_type": "FIND_PRESCRIBED_MEDICINES",
            "title": "Find Prescribed Medicines Locally",
            "description": f"Prescription from {active_presc['prescriber_name']} is ready. Compare local pharmacies for confirmed stock and split delivery options.",
            "button_label": "Find Medicines",
            "target_url": f"/connected-care/fulfilment?prescription_id={active_presc['id']}",
            "priority": "critical",
            "cta_label": "Find Medicines",
            "cta_url": f"/connected-care/fulfilment?prescription_id={active_presc['id']}",
            "urgency": "critical",
        })

    # 3. Check for ready diagnostic reports -> Prompt sharing with doctor
    diag_completed = db.execute(
        """
        SELECT db.*, dc.name test_name FROM diagnostic_bookings db
        JOIN diagnostic_catalog dc ON dc.id=db.test_id
        WHERE db.patient_id=? AND db.status='completed'
        ORDER BY db.updated_at DESC LIMIT 1
        """,
        (patient_id,),
    ).fetchone()
    if diag_completed:
        actions.append({
            "action_type": "SHARE_REPORT",
            "title": f"Share {diag_completed['test_name']} Report",
            "description": "Your test report is ready in Health Memory. Share it with your consulting physician for review.",
            "button_label": "Share Report",
            "target_url": "/records",
            "priority": "normal",
            "cta_label": "Share Report",
            "cta_url": "/records",
            "urgency": "normal",
        })

    # 4. Check for upcoming doctor appointment
    upcoming_appt = db.execute(
        """
        SELECT a.*, d.name doctor_name FROM appointments a
        JOIN users d ON d.id=a.provider_id
        WHERE a.patient_id=? AND a.status='confirmed' AND a.scheduled_for >= date('now')
        ORDER BY a.scheduled_for ASC LIMIT 1
        """,
        (patient_id,),
    ).fetchone()
    if upcoming_appt:
        actions.append({
            "action_type": "PREPARE_FOR_VISIT",
            "title": f"Upcoming Visit with {upcoming_appt['doctor_name']}",
            "description": f"Scheduled for {upcoming_appt['scheduled_for']}. Review consultation questions or upload recent vitals.",
            "button_label": "View Appointment",
            "target_url": "/appointments",
            "priority": "normal",
            "cta_label": "View Appointment",
            "cta_url": "/appointments",
            "urgency": "normal",
        })

    return actions
