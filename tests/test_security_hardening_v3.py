from __future__ import annotations

import pytest

from zendoc.audit_privacy import safe_payload
from zendoc.db import get_db, now_iso
from zendoc.event_bus import publish_event
from zendoc.family_care import authorize_family_patient
from zendoc.health_access import authorize_patient
from tests.test_milestone1 import make_app
from tests.test_milestone7 import api_token, headers


def _register_role(client, email, role):
    registered = client.post(
        "/api/v1/auth/register",
        json={"name": role.title(), "email": email, "password": "StrongPass123", "role": role},
    )
    assert registered.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongPass123"},
    )
    assert login.status_code == 200
    return login.get_json()["token"]


def _user_id(app, email):
    with app.app_context():
        return int(
            get_db().execute(
                "SELECT id FROM users WHERE email_normalized=?",
                (email.lower(),),
            ).fetchone()["id"]
        )


def test_patient_cannot_read_another_patients_health_summary(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    token_a = api_token(client, "idor-a@example.com")
    api_token(client, "idor-b@example.com")
    patient_b = _user_id(app, "idor-b@example.com")

    response = client.get(
        f"/api/v1/health-summary?patient_id={patient_b}",
        headers=headers(token_a),
    )
    assert response.status_code == 403


@pytest.mark.parametrize("role", ["doctor", "hospital"])
def test_provider_without_consent_cannot_read_patient_health_summary(tmp_path, role):
    app = make_app(tmp_path)
    client = app.test_client()
    patient_token = api_token(client, f"consent-patient-{role}@example.com")
    assert patient_token
    patient_id = _user_id(app, f"consent-patient-{role}@example.com")
    provider_token = _register_role(client, f"no-consent-{role}@example.com", role)

    response = client.get(
        f"/api/v1/health-summary?patient_id={patient_id}",
        headers=headers(provider_token),
    )
    assert response.status_code == 403


def test_fake_admin_role_cannot_override_health_or_family_authorization(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    api_token(client, "owner-boundary-patient@example.com")
    patient_id = _user_id(app, "owner-boundary-patient@example.com")

    fake_admin = {
        "id": 999999,
        "role": "admin",
        "active": 1,
        "email": "not-the-owner@example.com",
        "email_normalized": "not-the-owner@example.com",
    }

    with app.app_context():
        with pytest.raises(PermissionError):
            authorize_patient(fake_admin, patient_id, "profile")
        with pytest.raises(PermissionError):
            authorize_family_patient(fake_admin, patient_id, "pharmacy")


def test_universal_search_api_requires_bearer_authentication(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    response = client.get("/api/v1/search?q=doctor")
    assert response.status_code == 401


def test_pharmacy_order_rejects_foreign_prescription_record_id(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    token_a = api_token(client, "order-a@example.com")
    api_token(client, "order-b@example.com")
    patient_a = _user_id(app, "order-a@example.com")
    patient_b = _user_id(app, "order-b@example.com")

    with app.app_context():
        db = get_db()
        record_id = db.execute(
            """
            INSERT INTO medical_records
            (owner_id, uploaded_by, title, category, original_filename, stored_filename, mime_type, file_size, created_at)
            VALUES (?, ?, 'Foreign prescription', 'prescription', 'foreign.txt', 'foreign-idor.txt', 'text/plain', 10, ?)
            """,
            (patient_b, patient_b, now_iso()),
        ).lastrowid
        db.commit()

    response = client.post(
        "/api/v1/pharmacy/orders",
        json={
            "patient_id": patient_a,
            "items": [{"medicine": "Paracetamol"}],
            "delivery_address": "Test address",
            "prescription_record_id": record_id,
        },
        headers=headers(token_a),
    )
    assert response.status_code == 403


def test_emergency_precedence_beats_appointment_and_pharmacy_intents(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    token = api_token(client, "mixed-emergency@example.com")

    response = client.post(
        "/api/v1/agent/message",
        json={"message": "I have severe chest pain; also book an appointment and find a pharmacy"},
        headers=headers(token),
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["intent"] == "emergency"
    assert payload["urgency"] == "emergency"
    assert payload["plan"]["assigned_agent"] == "SafetyAgent"
    assert payload["plan"]["steps"] == []

    with app.app_context():
        run = get_db().execute(
            "SELECT command_text, intent, urgency FROM agent_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert run["intent"] == "emergency"
        assert run["urgency"] == "emergency"
        assert "chest pain" not in run["command_text"].lower()
        assert run["command_text"].startswith("agent_command;chars=")


def test_legacy_ai_helpers_apply_emergency_precedence(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    token = api_token(client, "legacy-emergency@example.com")

    assistant = client.post(
        "/api/v1/ai/assistant",
        json={"message": "I have chest pain but I also need an appointment"},
        headers=headers(token),
    )
    assert assistant.status_code == 200
    assert "emergency" in assistant.get_json()["answer"].lower()

    mental = client.post(
        "/api/v1/ai/mental-health",
        json={"age_group": "adult", "context": "I want to kill myself", "stress_level": 1},
        headers=headers(token),
    )
    assert mental.status_code == 200
    assert mental.get_json()["emergency"] is True
    assert mental.get_json()["risk_level"] == "high"


def test_operational_event_payload_and_errors_are_privacy_minimized(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        event = publish_event(
            "security.privacy_test",
            actor={"id": 1},
            payload={
                "patient_id": 42,
                "intent": "diagnostics",
                "address": "12 Private Lane",
                "message": "I have chest pain",
                "token": "super-secret-token",
                "email": "private@example.com",
            },
            error="Bearer secret-token failed for private@example.com +91 9876543210",
        )
        assert event["payload"]["patient_id"] == 42
        assert event["payload"]["intent"] == "diagnostics"
        assert event["payload"]["address"] == "[redacted]"
        assert event["payload"]["message"] == "[redacted]"
        assert event["payload"]["token"] == "[redacted]"
        assert event["payload"]["email"] == "[redacted]"
        assert "private@example.com" not in (event.get("error") or "")
        assert "9876543210" not in (event.get("error") or "")
        assert "secret-token" not in (event.get("error") or "")


def test_safe_payload_preserves_ids_but_redacts_clinical_text():
    payload = safe_payload(
        {
            "patient_id": 7,
            "task_id": 9,
            "status": "completed",
            "symptoms": "chest pain and shortness of breath",
            "delivery_address": "Private address",
            "notes": "Sensitive clinical note",
        }
    )
    assert payload["patient_id"] == 7
    assert payload["task_id"] == 9
    assert payload["status"] == "completed"
    assert payload["symptoms"] == "[redacted]"
    assert payload["delivery_address"] == "[redacted]"
    assert payload["notes"] == "[redacted]"
