"""Truthful CareLoop bridge for assigned ZENDOC pharmacy orders.

The bridge links only orders assigned to an active, verified ZENDOC pharmacy.
It records ZENDOC-internal workflow state and never claims stock, payment,
dispensing, or external courier execution.
"""
from __future__ import annotations

import json

from .care_action_ledger import ALLOWED_TRANSITIONS, create_action, ensure_care_action_ledger_schema
from .care_journey_store import create_persisted_journey
from .db import get_db, now_iso
from .security import is_owner


PHARMACY_STATUS_TO_ACTION = {
    "pending": "STAGED",
    "accepted": "CONFIRMED",
    "preparing": "IN_PROGRESS",
    "dispatched": "IN_PROGRESS",
    "completed": "COMPLETED",
    "cancelled": "CANCELLED",
}


def link_registered_pharmacy_order(actor, order_id: int):
    """Create one CareLoop action for an assigned verified ZENDOC pharmacy order."""
    ensure_care_action_ledger_schema()
    db = get_db()
    order = db.execute(
        """
        SELECT mo.id,mo.patient_id,mo.ordered_by,mo.pharmacy_id,mo.status,
               pharmacy.name AS pharmacy_name, pharmacy.active,
               pp.id AS provider_profile_id, pp.verification_status
        FROM medicine_orders mo
        JOIN users pharmacy ON pharmacy.id=mo.pharmacy_id AND pharmacy.role='pharmacy'
        LEFT JOIN provider_profiles pp ON pp.user_id=pharmacy.id
        WHERE mo.id=?
        """,
        (int(order_id),),
    ).fetchone()
    if not order or not order["pharmacy_id"]:
        return None
    if not bool(order["active"]):
        return None
    if str(order["verification_status"] or "").strip().lower() != "verified":
        return None

    actor_id = int(actor["id"])
    if actor_id not in {int(order["ordered_by"]), int(order["patient_id"])} and not is_owner(actor):
        raise PermissionError("Only the authorized patient/orderer may link this pharmacy order.")

    service_ref = f"zendoc_pharmacy_order:{int(order_id)}"
    existing = db.execute(
        "SELECT id FROM care_actions WHERE service_ref=? AND patient_id=? ORDER BY id DESC LIMIT 1",
        (service_ref, int(order["patient_id"])),
    ).fetchone()
    if existing:
        return int(existing["id"])

    journey = create_persisted_journey(
        actor,
        patient_id=int(order["patient_id"]),
        provenance={
            "source": "zendoc_registered_pharmacy_order",
            "medicine_order_id": int(order_id),
            "pharmacy_id": int(order["pharmacy_id"]),
        },
    )
    action = create_action(
        actor,
        int(journey["id"]),
        {
            "action_type": "pharmacy_fulfilment",
            "title": f"Medicine request with {order['pharmacy_name']}",
            "rationale": "Patient authorized a medicine request through an assigned ZENDOC pharmacy.",
            "status": "STAGED",
            "human_confirmation_required": True,
            "owner_type": "patient",
            "owner_id": int(order["patient_id"]),
            "provider_name": order["pharmacy_name"],
            "service_ref": service_ref,
            "evidence": {
                "source_type": "zendoc_medicine_order_record",
                "medicine_order_id": int(order_id),
            },
            "provenance": {
                "source": "zendoc_registered_pharmacy_order",
                "medicine_order_id": int(order_id),
                "pharmacy_id": int(order["pharmacy_id"]),
                "provider_profile_id": order["provider_profile_id"],
                "provider_verification_status": order["verification_status"],
            },
        },
    )
    return int(action["id"])


def sync_registered_pharmacy_order_status(actor, order_id: int, target_order_status: str):
    """Mirror an already-authorized assigned pharmacy order into its CareLoop action."""
    ensure_care_action_ledger_schema()
    db = get_db()
    order = db.execute(
        "SELECT id,patient_id,pharmacy_id,status FROM medicine_orders WHERE id=?",
        (int(order_id),),
    ).fetchone()
    if not order:
        raise LookupError("Linked medicine order not found.")
    if not order["pharmacy_id"]:
        raise PermissionError("Only an assigned ZENDOC pharmacy order can synchronize CareLoop execution.")

    actor_id = int(actor["id"])
    if actor_id != int(order["pharmacy_id"]) and not is_owner(actor):
        raise PermissionError("Only the assigned pharmacy or ZENDOC owner can synchronize this pharmacy action.")

    order_status = str(target_order_status or "").strip().lower()
    target = PHARMACY_STATUS_TO_ACTION.get(order_status)
    if not target:
        raise ValueError("Unsupported medicine order status for CareLoop synchronization.")

    service_ref = f"zendoc_pharmacy_order:{int(order_id)}"
    action = db.execute(
        "SELECT * FROM care_actions WHERE service_ref=? AND patient_id=? ORDER BY id DESC LIMIT 1",
        (service_ref, int(order["patient_id"])),
    ).fetchone()
    if not action:
        return None

    current = str(action["status"])
    if current == target:
        return dict(action)
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise ValueError(f"Linked pharmacy action cannot transition {current} -> {target}.")

    provenance = {
        "source": "zendoc_registered_pharmacy_order",
        "medicine_order_id": int(order_id),
        "pharmacy_id": int(order["pharmacy_id"]),
        "medicine_order_status": order_status,
    }
    note = {
        "CONFIRMED": "Assigned ZENDOC pharmacy accepted the medicine request.",
        "IN_PROGRESS": "Assigned ZENDOC pharmacy advanced its internal fulfilment workflow.",
        "COMPLETED": "Assigned ZENDOC pharmacy marked its ZENDOC medicine order completed.",
        "CANCELLED": "Assigned ZENDOC pharmacy order was cancelled.",
        "STAGED": "Assigned ZENDOC pharmacy request is awaiting acceptance.",
    }[target]
    now = now_iso()
    db.execute("UPDATE care_actions SET status=?,updated_at=? WHERE id=?", (target, now, int(action["id"])))
    db.execute(
        """
        INSERT INTO care_action_events
        (action_id,previous_status,status,event_type,note,actor_id,provenance_json,created_at)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            int(action["id"]), current, target, "INTERNAL_PHARMACY_ORDER_SYNC", note, actor_id,
            json.dumps(provenance, sort_keys=True, separators=(",", ":")), now,
        ),
    )
    db.commit()
    return dict(db.execute("SELECT * FROM care_actions WHERE id=?", (int(action["id"]),)).fetchone())
