"""Notification provider boundary with a real in-app provider and truthful external status."""
from __future__ import annotations

from dataclasses import dataclass

from .db import get_db, now_iso


SUPPORTED_CHANNELS = {"in_app", "email", "sms", "whatsapp", "push"}
DELIVERY_STATUSES = {"queued", "sent", "delivered", "failed"}
DELIVERY_TRANSITIONS = {
    "queued": {"sent", "failed"},
    "sent": {"delivered", "failed"},
    "delivered": set(),
    "failed": set(),
}


@dataclass(frozen=True)
class DeliveryResult:
    delivery_id: int
    channel: str
    status: str
    provider: str
    integration_required: bool = False
    queued_at: str | None = None
    sent_at: str | None = None
    delivered_at: str | None = None
    failed_at: str | None = None

    def to_dict(self):
        return self.__dict__.copy()


def deliver_notification(
    user_id: int,
    title: str,
    message: str,
    channel: str = "in_app",
    template_type: str | None = None,
) -> DeliveryResult:
    channel = str(channel or "in_app").strip().lower()
    if channel not in SUPPORTED_CHANNELS:
        raise ValueError("Unsupported notification channel.")
    user = get_db().execute("SELECT id FROM users WHERE id=? AND active=1", (int(user_id),)).fetchone()
    if not user:
        raise LookupError("Notification recipient not found.")
    title = str(title or "ZENDOC notification").strip()[:180]
    message = str(message or "").strip()[:1000]
    if not message:
        raise ValueError("Notification message is required.")

    now = now_iso()
    queued_at = now
    sent_at = None
    delivered_at = None
    failed_at = None

    if channel == "in_app":
        get_db().execute(
            "INSERT INTO notifications (user_id, title, message, channel, created_at) VALUES (?, ?, ?, 'in_app', ?)",
            (int(user_id), title, message, now),
        )
        status = "delivered"
        provider_response = "local_in_app"
        sent_at = now
        delivered_at = now
        integration_required = False
    else:
        # Persist a truthful queue intent. Without a configured external
        # provider, this is neither sent nor delivered.
        status = "queued"
        provider_response = f"{channel}_provider_not_configured"
        integration_required = True

    cursor = get_db().execute(
        """
        INSERT INTO notification_deliveries
        (user_id,channel,template_type,status,title,message,provider_response,
         created_at,queued_at,sent_at,delivered_at,failed_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            int(user_id),
            channel,
            str(template_type or "")[:100] or None,
            status,
            title,
            message,
            provider_response,
            now,
            queued_at,
            sent_at,
            delivered_at,
            failed_at,
            now,
        ),
    )
    return DeliveryResult(
        int(cursor.lastrowid),
        channel,
        status,
        provider_response,
        integration_required,
        queued_at,
        sent_at,
        delivered_at,
        failed_at,
    )


def get_notification_delivery(delivery_id: int) -> dict:
    row = get_db().execute(
        "SELECT * FROM notification_deliveries WHERE id=?",
        (int(delivery_id),),
    ).fetchone()
    if not row:
        raise LookupError(f"Notification delivery #{delivery_id} not found.")
    item = dict(row)
    item["integration_required"] = (
        item["channel"] != "in_app"
        and str(item.get("provider_response") or "").endswith("_provider_not_configured")
        and item["status"] == "queued"
    )
    item["truth_notice"] = (
        "queued means no send is claimed; sent means a configured provider accepted the send; "
        "delivered requires provider/local confirmation; failed is terminal for this delivery attempt."
    )
    return item


def transition_notification_delivery(
    delivery_id: int,
    *,
    status: str,
    provider_response: str | None = None,
    provider_message_id: str | None = None,
    failure_reason: str | None = None,
) -> dict:
    target = str(status or "").strip().lower()
    if target not in DELIVERY_STATUSES - {"queued"}:
        raise ValueError("Notification delivery may transition only to sent, delivered, or failed.")

    current = get_notification_delivery(delivery_id)
    current_status = str(current["status"])
    if target not in DELIVERY_TRANSITIONS.get(current_status, set()):
        raise ValueError(f"Invalid notification delivery transition: {current_status} -> {target}.")

    now = now_iso()
    sent_at = current.get("sent_at")
    delivered_at = current.get("delivered_at")
    failed_at = current.get("failed_at")
    if target == "sent":
        sent_at = sent_at or now
    elif target == "delivered":
        sent_at = sent_at or now
        delivered_at = delivered_at or now
    elif target == "failed":
        failed_at = failed_at or now
        if not str(failure_reason or "").strip():
            raise ValueError("failure_reason is required when marking delivery failed.")

    get_db().execute(
        """
        UPDATE notification_deliveries
        SET status=?,provider_response=COALESCE(?,provider_response),
            provider_message_id=COALESCE(?,provider_message_id),
            failure_reason=COALESCE(?,failure_reason),
            sent_at=?,delivered_at=?,failed_at=?,updated_at=?
        WHERE id=?
        """,
        (
            target,
            str(provider_response or "").strip()[:1000] or None,
            str(provider_message_id or "").strip()[:300] or None,
            str(failure_reason or "").strip()[:1000] or None,
            sent_at,
            delivered_at,
            failed_at,
            now,
            int(delivery_id),
        ),
    )
    return get_notification_delivery(delivery_id)


def notification_provider_status() -> dict:
    return {
        "in_app": {"status": "working", "provider": "local_in_app"},
        "email": {"status": "integration_required"},
        "sms": {"status": "integration_required"},
        "whatsapp": {"status": "integration_required"},
        "push": {"status": "integration_required"},
    }
