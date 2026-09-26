import pytest

from flask import abort

from zendoc.db import get_db, now_iso
from zendoc.email_delivery import send_transactional_email
from zendoc.notification_providers import deliver_notification
from zendoc.payments import create_checkout_order
from zendoc.record_storage import get_record_storage
from tests.test_milestone1 import csrf, login_web, make_app, register_web


def test_release_channel_defaults_to_controlled_pilot(tmp_path):
    app = make_app(tmp_path)
    assert app.config["RELEASE_CHANNEL"] == "pilot"


def test_authenticated_user_can_submit_minimum_necessary_feedback(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "pilot-feedback@example.com", "Pilot Patient")
    login_web(client, "patient", "pilot-feedback@example.com")

    page = client.get("/feedback?page=/finder?location=private-value&feature=find_care")
    assert page.status_code == 200
    token = csrf(page.data.decode())

    response = client.post(
        "/feedback",
        data={
            "csrf_token": token,
            "page_path": "/finder?location=private-value",
            "feature": "find_care",
            "source_endpoint": "main.finder",
            "category": "data",
            "severity": "high",
            "message": "The result list did not load after the search timed out.",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"feedback was recorded" in response.data

    with app.app_context():
        row = get_db().execute(
            "SELECT * FROM pilot_feedback_reports ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        assert row["role"] == "patient"
        assert row["page_path"] == "/finder"
        assert row["feature"] == "find_care"
        assert row["severity"] == "high"
        assert row["status"] == "NEW"
        assert row["release_channel"] == "pilot"
        assert "private-value" not in row["page_path"]
        assert "user_agent_hash" in row["technical_context_json"]


def test_feedback_admin_is_owner_only_and_status_is_audited(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "feedback-owner-check@example.com", "Patient")
    login_web(client, "patient", "feedback-owner-check@example.com")

    page = client.get("/feedback?page=/dashboard&feature=dashboard")
    token = csrf(page.data.decode())
    client.post(
        "/feedback",
        data={
            "csrf_token": token,
            "page_path": "/dashboard",
            "feature": "dashboard",
            "category": "usability",
            "severity": "medium",
            "message": "A mobile control was difficult to use.",
        },
    )
    assert client.get("/admin/pilot/feedback", follow_redirects=False).status_code == 403

    client.get("/logout")
    login_web(client, "admin", "admin@example.com", "AdminStrong123")
    admin_page = client.get("/admin/pilot/feedback?severity=medium&status=NEW")
    assert admin_page.status_code == 200
    assert b"A mobile control was difficult to use." in admin_page.data
    token = csrf(admin_page.data.decode())

    response = client.post(
        "/admin/pilot/feedback/1/status",
        data={"csrf_token": token, "status": "INVESTIGATING"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        report = get_db().execute(
            "SELECT status FROM pilot_feedback_reports WHERE id=1"
        ).fetchone()
        assert report["status"] == "INVESTIGATING"
        audit = get_db().execute(
            "SELECT action FROM audit_logs WHERE entity_type='pilot_feedback_report' AND entity_id='1' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert audit["action"] == "pilot_feedback.status_update"


def test_owner_can_assign_and_remove_user_pilot_cohort(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "cohort-patient@example.com", "Cohort Patient")

    with app.app_context():
        user = get_db().execute(
            "SELECT id FROM users WHERE email_normalized='cohort-patient@example.com'"
        ).fetchone()
        user_id = int(user["id"])

    login_web(client, "admin", "admin@example.com", "AdminStrong123")
    page = client.get("/admin/pilot/cohorts")
    assert page.status_code == 200
    token = csrf(page.data.decode())
    response = client.post(
        "/admin/pilot/cohorts",
        data={
            "csrf_token": token,
            "entity_type": "user",
            "entity_id": str(user_id),
            "cohort_label": "Pilot-Patient-01",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Pilot-Patient-01" in response.data

    with app.app_context():
        membership = get_db().execute(
            "SELECT id,active FROM pilot_cohort_memberships WHERE entity_type='user' AND entity_id=?",
            (user_id,),
        ).fetchone()
        membership_id = int(membership["id"])
        assert membership["active"] == 1

    page = client.get("/admin/pilot/cohorts")
    token = csrf(page.data.decode())
    client.post(
        f"/admin/pilot/cohorts/{membership_id}/remove",
        data={"csrf_token": token},
        follow_redirects=True,
    )
    with app.app_context():
        membership = get_db().execute(
            "SELECT active FROM pilot_cohort_memberships WHERE id=?",
            (membership_id,),
        ).fetchone()
        assert membership["active"] == 0


def test_web_500_and_502_recovery_do_not_leak_exception_text(tmp_path):
    app = make_app(tmp_path)
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.get("/_test/upstream-failure")
    def _upstream_failure():
        abort(502)

    @app.get("/_test/internal-failure")
    def _internal_failure():
        raise RuntimeError("internal-detail-marker")

    client = app.test_client()

    upstream = client.get("/_test/upstream-failure")
    assert upstream.status_code == 502
    assert b"connected service is temporarily unavailable" in upstream.data

    internal = client.get("/_test/internal-failure")
    assert internal.status_code == 500
    assert b"Service temporarily unavailable" in internal.data
    assert b"internal-detail-marker" not in internal.data


def test_api_502_recovery_preserves_structured_error_semantics(tmp_path):
    app = make_app(tmp_path)

    @app.get("/api/_test/upstream-failure")
    def _api_upstream_failure():
        abort(502)

    response = app.test_client().get("/api/_test/upstream-failure")
    assert response.status_code == 502
    payload = response.get_json()
    assert payload["error"]["code"] == 502
    assert "did not confirm the external action" in payload["error"]["message"]


def test_find_care_keeps_permission_denied_fallback_and_universal_feedback_entry(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "finder-pilot@example.com", "Finder Pilot")
    login_web(client, "patient", "finder-pilot@example.com")

    finder = client.get("/find-care")
    if finder.status_code in {301, 302, 307, 308}:
        finder = client.get(finder.headers["Location"])
    assert finder.status_code == 200
    assert b"Report a problem / Give feedback" in finder.data
    assert b"Use my current location" in finder.data

    script = client.get("/static/finder.js")
    assert script.status_code == 200
    assert b"Location permission was denied or unavailable" in script.data
    assert b"enter a location manually" in script.data


def test_demo_mode_blocks_consequential_live_external_connectors(tmp_path):
    app = make_app(tmp_path)
    app.config.update(
        CONNECTED_CARE_DATA_MODE="DEMO",
        EMAIL_PROVIDER="smtp",
        SMTP_HOST="smtp.example.invalid",
        SMTP_FROM_EMAIL="noreply@example.invalid",
        STORAGE_PROVIDER="s3",
        S3_BUCKET="demo-must-not-connect",
        S3_ACCESS_KEY_ID="configured-for-test",
        S3_SECRET_ACCESS_KEY="configured-for-test",
    )

    with app.app_context():
        with pytest.raises(RuntimeError, match="blocked for demo/synthetic activity"):
            send_transactional_email(
                "pilot@example.com",
                "Demo external boundary",
                "This must never reach SMTP.",
            )

        with pytest.raises(RuntimeError, match="blocked for demo/synthetic activity"):
            create_checkout_order(
                {"id": 1, "role": "patient", "email": "pilot@example.com"},
                999999,
            )

        storage = get_record_storage()
        with pytest.raises(RuntimeError, match="blocked for demo/synthetic activity"):
            storage._client()


def test_demo_notification_records_blocked_state_without_external_send(tmp_path):
    app = make_app(tmp_path)
    app.config.update(
        CONNECTED_CARE_DATA_MODE="DEMO",
        EMAIL_PROVIDER="smtp",
        SMTP_HOST="smtp.example.invalid",
        SMTP_FROM_EMAIL="noreply@example.invalid",
    )
    with app.app_context():
        db = get_db()
        now = now_iso()
        user_id = db.execute(
            """
            INSERT INTO users
            (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
            VALUES (?,?,?,?, 'patient',1,?,?)
            """,
            (
                "Demo Notification User",
                "demo-notification@example.com",
                "demo-notification@example.com",
                "unused",
                now,
                now,
            ),
        ).lastrowid
        db.commit()

        result = deliver_notification(
            int(user_id),
            "Pilot notification",
            "This demo message must stay inside ZENDOC.",
            channel="email",
        )
        assert result.status == "failed"
        assert result.provider == "demo_external_delivery_blocked"
        delivery = db.execute(
            "SELECT status,provider_response FROM notification_deliveries WHERE id=?",
            (result.delivery_id,),
        ).fetchone()
        assert delivery["status"] == "failed"
        assert delivery["provider_response"] == "demo_external_delivery_blocked"


def test_synthetic_demo_recipient_is_blocked_even_in_live_data_mode(tmp_path):
    app = make_app(tmp_path)
    app.config.update(
        CONNECTED_CARE_DATA_MODE="LIVE",
        EMAIL_PROVIDER="smtp",
        SMTP_HOST="smtp.example.invalid",
        SMTP_FROM_EMAIL="noreply@example.invalid",
    )
    with app.app_context():
        with pytest.raises(RuntimeError, match="synthetic_demo_target"):
            send_transactional_email(
                "demo-patient@zendoc.local",
                "Synthetic demo email",
                "This must not leave ZENDOC.",
            )
