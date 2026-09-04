"""
ZENDOC Care Graph Domain Model — Milestone 10
Relational continuity and provenance engine connecting:
PATIENT ↔ DOCTOR ↔ APPOINTMENT ↔ PRESCRIPTION ↔ MEDICINE ↔ PHARMACY ↔ ORDER ↔ DIAGNOSTIC ↔ REPORT ↔ FOLLOW-UP

Maintains complete provenance without requiring an external graph database.
"""
from __future__ import annotations

import json
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


def record_care_continuity_event(
    patient_id: int,
    event_type: str,
    title: str,
    summary: str,
    source: str,
    source_ref: str | None = None,
    actor_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Append an authorized, provenance-tagged continuity event to the patient's Health Memory.
    Casual AI chat is NEVER recorded as clinical fact; only verified logistical, provider, or device events.
    """
    db = get_db()
    now = now_iso()
    cursor = db.execute(
        """
        INSERT INTO health_timeline_events
        (patient_id, event_type, event_at, title, summary, provider_name, source, source_ref, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            patient_id,
            event_type,
            now,
            title,
            summary,
            (metadata or {}).get("provider_name"),
            source,
            source_ref,
            actor_id,
            now,
        ),
    )
    event_id = cursor.lastrowid

    # Emit platform event for audit
    db.execute(
        """
        INSERT INTO platform_events
        (actor_id, agent_name, action, entity_type, entity_id, status, event_type, payload_json, created_at)
        VALUES (?, 'CareGraph', 'record_continuity_event', 'health_timeline_events', ?, 'info', ?, ?, ?)
        """,
        (
            actor_id,
            str(event_id),
            event_type,
            json.dumps(metadata or {}),
            now,
        ),
    )
    db.commit()

    row = db.execute("SELECT * FROM health_timeline_events WHERE id=?", (event_id,)).fetchone()
    return dict(row)


def get_patient_care_graph(patient_id: int, actor: Any = None) -> dict[str, Any]:
    """
    Assemble the full domain Care Graph for a patient:
    Aggregates appointments, prescriptions, orders, diagnostics, timeline events, and the relational edges between them.
    """
    if actor is not None:
        from .context_engine import verify_context_authorization
        verify_context_authorization(actor, patient_id, "care_graph_view")

    db = get_db()
    patient_row = db.execute("SELECT id, name, city, email FROM users WHERE id=?", (patient_id,)).fetchone()
    if not patient_row:
        raise LookupError(f"Patient #{patient_id} not found.")

    # 1. Appointments
    appts = db.execute(
        """
        SELECT a.*, d.name doctor_name, dp.specialty
        FROM appointments a
        LEFT JOIN users d ON d.id=a.provider_id
        LEFT JOIN provider_profiles dp ON dp.user_id=a.provider_id
        WHERE a.patient_id=?
        ORDER BY a.scheduled_for DESC
        """,
        (patient_id,),
    ).fetchall()

    # 2. Prescriptions & items
    prescs = db.execute(
        """
        SELECT p.*
        FROM prescriptions p
        WHERE p.patient_id=?
        ORDER BY p.issue_date DESC
        """,
        (patient_id,),
    ).fetchall()
    prescriptions_list = []
    prescription_ids = []
    for p in prescs:
        p_dict = dict(p)
        prescription_ids.append(p_dict["id"])
        items = db.execute(
            "SELECT * FROM prescription_items WHERE prescription_id=?",
            (p_dict["id"],),
        ).fetchall()
        p_dict["items"] = [dict(i) for i in items]
        prescriptions_list.append(p_dict)

    # 3. Medicine / Pharmacy Orders
    orders = db.execute(
        """
        SELECT mo.*, pharm.name pharmacy_name, fp.strategy_name
        FROM medicine_orders mo
        LEFT JOIN users pharm ON pharm.id=mo.pharmacy_id
        LEFT JOIN fulfilment_plans fp ON fp.id=mo.plan_id
        WHERE mo.patient_id=?
        ORDER BY mo.created_at DESC
        """,
        (patient_id,),
    ).fetchall()
    orders_list = []
    for o in orders:
        o_dict = dict(o)
        try:
            o_dict["items"] = json.loads(o_dict.get("items_json") or "[]")
        except Exception:
            o_dict["items"] = []
        events = db.execute(
            "SELECT * FROM order_events WHERE order_id=? ORDER BY id ASC",
            (o_dict["id"],),
        ).fetchall()
        o_dict["events"] = [dict(e) for e in events]
        orders_list.append(o_dict)

    # 4. Diagnostics & Lab Bookings
    diag_bookings = db.execute(
        """
        SELECT db.*, dc.name test_name, dc.category test_category, lab.name lab_name
        FROM diagnostic_bookings db
        JOIN diagnostic_catalog dc ON dc.id=db.test_id
        LEFT JOIN users lab ON lab.id=db.lab_id
        WHERE db.patient_id=?
        ORDER BY db.scheduled_date DESC
        """,
        (patient_id,),
    ).fetchall()

    # 5. Timeline Events
    timeline = db.execute(
        """
        SELECT * FROM health_timeline_events
        WHERE patient_id=?
        ORDER BY event_at DESC LIMIT 50
        """,
        (patient_id,),
    ).fetchall()

    # 6. Reminders / Follow-ups
    reminders = db.execute(
        "SELECT * FROM medicine_reminders WHERE user_id=? AND active=1 ORDER BY reminder_time ASC",
        (patient_id,),
    ).fetchall()

    # Synthesize Edges (Provenance & Continuity relations)
    edges = []
    # Appointment -> Prescription
    for p in prescriptions_list:
        if p.get("prescriber_id"):
            edges.append({
                "from": f"doctor:{p['prescriber_id']}",
                "to": f"prescription:{p['id']}",
                "relation": "PRESCRIBED_BY",
                "label": f"Prescribed by {p.get('prescriber_name')}",
            })

    # Prescription -> Order
    for o in orders_list:
        if o.get("prescription_id"):
            edges.append({
                "from": f"prescription:{o['prescription_id']}",
                "to": f"order:{o['id']}",
                "relation": "FULFILLED_BY_ORDER",
                "label": f"Order #{o['id']} fulfils prescription #{o['prescription_id']}",
            })
        if o.get("pharmacy_id"):
            edges.append({
                "from": f"order:{o['id']}",
                "to": f"pharmacy:{o['pharmacy_id']}",
                "relation": "ASSIGNED_TO_PHARMACY",
                "label": f"Fulfilled by {o.get('pharmacy_name') or 'Pharmacy'}",
            })

    # Diagnostic Booking -> Report Record
    for db_item in diag_bookings:
        if db_item.get("report_record_id"):
            edges.append({
                "from": f"diagnostic_booking:{db_item['id']}",
                "to": f"medical_record:{db_item['report_record_id']}",
                "relation": "GENERATED_REPORT",
                "label": f"Report for {db_item['test_name']}",
            })

    # Order -> Reminder
    for r in reminders:
        edges.append({
            "from": "health_memory",
            "to": f"reminder:{r['id']}",
            "relation": "FOLLOW_UP_REMINDER",
            "label": f"Refill reminder: {r['medicine_name']}",
        })

    return {
        "patient": dict(patient_row),
        "nodes": {
            "appointments": [dict(a) for a in appts],
            "prescriptions": prescriptions_list,
            "orders": orders_list,
            "diagnostics": [dict(d) for d in diag_bookings],
            "timeline": [dict(t) for t in timeline],
            "reminders": [dict(r) for r in reminders],
        },
        "events": [dict(t) for t in timeline],
        "edges": edges,
        "summary": {
            "active_prescriptions_count": len(prescriptions_list),
            "pending_orders_count": sum(1 for o in orders_list if o.get("tracking_status") not in {"DELIVERED", "CANCELLED"}),
            "scheduled_appointments_count": len(appts),
            "diagnostics_count": len(diag_bookings),
        },
    }