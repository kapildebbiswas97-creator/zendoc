"""
ZENDOC Order & Fulfilment Lifecycle — Milestone 10.

This module owns the consequential pharmacy-order boundary. A fulfilment plan
is only a quote until a caller supplies explicit confirmation, the plan hash,
and a concrete delivery address. At submission time the service revalidates
every inventory observation and provider quote; a stale, missing, unknown, or
changed value can never silently become an order.

ORDER LIFECYCLE:
SUBMITTED → ACCEPTED → PREPARING → READY_FOR_PICKUP → OUT_FOR_DELIVERY → DELIVERED
                         ↘ REJECTED / CANCELLED
"""
from __future__ import annotations

import json
import math
import re
from typing import Any

from .db import get_db, now_iso


ALLOWED_TRACKING_STATUSES = {
    "DRAFT",
    "AWAITING_CONFIRMATION",
    "SUBMITTED",
    "ACCEPTED",
    "REJECTED",
    "PREPARING",
    "PACKED",
    "READY_FOR_PICKUP",
    "OUT_FOR_DELIVERY",
    "DISPATCHED",
    "DELIVERED",
    "CANCELLED",
}

# Tracking is a state machine, rather than a free-form status field. The
# acknowledgement endpoint is the normal SUBMITTED -> ACCEPTED/REJECTED
# transition; keeping those transitions here also makes direct service calls
# safe when a provider integration uses the tracking endpoint.
TRACKING_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"SUBMITTED", "CANCELLED"},
    "AWAITING_CONFIRMATION": {"SUBMITTED", "CANCELLED"},
    "SUBMITTED": {"ACCEPTED", "REJECTED", "CANCELLED"},
    "ACCEPTED": {"PREPARING", "CANCELLED"},
    "PREPARING": {"READY_FOR_PICKUP", "OUT_FOR_DELIVERY", "CANCELLED"},
    "READY_FOR_PICKUP": {"OUT_FOR_DELIVERY", "DELIVERED", "CANCELLED"},
    "OUT_FOR_DELIVERY": {"DELIVERED", "CANCELLED"},
    "REJECTED": set(),
    "DELIVERED": set(),
    "CANCELLED": set(),
}

_IDEMPOTENCY_KEY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}\Z")


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


def _active_actor(db, actor: Any):
    """Resolve the actor from the database; never trust a client role claim."""
    aid = _user_id(actor)
    if not aid:
        raise PermissionError("Authentication is required for order actions.")
    row = db.execute("SELECT * FROM users WHERE id=? AND active=1", (aid,)).fetchone()
    if not row:
        raise PermissionError("The authenticated account is no longer active.")
    return row


def _is_owner(actor_row: Any) -> bool:
    from .security import is_owner

    return bool(is_owner(actor_row))


def _data_mode(explicit: str | None = None) -> str:
    """Resolve the configured LIVE/DEMO boundary without implicit mixing."""
    from .inventory_service import _data_mode as resolve_data_mode

    return resolve_data_mode(explicit)


def _normalise_idempotency_key(value: Any) -> str | None:
    if value is None:
        return None
    key = str(value).strip()
    if not key:
        return None
    if not _IDEMPOTENCY_KEY_RE.fullmatch(key):
        raise ValueError(
            "idempotency_key must contain only letters, numbers, '.', '_', ':', or '-'."
        )
    return key


def _order_result(order_ids: list[int], db, *, replay: bool = False) -> dict[str, Any]:
    """Return the stable submission shape for both a fresh request and replay."""
    if not order_ids:
        raise LookupError("No order was created for this fulfilment plan.")
    primary_id = int(order_ids[0])
    details = get_order_details(primary_id, actor=None, _internal=True)
    tracking = str(details.get("tracking_status") or "SUBMITTED").upper()
    return {
        "success": True,
        "order_id": primary_id,
        "primary_order_id": primary_id,
        "all_order_ids": [int(order_id) for order_id in order_ids],
        "deliveries_count": len(order_ids),
        "status": tracking,
        "message": "Order submitted and awaiting provider acknowledgement."
        if tracking == "SUBMITTED"
        else f"Order is currently {tracking.lower()}.",
        "idempotent_replay": bool(replay),
    }


def _existing_orders_for_submission(
    db,
    *,
    patient_id: int,
    plan_id: int,
    actor_id: int,
    idempotency_key: str | None,
) -> list[int]:
    """Find a prior logical submission without leaking another patient's order."""
    rows = []
    if idempotency_key:
        rows = db.execute(
            """
            SELECT id, patient_id, plan_id, ordered_by
            FROM medicine_orders
            WHERE patient_id=? AND (idempotency_key=? OR idempotency_key LIKE ?)
            ORDER BY id ASC
            """,
            (patient_id, idempotency_key, f"{idempotency_key}:%"),
        ).fetchall()
        if rows and any(int(row["plan_id"] or 0) != int(plan_id) for row in rows):
            raise ValueError("This idempotency key was already used for another fulfilment plan.")
        if rows and any(int(row["ordered_by"] or 0) != int(actor_id) for row in rows):
            raise PermissionError("This idempotency key belongs to another ordering actor.")
    if not rows:
        rows = db.execute(
            """
            SELECT id FROM medicine_orders
            WHERE patient_id=? AND plan_id=?
            ORDER BY id ASC
            """,
            (patient_id, plan_id),
        ).fetchall()
    return [int(row["id"]) for row in rows]


def _validate_plan_snapshot(db, plan: dict[str, Any], plan_items: list[dict[str, Any]]) -> None:
    """Verify that the persisted plan still matches its signed snapshot."""
    from .fulfilment_optimizer import compute_plan_hash

    plan_hash = str(plan.get("plan_hash") or "").strip()
    if not plan_hash:
        raise ValueError("This fulfilment plan has no integrity hash and cannot be ordered.")
    try:
        plan_total = float(plan.get("total_inr"))
        item_total = float(plan.get("item_total_inr"))
        delivery_fee = float(plan.get("delivery_fee_inr") or 0.0)
    except (TypeError, ValueError):
        raise ValueError("This fulfilment plan has an invalid monetary snapshot.")
    if not all(math.isfinite(value) and value >= 0 for value in (plan_total, item_total, delivery_fee)):
        raise ValueError("This fulfilment plan has an invalid monetary snapshot.")

    pharmacies = [int(item["pharmacy_id"]) for item in plan_items]
    recomputed_hash = compute_plan_hash(plan_items, pharmacies, plan_total)
    if recomputed_hash != plan_hash:
        raise ValueError("The fulfilment plan changed after it was staged; please refresh it.")

    recomputed_item_total = 0.0
    for item in plan_items:
        try:
            qty = int(item.get("quantity") or 0)
            unit_price = float(item.get("unit_price_inr"))
            line_total = float(item.get("total_price_inr"))
        except (TypeError, ValueError):
            raise ValueError("The fulfilment plan contains an invalid item quote.")
        if qty <= 0 or not all(math.isfinite(value) and value >= 0 for value in (unit_price, line_total)):
            raise ValueError("The fulfilment plan contains an invalid item quote.")
        if round(unit_price * qty, 2) != round(line_total, 2):
            raise ValueError("The fulfilment plan item total no longer matches its unit price.")
        recomputed_item_total += line_total
    if round(recomputed_item_total, 2) != round(item_total, 2):
        raise ValueError("The fulfilment plan item total changed after staging.")
    if round(item_total + delivery_fee, 2) != round(plan_total, 2):
        raise ValueError("The fulfilment plan total changed after staging.")


def _revalidate_inventory_and_quote(
    db,
    plan: dict[str, Any],
    plan_items: list[dict[str, Any]],
    mode: str,
) -> None:
    """Re-read provider inventory and fees immediately before order creation."""
    from .inventory_service import evaluate_freshness

    provider_ids = sorted({int(item["pharmacy_id"]) for item in plan_items})
    current_fees: list[float] = []
    for pharmacy_id in provider_ids:
        provider = db.execute(
            """
            SELECT u.id, u.role, u.active, pp.delivery_fee_base_inr, pp.data_mode,
                   pp.delivery_available, pp.user_id
            FROM users u
            LEFT JOIN provider_profiles pp ON pp.user_id=u.id
            WHERE u.id=?
            """,
            (pharmacy_id,),
        ).fetchone()
        if not provider or provider["role"] != "pharmacy" or not bool(provider["active"]):
            raise ValueError("A pharmacy in this plan is no longer an active provider.")
        profile_mode = str(provider["data_mode"] or mode).strip().upper()
        if profile_mode != mode:
            raise ValueError("A pharmacy in this plan belongs to a different Connected Care data mode.")
        # A provider profile is required for an order-ready quote. A bare
        # pharmacy account with inventory but no provider configuration is
        # discovery-only, not an order destination.
        if provider["user_id"] is None or provider["delivery_fee_base_inr"] is None:
            raise ValueError("A pharmacy in this plan has not supplied a delivery fee quote.")
        try:
            fee = float(provider["delivery_fee_base_inr"])
        except (TypeError, ValueError):
            raise ValueError("A pharmacy in this plan has an invalid delivery fee quote.")
        if not math.isfinite(fee) or fee < 0:
            raise ValueError("A pharmacy in this plan has an invalid delivery fee quote.")
        if provider["delivery_available"] is not None and not bool(provider["delivery_available"]):
            raise ValueError("A pharmacy in this plan no longer offers delivery.")
        current_fees.append(fee)

    try:
        staged_delivery_fee = float(plan.get("delivery_fee_inr") or 0.0)
    except (TypeError, ValueError):
        raise ValueError("The fulfilment plan has an invalid delivery fee.")
    if round(sum(current_fees), 2) != round(staged_delivery_fee, 2):
        raise ValueError("The delivery quote changed; please refresh the fulfilment plan.")

    for item in plan_items:
        pharmacy_id = int(item["pharmacy_id"])
        sku_id = int(item["sku_id"])
        quantity_needed = int(item.get("quantity") or 0)
        observation = db.execute(
            """
            SELECT * FROM inventory_observations
            WHERE pharmacy_id=? AND sku_id=? AND data_mode=?
            """,
            (pharmacy_id, sku_id, mode),
        ).fetchone()
        if not observation:
            raise ValueError("Inventory is no longer confirmed for every item; please refresh the plan.")
        observation_dict = dict(observation)
        effective_status, _freshness = evaluate_freshness(
            observation_dict.get("observed_at"), observation_dict.get("stock_status", "UNKNOWN")
        )
        available = int(observation_dict.get("quantity_available") or 0)
        if effective_status != "CONFIRMED" or available < quantity_needed:
            raise ValueError("Inventory is stale, unavailable, or insufficient; please refresh the plan.")
        price_available = bool(observation_dict.get("price_available", 1))
        current_price = observation_dict.get("price_inr") if price_available else None
        if current_price is None:
            raise ValueError("A current item price is unavailable; the order cannot be submitted.")
        try:
            current_price = float(current_price)
            staged_price = float(item.get("unit_price_inr"))
        except (TypeError, ValueError):
            raise ValueError("The item price quote is invalid.")
        if not math.isfinite(current_price) or current_price < 0:
            raise ValueError("A current item price is invalid; the order cannot be submitted.")
        if round(current_price, 2) != round(staged_price, 2):
            raise ValueError("An item price changed; please refresh the fulfilment plan.")


def submit_order_from_plan(
    actor: Any = None,
    plan_id: int | None = None,
    delivery_address: str | None = None,
    user_confirmed: bool = False,
    idempotency_key: str | None = None,
    expected_plan_hash: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Submit a staged plan after explicit, integrity-checked user approval."""
    # Preserve the historical swapped positional call shape while enforcing
    # the same checks for every invocation path.
    if isinstance(actor, (int, float)) and (isinstance(plan_id, dict) or hasattr(plan_id, "__getitem__")):
        plan_id, actor = int(actor), plan_id
    elif plan_id is None and kwargs.get("plan_id") is not None:
        plan_id = int(kwargs["plan_id"])
    if actor is None and kwargs.get("actor") is not None:
        actor = kwargs["actor"]
    if isinstance(delivery_address, bool):
        user_confirmed = delivery_address
        delivery_address = None
    if "user_confirmed" in kwargs:
        user_confirmed = bool(kwargs["user_confirmed"])
    if expected_plan_hash is None:
        expected_plan_hash = kwargs.get("plan_hash") or kwargs.get("expected_plan_hash")
    if idempotency_key is None:
        idempotency_key = kwargs.get("idempotency_key")

    if not user_confirmed:
        raise ValueError("Explicit user confirmation is strictly required before an order can be submitted.")
    address = str(delivery_address or kwargs.get("delivery_address") or "").strip()
    if not address:
        raise ValueError("A concrete delivery_address is required before an order can be submitted.")
    if plan_id is None:
        raise ValueError("plan_id is required before an order can be submitted.")
    expected_hash = str(expected_plan_hash or "").strip()
    if not expected_hash:
        raise ValueError("plan_hash is required before an order can be submitted.")
    key = _normalise_idempotency_key(idempotency_key)

    db = get_db()
    actor_row = _active_actor(db, actor)
    aid = int(actor_row["id"])
    plan_row = db.execute("SELECT * FROM fulfilment_plans WHERE id=?", (int(plan_id),)).fetchone()
    if not plan_row:
        raise LookupError(f"Fulfilment plan #{plan_id} not found.")
    plan = dict(plan_row)
    patient_id = int(plan["patient_id"])

    from .context_engine import verify_context_authorization

    verify_context_authorization(actor_row, patient_id, "pharmacy_fulfilment")
    if expected_hash != str(plan.get("plan_hash") or ""):
        raise ValueError("The approved plan_hash does not match the staged fulfilment plan.")

    # Replays are safe even after the underlying stock has moved on; they do
    # not create a second order and return only an order the caller already
    # submitted for this patient/plan.
    existing_ids = _existing_orders_for_submission(
        db,
        patient_id=patient_id,
        plan_id=int(plan_id),
        actor_id=aid,
        idempotency_key=key,
    )
    if existing_ids:
        return _order_result(existing_ids, db, replay=True)

    if str(plan.get("status") or "").lower() not in {"staged", "confirmed"}:
        raise ValueError("This fulfilment plan is no longer awaiting confirmation.")

    plan_items = [
        dict(item)
        for item in db.execute(
            """
            SELECT fpi.*, ms.name medicine_name, ms.form, ms.strength, u.name pharmacy_name
            FROM fulfilment_plan_items fpi
            JOIN medication_skus ms ON ms.id=fpi.sku_id
            JOIN users u ON u.id=fpi.pharmacy_id
            WHERE fpi.plan_id=? ORDER BY fpi.id ASC
            """,
            (int(plan_id),),
        ).fetchall()
    ]
    if not plan_items:
        raise ValueError("Plan contains no items to order.")

    _validate_plan_snapshot(db, plan, plan_items)
    mode = _data_mode(str(plan.get("data_mode") or "LIVE"))
    configured_mode = _data_mode()
    if mode != configured_mode:
        raise ValueError("This plan belongs to a different Connected Care data mode; please refresh it.")
    _revalidate_inventory_and_quote(db, plan, plan_items, mode)

    # A key is persisted per logical submission. Deriving one from the
    # immutable plan hash preserves idempotency for trusted service callers
    # that did not supply an HTTP Idempotency-Key.
    persisted_key = key or f"plan-{int(plan_id)}-{expected_hash}"
    existing_ids = _existing_orders_for_submission(
        db,
        patient_id=patient_id,
        plan_id=int(plan_id),
        actor_id=aid,
        idempotency_key=persisted_key,
    )
    if existing_ids:
        return _order_result(existing_ids, db, replay=True)

    now = now_iso()
    by_pharmacy: dict[int, list[dict[str, Any]]] = {}
    for item in plan_items:
        by_pharmacy.setdefault(int(item["pharmacy_id"]), []).append(item)
    delivery_fee = round(float(plan.get("delivery_fee_inr") or 0.0), 2)
    created_orders: list[int] = []
    pharmacy_entries = list(by_pharmacy.items())
    for index, (pharmacy_id, items) in enumerate(pharmacy_entries):
        item_total = round(sum(float(item["total_price_inr"]) for item in items), 2)
        # The staged plan's delivery fee is the sum of provider quotes. For
        # split fulfilment, retain a deterministic equal accounting share on
        # each order while the plan total remains authoritative.
        provider_count = max(1, len(pharmacy_entries))
        equal_share = round(delivery_fee / provider_count, 2)
        fee_share = (
            round(delivery_fee - equal_share * (provider_count - 1), 2)
            if index == provider_count - 1
            else equal_share
        )
        total_amount = round(item_total + fee_share, 2)
        order_uid = f"ord_{patient_id}_{pharmacy_id}_{now[:10].replace('-', '')}_{len(created_orders) + 1}"
        cursor = db.execute(
            """
            INSERT INTO medicine_orders
            (patient_id, ordered_by, pharmacy_id, plan_id, prescription_id, order_uid,
             items_json, delivery_address, total_amount_inr, payment_status,
             acknowledgement_status, tracking_status, idempotency_key, status, data_mode, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'cash_on_delivery', 'pending', 'SUBMITTED', ?, 'pending', ?, ?, ?)
            """,
            (
                patient_id,
                aid,
                pharmacy_id,
                int(plan_id),
                plan.get("prescription_id"),
                order_uid,
                json.dumps(items, sort_keys=True),
                address,
                total_amount,
                f"{persisted_key}:{pharmacy_id}",
                mode,
                now,
                now,
            ),
        )
        order_id = int(cursor.lastrowid)
        db.execute(
            """
            INSERT INTO order_events
            (order_id, event_type, event_status, message, source, created_at)
            VALUES (?, 'ORDER_SUBMITTED', 'SUBMITTED', ?, 'patient_confirmed', ?)
            """,
            (order_id, "Order submitted after explicit confirmation and fresh inventory recheck.", now),
        )
        created_orders.append(order_id)

    db.execute(
        """
        UPDATE fulfilment_plans
        SET confirmed_by_user=1, confirmed_at=?, status='ordered'
        WHERE id=?
        """,
        (now, int(plan_id)),
    )

    from .care_graph import record_care_continuity_event

    record_care_continuity_event(
        patient_id=patient_id,
        event_type="ORDER_PLACED",
        title="Medicine order confirmed",
        summary=f"Prescription fulfilment order placed across {len(by_pharmacy)} participating pharmacy provider(s).",
        source="USER_REPORTED",
        source_ref=f"order:{created_orders[0]}",
        actor_id=aid,
        metadata={"order_ids": created_orders, "plan_id": int(plan_id), "data_mode": mode},
    )
    db.commit()
    return _order_result(created_orders, db)


def _pharmacy_can_act(db, actor: Any, order: dict[str, Any]) -> tuple[Any, bool]:
    actor_row = _active_actor(db, actor)
    aid = int(actor_row["id"])
    if _is_owner(actor_row):
        return actor_row, True
    if actor_row["role"] != "pharmacy" or int(order.get("pharmacy_id") or 0) != aid:
        raise PermissionError("Only the assigned active pharmacy may update this order.")
    return actor_row, False


def acknowledge_order(
    pharmacy_user: Any,
    order_id: int,
    action: str = "accept",
    note: str | None = None,
) -> dict[str, Any]:
    """Record an explicit acknowledgement by the assigned pharmacy."""
    db = get_db()
    row = db.execute("SELECT * FROM medicine_orders WHERE id=?", (int(order_id),)).fetchone()
    if not row:
        raise LookupError(f"Order #{order_id} not found.")
    order = dict(row)
    actor_row, _owner = _pharmacy_can_act(db, pharmacy_user, order)
    normalized_action = str(action or "").strip().lower()
    if normalized_action not in {"accept", "reject"}:
        raise ValueError("Order acknowledgement action must be 'accept' or 'reject'.")
    current = str(order.get("tracking_status") or "SUBMITTED").upper()
    target = "ACCEPTED" if normalized_action == "accept" else "REJECTED"
    if current == target:
        return get_order_details(int(order_id), actor=actor_row)
    if target not in TRACKING_TRANSITIONS.get(current, set()):
        raise ValueError(f"Order cannot be {normalized_action}ed from tracking status {current}.")

    now = now_iso()
    db.execute(
        """
        UPDATE medicine_orders
        SET tracking_status=?, acknowledgement_status=?, acknowledged_at=?, status=?, updated_at=?
        WHERE id=?
        """,
        (
            target,
            "acknowledged" if target == "ACCEPTED" else "rejected",
            now,
            "accepted" if target == "ACCEPTED" else "cancelled",
            now,
            int(order_id),
        ),
    )
    db.execute(
        """
        INSERT INTO order_events
        (order_id, event_type, event_status, message, source, created_at)
        VALUES (?, 'PROVIDER_ACKNOWLEDGEMENT', ?, ?, 'pharmacy_portal', ?)
        """,
        (
            int(order_id),
            target,
            str(note or f"Pharmacy {'accepted' if target == 'ACCEPTED' else 'rejected'} order for fulfilment.").strip(),
            now,
        ),
    )
    db.commit()
    return get_order_details(int(order_id), actor=actor_row)


def update_order_tracking_status(
    actor: Any,
    order_id: int | None = None,
    new_status: str | None = None,
    message: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Advance an order through the provider-controlled tracking state machine."""
    if isinstance(actor, int) and isinstance(order_id, str):
        order_id, new_status = actor, order_id
        actor = kwargs.get("actor")
    if order_id is None:
        order_id = kwargs.get("order_id")
    if new_status is None:
        new_status = kwargs.get("new_status")
    status_upper = str(new_status or "").upper().strip()
    if status_upper == "PACKED":
        # Preserve the legacy alias while keeping one canonical state.
        status_upper = "PREPARING"
    elif status_upper == "DISPATCHED":
        status_upper = "OUT_FOR_DELIVERY"
    if status_upper not in ALLOWED_TRACKING_STATUSES:
        raise ValueError(f"Invalid tracking status '{new_status}'.")
    if order_id is None:
        raise ValueError("order_id is required for tracking updates.")

    db = get_db()
    row = db.execute("SELECT * FROM medicine_orders WHERE id=?", (int(order_id),)).fetchone()
    if not row:
        raise LookupError(f"Order #{order_id} not found.")
    order = dict(row)
    actor_row, _owner = _pharmacy_can_act(db, actor, order)
    current = str(order.get("tracking_status") or "SUBMITTED").upper()
    if current == status_upper:
        return get_order_details(int(order_id), actor=actor_row)
    if status_upper not in TRACKING_TRANSITIONS.get(current, set()):
        raise ValueError(f"Order cannot transition from {current} to {status_upper}.")

    now = now_iso()
    status_value = {
        "ACCEPTED": "accepted",
        "REJECTED": "cancelled",
        "CANCELLED": "cancelled",
        "PREPARING": "preparing",
        "READY_FOR_PICKUP": "ready_for_pickup",
        "OUT_FOR_DELIVERY": "out_for_delivery",
        "DELIVERED": "delivered",
    }.get(status_upper, str(order.get("status") or "pending"))
    db.execute(
        "UPDATE medicine_orders SET tracking_status=?, status=?, updated_at=? WHERE id=?",
        (status_upper, status_value, now, int(order_id)),
    )
    db.execute(
        """
        INSERT INTO order_events
        (order_id, event_type, event_status, message, source, created_at)
        VALUES (?, 'STATUS_UPDATE', ?, ?, 'fulfilment_tracking', ?)
        """,
        (int(order_id), status_upper, message or f"Fulfilment status updated to {status_upper}", now),
    )

    # A delivered order produces one and only one logistics continuity event.
    if status_upper == "DELIVERED":
        already_recorded = db.execute(
            "SELECT 1 FROM order_events WHERE order_id=? AND event_type='MEDICINE_DELIVERED' LIMIT 1",
            (int(order_id),),
        ).fetchone()
        if not already_recorded:
            from .care_graph import record_care_continuity_event

            record_care_continuity_event(
                patient_id=order["patient_id"],
                event_type="MEDICINE_DELIVERED",
                title="Medicines delivered",
                summary=f"Medicine delivery completed for order #{order_id}.",
                source="PROVIDER_RECORDED",
                source_ref=f"order:{order_id}",
                actor_id=int(actor_row["id"]),
                metadata={"order_id": int(order_id)},
            )
            db.execute(
                """
                INSERT INTO order_events
                (order_id, event_type, event_status, message, source, created_at)
                VALUES (?, 'MEDICINE_DELIVERED', 'DELIVERED', ?, 'care_graph', ?)
                """,
                (int(order_id), "Delivery completion recorded in care continuity.", now),
            )
    db.commit()
    return get_order_details(int(order_id), actor=actor_row)


def get_order_details(order_id: int, actor: Any = None, _internal: bool = False) -> dict[str, Any]:
    """Retrieve complete order details, enforcing ownership/provider access."""
    db = get_db()
    row = db.execute(
        """
        SELECT mo.*, u.name patient_name, pharm.name pharmacy_name, fp.strategy_name
        FROM medicine_orders mo
        JOIN users u ON u.id=mo.patient_id
        LEFT JOIN users pharm ON pharm.id=mo.pharmacy_id
        LEFT JOIN fulfilment_plans fp ON fp.id=mo.plan_id
        WHERE mo.id=?
        """,
        (int(order_id),),
    ).fetchone()
    if not row:
        raise LookupError(f"Order #{order_id} not found.")

    res = dict(row)
    if not _internal:
        actor_row = _active_actor(db, actor)
        from .security import is_owner

        aid = int(actor_row["id"])
        if (
            aid != int(res["patient_id"])
            and aid != int(res["ordered_by"])
            and aid != int(res.get("pharmacy_id") or 0)
            and not is_owner(actor_row)
        ):
            raise PermissionError("Access denied to order record.")

    try:
        res["items"] = json.loads(res.get("items_json") or "[]")
    except Exception:
        res["items"] = []
    events = db.execute(
        "SELECT * FROM order_events WHERE order_id=? ORDER BY id ASC",
        (int(order_id),),
    ).fetchall()
    res["events"] = [dict(event) for event in events]
    return res
