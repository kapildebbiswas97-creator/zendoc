"""Notification provider boundary with a real in-app provider and truthful external status."""
from __future__ import annotations

from dataclasses import dataclass

from .db import get_db, now_iso


SUPPORTED_CHANNELS = {"in_app", "email", "sms", "whatsapp", "push"}


@dataclass(frozen=True)
class DeliveryResult:
    delivery_id: int
    channel: str
    status: str
    provider: str
    integration_required: bool = False

    def to_dict(self):
        return self.__dict__.copy()


def deliver_notification(user_id: int, title: str, message: str, channel: str = "in_app", template_type: str | None = None) -> DeliveryResult:
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
    if channel == "in_app":
        get_db().execute(
            "INSERT INTO notifications (user_id, title, message, channel, created_at) VALUES (?, ?, ?, 'in_app', ?)",
            (int(user_id), title, message, now),
        )
        status = "sent"
        provider_response = "local_in_app"
        sent_at = now
        integration_required = False
    else:
        # Persist intent for a future worker, but never claim external delivery occurred.
        status = "integration_required"
        provider_response = f"{channel}_provider_not_configured"
        sent_at = None
        integration_required = True
    cursor = get_db().execute(
        """
        INSERT INTO notification_deliveries
        (user_id, channel, template_type, status, title, message, provider_response, created_at, sent_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (int(user_id), channel, str(template_type or "")[:100] or None, status, title, message, provider_response, now, sent_at),
    )
    return DeliveryResult(cursor.lastrowid, channel, status, provider_response, integration_required)


def notification_provider_status() -> dict:
    return {
        "in_app": {"status": "working", "provider": "local_in_app"},
        "email": {"status": "integration_required"},
        "sms": {"status": "integration_required"},
        "whatsapp": {"status": "integration_required"},
        "push": {"status": "integration_required"},
    }
