from __future__ import annotations

from zendoc.db import get_db, now_iso
from zendoc.telehealth import set_doctor_availability
from tests.test_milestone1 import login_web, make_app, register_web
from tests.test_milestone7 import headers


PASSWORD = "StrongPass123"


def _register_api(client, email, role, name=None):
    response = client.post(
        "/api/v1/auth/register",
        json={"name": name or role.title(), "email": email, "password": PASSWORD, "role": role},
    )
    assert response.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert login.status_code == 200
    return login.get_json()["token"]


def _user(app, email):
    with app.app_context():
        row = get_db().execute(
            "SELECT * FROM users WHERE email_normalized=?",
            (email.lower(),),
        ).fetchone()
        return dict(row)


def _allow_new_patient_chat(app, doctor):
    with app.app_context():
        set_doctor_availability(
            doctor,
            {
                "status": "available",
                "accepts_chat": True,
                "patient_message_policy": "anyone",
            },
        )


def test_patient_requires_provider_chat_policy_for_doctor_then_doctor_can_reply(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    patient_token = _register_api(client, "policy-chat-patient@example.com", "patient", "Policy Chat Patient")
    doctor_token = _register_api(client, "policy-chat-doctor@example.com", "doctor", "Policy Chat Doctor")
    doctor = _user(app, "policy-chat-doctor@example.com")

    blocked = client.post(
        "/api/v1/conversations",
        json={"target_user_id": doctor["id"], "context_type": "direct"},
        headers=headers(patient_token),
    )
    assert blocked.status_code == 403

    _allow_new_patient_chat(app, doctor)

    started = client.post(
        "/api/v1/conversations",
        json={"target_user_id": doctor["id"], "context_type": "direct"},
        headers=headers(patient_token),
    )
    assert started.status_code == 201
    conversation_id = started.get_json()["conversation"]["id"]

    reply = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"body": "I received your message and can reply here.", "message_type": "text"},
        headers=headers(doctor_token),
    )
    assert reply.status_code == 201


def test_doctor_can_initiate_patient_chat_with_real_care_relationship_without_explicit_chat_grant(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    _register_api(client, "relationship-patient@example.com", "patient", "Relationship Patient")
    doctor_token = _register_api(client, "relationship-doctor@example.com", "doctor", "Relationship Doctor")
    patient = _user(app, "relationship-patient@example.com")
    doctor = _user(app, "relationship-doctor@example.com")

    unrelated = client.post(
        "/api/v1/conversations",
        json={"target_user_id": patient["id"], "context_type": "direct"},
        headers=headers(doctor_token),
    )
    assert unrelated.status_code == 403

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO appointments
            (patient_id, provider_id, provider_name, scheduled_for, reason, status, created_at, updated_at)
            VALUES (?, ?, 'Relationship Doctor', '2026-12-20T10:00', 'Review', 'confirmed', ?, ?)
            """,
            (patient["id"], doctor["id"], now_iso(), now_iso()),
        )
        db.commit()

    allowed = client.post(
        "/api/v1/conversations",
        json={"target_user_id": patient["id"], "context_type": "direct"},
        headers=headers(doctor_token),
    )
    assert allowed.status_code == 201
    assert allowed.get_json()["conversation"]["id"]


def test_patient_can_message_pharmacy_without_existing_order(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    patient_token = _register_api(client, "pharmacy-chat-patient@example.com", "patient")
    pharmacy_token = _register_api(client, "open-pharmacy@example.com", "pharmacy")
    pharmacy = _user(app, "open-pharmacy@example.com")

    started = client.post(
        "/api/v1/conversations",
        json={"target_user_id": pharmacy["id"], "context_type": "direct"},
        headers=headers(patient_token),
    )
    assert started.status_code == 201
    conversation_id = started.get_json()["conversation"]["id"]

    reply = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"body": "We can reply to the patient-started conversation."},
        headers=headers(pharmacy_token),
    )
    assert reply.status_code == 201


def test_same_role_users_can_start_direct_text_chat(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    patient_a_token = _register_api(client, "same-role-a@example.com", "patient", "Same Role A")
    _register_api(client, "same-role-b@example.com", "patient", "Same Role B")
    patient_b = _user(app, "same-role-b@example.com")

    started = client.post(
        "/api/v1/conversations",
        json={"target_user_id": patient_b["id"], "context_type": "direct"},
        headers=headers(patient_a_token),
    )
    assert started.status_code == 201


def test_patient_messages_page_shows_permitted_provider_contacts_without_exposing_patient_directory(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    _register_api(client, "visible-doctor@example.com", "doctor", "Visible Doctor")
    doctor = _user(app, "visible-doctor@example.com")
    _allow_new_patient_chat(app, doctor)
    register_web(client, "patient", "other-patient@example.com", "Other Patient")
    register_web(client, "patient", "visible-patient@example.com", "Visible Patient")
    login_web(client, "patient", "visible-patient@example.com")

    page = client.get("/messages")
    assert page.status_code == 200
    body = page.data.decode()
    assert "Visible Doctor" in body
    assert "Provider accepts new patient messages" in body
    assert "Other Patient" not in body

    searched = client.get("/messages?q=Other+Patient")
    assert searched.status_code == 200
    assert "Other Patient" in searched.data.decode()
    assert "Same-role ZENDOC conversation" in searched.data.decode()


def test_patient_dashboard_surfaces_new_tools_and_ai_surfaces_mental_awareness(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "feature-visibility@example.com", "Feature Visibility")
    login_web(client, "patient", "feature-visibility@example.com")

    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    body = dashboard.data.decode()
    assert "Explore ZENDOC tools" in body
    assert "Agent OS" in body
    assert 'href="/agent-os"' in body
    assert "Health Hub" in body
    assert 'href="/health-hub"' in body
    assert "Mental Wellness &amp; Awareness" in body
    assert "#mental-awareness" in body

    ai_page = client.get("/ai")
    assert ai_page.status_code == 200
    ai_body = ai_page.data.decode()
    assert 'id="mental-awareness"' in ai_body
    assert "A visible place to check in with yourself" in ai_body
    assert 'name="feature" value="mental_health"' in ai_body
