from zendoc.db import get_db
from zendoc.notification_providers import deliver_notification, get_notification_delivery
from tests.test_milestone1 import make_app, register_web


def test_configured_email_notification_records_sent_not_delivered(monkeypatch,tmp_path):
    app=make_app(tmp_path)
    client=app.test_client()
    register_web(client,"patient","notify-email@example.com","Notify Email")
    with app.app_context():
        user_id=int(get_db().execute(
            "SELECT id FROM users WHERE email_normalized='notify-email@example.com'"
        ).fetchone()["id"])
        monkeypatch.setattr(
            "zendoc.notification_providers.email_delivery_status",
            lambda: {"transactional_email":True,"provider":"smtp"},
        )
        monkeypatch.setattr(
            "zendoc.notification_providers.send_transactional_email",
            lambda *args,**kwargs: {"status":"sent","provider":"smtp"},
        )
        result=deliver_notification(user_id,"Test email","Hello",channel="email")
        assert result.status=="sent"
        assert result.delivered_at is None
        delivery=get_notification_delivery(result.delivery_id)
        assert delivery["status"]=="sent"
        assert delivery["delivered_at"] is None
        assert delivery["integration_required"] is False


def test_unconfigured_email_stays_queued(monkeypatch,tmp_path):
    app=make_app(tmp_path)
    client=app.test_client()
    register_web(client,"patient","notify-queue@example.com","Notify Queue")
    with app.app_context():
        user_id=int(get_db().execute(
            "SELECT id FROM users WHERE email_normalized='notify-queue@example.com'"
        ).fetchone()["id"])
        monkeypatch.setattr(
            "zendoc.notification_providers.email_delivery_status",
            lambda: {"transactional_email":False,"provider":"none"},
        )
        result=deliver_notification(user_id,"Queued email","Hello",channel="email")
        assert result.status=="queued"
        assert result.integration_required is True
