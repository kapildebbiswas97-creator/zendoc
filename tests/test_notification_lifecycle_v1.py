from zendoc.db import get_db
from zendoc.notification_providers import (
    deliver_notification,
    get_notification_delivery,
    transition_notification_delivery,
)
from tests.test_milestone1 import make_app


def create_user(db, email="notify@example.com"):
    now = "2026-09-08T00:00:00+00:00"
    return int(
        db.execute(
            """
            INSERT INTO users
            (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
            VALUES ('Notify User',?,?, 'x','patient',1,?,?)
            """,
            (email, email, now, now),
        ).lastrowid
    )


def test_in_app_notification_is_delivered_only_after_local_inbox_write(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        user_id = create_user(db)

        result = deliver_notification(
            user_id,
            "Test notification",
            "This notification is visible in the in-app inbox.",
            channel="in_app",
        )
        db.commit()

        assert result.status == "delivered"
        assert result.integration_required is False
        assert result.sent_at is not None
        assert result.delivered_at is not None

        inbox = db.execute(
            "SELECT * FROM notifications WHERE user_id=?",
            (user_id,),
        ).fetchall()
        assert len(inbox) == 1

        delivery = get_notification_delivery(result.delivery_id)
        assert delivery["status"] == "delivered"
        assert delivery["channel"] == "in_app"
        assert delivery["queued_at"] is not None
        assert delivery["sent_at"] is not None
        assert delivery["delivered_at"] is not None
        assert delivery["failed_at"] is None


def test_unconfigured_external_channel_is_queued_not_sent(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        user_id = create_user(db, "external-notify@example.com")

        result = deliver_notification(
            user_id,
            "Email intent",
            "This should not be falsely claimed as sent.",
            channel="email",
        )
        db.commit()

        assert result.status == "queued"
        assert result.integration_required is True
        assert result.sent_at is None
        assert result.delivered_at is None

        delivery = get_notification_delivery(result.delivery_id)
        assert delivery["status"] == "queued"
        assert delivery["integration_required"] is True
        assert delivery["sent_at"] is None
        assert delivery["delivered_at"] is None

        inbox = db.execute(
            "SELECT COUNT(*) c FROM notifications WHERE user_id=?",
            (user_id,),
        ).fetchone()["c"]
        assert inbox == 0


def test_external_delivery_state_machine_requires_sent_before_delivered(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        user_id = create_user(db, "state-machine@example.com")
        queued = deliver_notification(
            user_id,
            "External",
            "Provider transition test.",
            channel="sms",
        )

        invalid = False
        try:
            transition_notification_delivery(
                queued.delivery_id,
                status="delivered",
                provider_response="provider_delivered",
            )
        except ValueError:
            invalid = True
        assert invalid is True

        sent = transition_notification_delivery(
            queued.delivery_id,
            status="sent",
            provider_response="provider_accepted",
            provider_message_id="provider-msg-123",
        )
        assert sent["status"] == "sent"
        assert sent["sent_at"] is not None
        assert sent["delivered_at"] is None

        delivered = transition_notification_delivery(
            queued.delivery_id,
            status="delivered",
            provider_response="provider_delivery_confirmed",
        )
        db.commit()
        assert delivered["status"] == "delivered"
        assert delivered["provider_message_id"] == "provider-msg-123"
        assert delivered["delivered_at"] is not None


def test_failed_delivery_requires_reason_and_is_terminal(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        user_id = create_user(db, "failed-notify@example.com")
        queued = deliver_notification(
            user_id,
            "External",
            "Failure state test.",
            channel="push",
        )

        missing_reason = False
        try:
            transition_notification_delivery(queued.delivery_id, status="failed")
        except ValueError:
            missing_reason = True
        assert missing_reason is True

        failed = transition_notification_delivery(
            queued.delivery_id,
            status="failed",
            provider_response="provider_error",
            failure_reason="No push provider is configured.",
        )
        db.commit()
        assert failed["status"] == "failed"
        assert failed["failed_at"] is not None

        terminal = False
        try:
            transition_notification_delivery(
                queued.delivery_id,
                status="sent",
                provider_response="late_retry",
            )
        except ValueError:
            terminal = True
        assert terminal is True
