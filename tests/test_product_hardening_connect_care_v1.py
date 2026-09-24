from pathlib import Path

import zendoc.call_signaling as call_signaling
import zendoc.connect as connect_module
import zendoc.milestone7_routes as milestone7_routes
from zendoc.db import get_db
from tests.test_milestone1 import api_token, csrf, login_web, make_app, register_web


ROOT = Path(__file__).resolve().parents[1]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _user(app, email):
    with app.app_context():
        return dict(
            get_db().execute(
                "SELECT * FROM users WHERE email_normalized=?",
                (email.lower(),),
            ).fetchone()
        )


def test_message_send_survives_notification_layer_failure(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    client = app.test_client()
    sender_token = api_token(client, "notify-fail-sender@example.com")
    api_token(client, "notify-fail-recipient@example.com")
    recipient = _user(app, "notify-fail-recipient@example.com")

    started = client.post(
        "/api/v1/conversations",
        json={"target_user_id": recipient["id"], "context_type": "direct"},
        headers=_auth(sender_token),
    )
    assert started.status_code == 201
    conversation_id = int(started.get_json()["conversation"]["id"])

    monkeypatch.setattr(
        connect_module,
        "_deliver_message_notifications_best_effort",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("notification outage")),
    )

    sent = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"body": "This message must survive notification failure.", "message_type": "text"},
        headers=_auth(sender_token),
    )
    assert sent.status_code == 201

    with app.app_context():
        row = get_db().execute(
            """
            SELECT body FROM messages
            WHERE conversation_id=? AND body=?
            """,
            (conversation_id, "This message must survive notification failure."),
        ).fetchone()
        assert row is not None


def test_call_creation_survives_notification_layer_failure(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "call-fail-a@example.com", "Caller A")
    register_web(client, "patient", "call-fail-b@example.com", "Caller B")
    caller = _user(app, "call-fail-a@example.com")
    callee = _user(app, "call-fail-b@example.com")

    with app.app_context():
        conversation = connect_module.start_conversation(
            caller,
            {"target_user_id": callee["id"], "context_type": "direct"},
        )
        monkeypatch.setattr(
            call_signaling,
            "call_permission",
            lambda _actor, conversation_id, call_type: {
                "allowed": True,
                "reason": "test permission",
                "call_type": call_type,
                "conversation_id": int(conversation_id),
                "other_id": callee["id"],
                "other_name": callee["name"],
                "other_role": callee["role"],
            },
        )
        monkeypatch.setattr(
            call_signaling,
            "deliver_notification",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("notification outage")),
        )

        call = call_signaling.create_call(
            caller,
            int(conversation["id"]),
            "voice",
            '{"type":"offer","sdp":"v=0\\r\\nnotification-failure-test"}',
        )

        assert call["status"] == "ringing"
        row = get_db().execute(
            "SELECT status FROM connect_calls WHERE id=?",
            (int(call["id"]),),
        ).fetchone()
        assert row["status"] == "ringing"


def test_ors_booking_is_recorded_as_patient_reported_health_memory(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "ors-memory@example.com", "ORS Memory")
    login_web(client, "patient", "ors-memory@example.com")

    page = client.get("/finder")
    assert page.status_code == 200
    token = csrf(page.data.decode())

    saved = client.post(
        "/finder/external-opd",
        data={
            "csrf_token": token,
            "source": "ORS",
            "provider_name": "Example Government Medical College",
            "scheduled_for": "2026-10-20T11:30",
            "reason": "Cardiology OPD",
            "reference": "ORS-USER-REF-123",
        },
        follow_redirects=True,
    )
    assert saved.status_code == 200
    assert b"patient-reported" in saved.data.lower()

    user = _user(app, "ors-memory@example.com")
    with app.app_context():
        row = get_db().execute(
            """
            SELECT event_type,provider_name,source,source_ref,summary
            FROM health_timeline_events
            WHERE patient_id=?
            ORDER BY id DESC LIMIT 1
            """,
            (user["id"],),
        ).fetchone()
        assert row["event_type"] == "appointment"
        assert row["provider_name"] == "Example Government Medical College"
        assert row["source"] == "USER_REPORTED"
        assert "ORS" in row["source_ref"]
        assert "not independently verified" in row["summary"]


def test_connected_care_frontend_contains_no_fabricated_pharmacy_examples():
    body = (ROOT / "templates" / "connected_care.html").read_text(encoding="utf-8")

    assert "Green Cross Pharmacy" not in body
    assert "CarePlus + Neighbour Meds" not in body
    assert "Home Address, Main City" not in body
    assert "plan.options" in body
    assert "X-CSRF-Token" in body
    assert "user_confirmed: true" in body
    assert "provider acknowledgement" in body.lower()
    assert "verified lab offer" in body.lower()


def test_voice_fallback_is_explicit_and_never_auto_sends():
    script = (ROOT / "static" / "edgecare_voice.js").read_text(encoding="utf-8")

    assert "BrowserSpeechRecognition" in script
    assert "browserFallbackMode" in script
    assert "Use browser dictation" in script
    assert "review the transcript" in script.lower()
    assert "form.submit()" not in script
    assert "form.requestSubmit()" not in script


def test_community_supports_mobile_capture_without_weakening_safety_copy():
    body = (ROOT / "templates" / "community.html").read_text(encoding="utf-8")

    assert 'capture="environment"' in body
    assert "playsinline" in body
    assert "Your story" in body
    assert "Community Guidelines" in body
    assert "report" in body.lower()
    assert "block" in body.lower()


def test_carefin_template_renders_and_legacy_connected_url_redirects(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "carefin-render@example.com", "CareFin Render")
    login_web(client, "patient", "carefin-render@example.com")

    page = client.get("/carefin")
    assert page.status_code == 200
    assert b"CareFin Benefits" in page.data
    assert b"My CareFin cases" in page.data
    assert b"My tracked support" in page.data

    legacy = client.get("/connected-care/carefin", follow_redirects=False)
    assert legacy.status_code == 200
    assert b"CareFin benefits discovery" in legacy.data
    assert b"My CareFin cases" in legacy.data


def test_care_journey_links_real_care_surfaces():
    body = (ROOT / "templates" / "care_journey.html").read_text(encoding="utf-8")

    for endpoint in (
        "main.finder",
        "connected_care.diagnostics_page",
        "carefin.carefin_page",
        "connected_care.connected_care_home",
        "health_memory.timeline_page",
    ):
        assert endpoint in body
    assert "Government OPD" in body
    assert "patient-reported" in body


def test_live_message_fragment_survives_unread_counter_failure(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "live-fragment-a@example.com", "Live A")
    register_web(client, "patient", "live-fragment-b@example.com", "Live B")
    login_web(client, "patient", "live-fragment-a@example.com")
    sender = _user(app, "live-fragment-a@example.com")
    recipient = _user(app, "live-fragment-b@example.com")

    with app.app_context():
        conversation = connect_module.start_conversation(
            sender,
            {"target_user_id": recipient["id"], "context_type": "direct"},
        )
        connect_module.send_message(
            sender,
            conversation["id"],
            {"body": "Live fragment resilience", "message_type": "text"},
        )

    monkeypatch.setattr(
        milestone7_routes,
        "unread_count",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("counter unavailable")),
    )

    response = client.get(f"/messages/{conversation['id']}/live")

    assert response.status_code == 200
    assert b"Live fragment resilience" in response.data
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-ZENDOC-Unread-Count"] == "0"
