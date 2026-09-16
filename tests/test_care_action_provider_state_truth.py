from zendoc.db import get_db
from tests.test_milestone1 import csrf, login_web, make_client, register_web


def _post_registered_appointment(client, provider_email, provider_name):
    page = client.get("/appointments")
    token = csrf(page.data.decode())
    return client.post(
        "/appointments",
        data={
            "csrf_token": token,
            "scheduled_for": "2026-12-15T10:00",
            "reason": "Provider-state truth regression",
            "provider_email": provider_email,
            "provider_name": provider_name,
        },
        follow_redirects=False,
    )


def _api_headers(client, email, role="patient"):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongPass123", "role": role},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['token']}"}


def test_patient_ledger_transition_cannot_assert_registered_provider_confirmation(tmp_path):
    app, client = make_client(tmp_path)
    doctor_email = "truth-doctor@example.com"
    patient_email = "truth-patient@example.com"

    register_web(client, "doctor", doctor_email, "Truth Doctor")
    client.get("/logout")
    register_web(client, "patient", patient_email, "Truth Patient")
    login_web(client, "patient", patient_email)

    response = _post_registered_appointment(client, doctor_email, "Truth Doctor")
    assert response.status_code == 302

    with app.app_context():
        appointment = get_db().execute("SELECT id FROM appointments ORDER BY id DESC LIMIT 1").fetchone()
        appointment_id = int(appointment["id"])
        action = get_db().execute(
            "SELECT id,status FROM care_actions WHERE service_ref=?",
            (f"zendoc_appointment:{appointment_id}",),
        ).fetchone()
        action_id = int(action["id"])
        assert action["status"] == "STAGED"

    headers = _api_headers(client, patient_email)
    denied = client.post(
        f"/api/v1/care-actions/{action_id}/transition",
        headers=headers,
        json={
            "target_status": "CONFIRMED",
            "note": "Patient says the provider confirmed it.",
            "provenance": {"source": "patient_report"},
        },
    )
    assert denied.status_code == 403
    assert "appointment lifecycle" in denied.get_json()["error"]["message"].lower()

    with app.app_context():
        action = get_db().execute("SELECT status FROM care_actions WHERE id=?", (action_id,)).fetchone()
        assert action["status"] == "STAGED"
        fake_event = get_db().execute(
            "SELECT id FROM care_action_events WHERE action_id=? AND status='CONFIRMED'",
            (action_id,),
        ).fetchone()
        assert fake_event is None

    client.get("/logout")
    login_web(client, "doctor", doctor_email)
    page = client.get("/appointments")
    token = csrf(page.data.decode())
    confirmed = client.post(
        f"/appointments/{appointment_id}/status",
        data={"csrf_token": token, "status": "confirmed"},
        follow_redirects=False,
    )
    assert confirmed.status_code == 302

    with app.app_context():
        action = get_db().execute("SELECT status FROM care_actions WHERE id=?", (action_id,)).fetchone()
        assert action["status"] == "CONFIRMED"
        event = get_db().execute(
            "SELECT event_type,provenance_json FROM care_action_events WHERE action_id=? AND status='CONFIRMED' ORDER BY id DESC LIMIT 1",
            (action_id,),
        ).fetchone()
        assert event["event_type"] == "INTERNAL_APPOINTMENT_SYNC"
        assert "zendoc_registered_provider_appointment" in event["provenance_json"]
