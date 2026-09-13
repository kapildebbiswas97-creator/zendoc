"""Operational pharmacy-order lifecycle endpoints.

These routes update only ZENDOC's own persisted medicine-order records. They do
not claim pharmacy stock, payment, dispensing, or external delivery execution.
"""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from .db import get_db
from .routes import audit, require_api_user
from .security import is_owner


bp = Blueprint("pharmacy_order_ops", __name__)

ORDER_STATUS_TRANSITIONS = {
    "pending": {"accepted", "cancelled"},
    "accepted": {"preparing", "cancelled"},
    "preparing": {"dispatched", "cancelled"},
    "dispatched": {"completed"},
    "completed": set(),
    "cancelled": set(),
}


def update_medicine_order_status(actor, order_id: int, target_status: str) -> dict:
    """Update one assigned medicine order with strict provider authorization."""
    db = get_db()
    row = db.execute(
        """
        SELECT mo.*, patient.name AS patient_name, pharmacy.name AS pharmacy_name
        FROM medicine_orders mo
        JOIN users patient ON patient.id=mo.patient_id
        LEFT JOIN users pharmacy ON pharmacy.id=mo.pharmacy_id
        WHERE mo.id=?
        """,
        (int(order_id),),
    ).fetchone()
    if not row:
        raise LookupError("Medicine order not found.")
    if not row["pharmacy_id"]:
        raise PermissionError("This medicine request is not assigned to a ZENDOC pharmacy.")

    actor_id = int(actor["id"])
    if actor_id != int(row["pharmacy_id"]) and not is_owner(actor):
        raise PermissionError("Only the assigned pharmacy or ZENDOC owner can update this medicine order.")

    target = str(target_status or "").strip().lower()
    if not target:
        raise ValueError("status is required.")
    current = str(row["status"] or "pending").strip().lower()
    if target == current:
        return dict(row)
    if target not in ORDER_STATUS_TRANSITIONS.get(current, set()):
        raise ValueError(f"Invalid medicine order transition: {current} -> {target}.")

    db.execute(
        "UPDATE medicine_orders SET status=? WHERE id=?",
        (target, int(order_id)),
    )
    db.commit()

    # The order is the operational source of truth. CareLoop mirrors it only
    # after the source update succeeds, and a ledger failure cannot roll back
    # the pharmacy's real ZENDOC workflow state.
    try:
        from .careloop_pharmacy import sync_registered_pharmacy_order_status

        sync_registered_pharmacy_order_status(actor, int(order_id), target)
    except Exception:
        current_app.logger.exception("CareLoop pharmacy-order status sync failed safely.")

    updated = db.execute(
        """
        SELECT mo.*, patient.name AS patient_name, pharmacy.name AS pharmacy_name
        FROM medicine_orders mo
        JOIN users patient ON patient.id=mo.patient_id
        LEFT JOIN users pharmacy ON pharmacy.id=mo.pharmacy_id
        WHERE mo.id=?
        """,
        (int(order_id),),
    ).fetchone()
    return dict(updated)


def _api_error(error):
    if isinstance(error, PermissionError):
        status = 403
    elif isinstance(error, LookupError):
        status = 404
    else:
        status = 400
    return jsonify({"error": {"code": status, "message": str(error)}}), status


@bp.post("/api/v1/pharmacy/orders/<int:order_id>/status")
def api_update_medicine_order_status(order_id):
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        order = update_medicine_order_status(user, order_id, data.get("status"))
        audit("update_status", "medicine_order", str(order_id), actor=user)
        get_db().commit()
        return jsonify({
            "medicine_order": order,
            "execution_notice": (
                "This status reflects the assigned pharmacy's ZENDOC workflow only. "
                "It does not independently verify stock, payment, dispensing, or an external courier event."
            ),
        })
    except (ValueError, LookupError, PermissionError) as exc:
        return _api_error(exc)
