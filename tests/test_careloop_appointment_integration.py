from zendoc.db import get_db
from tests.test_milestone1 import csrf, login_web, make_client, register_web


def _post_appointment(client, **data):
    page = client.get("/appointments")
    token = csrf(page.data.decode())
    payload = {
        "csrf_token": token,
        "scheduled_for": "2026-12-15T10:00",
        "reason": "Patient requested follow-up",
        **data,
    }
    return client.post("/appointments", data=payload, follow_redirects=False)


def test_registered_provider_appointment_is_actually_linked_to_careloop(tmp_path):
    app, client = make_client(tmp_path)
    register_web(client, "doctor", "loop-doctor@example.com", "CareLoop Doctor")
    client.get("/logout")
    register_web(client, "patient", "loop-patient@example.com", "CareLoop Patient")
    login_web(client, "patient", "loop-patient@example.com")

    response = _post_appointment(
        client,
        provider_email="loop-doctor@example.com",
        provider_name="CareLoop Doctor",
    )
    assert response.status_code == 302
    assert "requested=1" in response.headers["Location"]

    with app.app_context():
        appointment = get_db().execute("SELECT * FROM appointments ORDER BY id DESC LIMIT 1").fetchone()
        assert appointment["provider_id"] is not None
        action = get_db().execute(
            "SELECT * FROM care_actions WHERE service_ref=?",
            (f"zendoc_appointment:{appointment['id']}",),
        ).fetchone()
        assert action is not None
        assert action["status"] == "STAGED"
        assert action["patient_id"] == appointment["patient_id"]
        assert action["provider_name"] == "CareLoop Doctor"
        journey = get_db().execute("SELECT * FROM care_journeys WHERE id=?", (action["journey_id"],)).fetchone()
        assert journey is not None

    # A patient-facing API view truthfully distinguishes internal integration
    # from external hospital/vendor execution.
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "loop-patient@example.com", "password": "StrongPass123", "role": "patient"},
    )
    headers = {"Authorization": f"Bearer {login_response.get_json()['token']}"}
    api = client.get(f"/api/v1/care-actions/{action['id']}", headers=headers)
    assert api.status_code == 200
    payload = api.get_json()["action"]
    assert payload["integration_status"] == "ACTUALLY_INTEGRATED"
    assert payload["execution_scope"] == "zendoc_internal_registered_provider"
    assert payload["actual_execution_recorded"] is True
    assert payload["external_execution"] is False


def test_provider_confirmation_and_completion_sync_to_care_action(tmp_path):
    app, client = make_client(tmp_path)
    register_web(client, "doctor", "sync-doctor@example.com", "Sync Doctor")
    client.get("/logout")
    register_web(client, "patient", "sync-patient@example.com", "Sync Patient")
    login_web(client, "patient", "sync-patient@example.com")
    response = _post_appointment(client, provider_email="sync-doctor@example.com", provider_name="Sync Doctor")
    assert response.status_code == 302

    with app.app_context():
        appointment_id = int(get_db().execute("SELECT id FROM appointments ORDER BY id DESC LIMIT 1").fetchone()["id"])
        action_id = int(get_db().execute(
            "SELECT id FROM care_actions WHERE service_ref=?",
            (f"zendoc_appointment:{appointment_id}",),
        ).fetchone()["id"])

    client.get("/logout")
    login_web(client, "doctor", "sync-doctor@example.com")
    page = client.get("/appointments")
    token = csrf(page.data.decode())
    confirmed = client.post(
        f"/appointments/{appointment_id}/status",
        data={"csrf_token": token, "status": "confirmed"},
        follow_redirects=False,
    )
    assert confirmed.status_code == 302
    with app.app_context():
        assert get_db().execute("SELECT status FROM care_actions WHERE id=?", (action_id,)).fetchone()["status"] == "CONFIRMED"

    page = client.get("/appointments")
    token = csrf(page.data.decode())
    completed = client.post(
        f"/appointments/{appointment_id}/status",
        data={"csrf_token": token, "status": "completed"},
        follow_redirects=False,
    )
    assert completed.status_code == 302
    with app.app_context():
        action = get_db().execute("SELECT status FROM care_actions WHERE id=?", (action_id,)).fetchone()
        assert action["status"] == "COMPLETED"
        events = get_db().execute(
            "SELECT event_type,status FROM care_action_events WHERE action_id=? ORDER BY id",
            (action_id,),
        ).fetchall()
        assert [(event["event_type"], event["status"]) for event in events][-2:] == [
            ("INTERNAL_APPOINTMENT_SYNC", "CONFIRMED"),
            ("INTERNAL_APPOINTMENT_SYNC", "COMPLETED"),
        ]


def test_free_text_external_provider_is_not_marked_actually_integrated(tmp_path):
    app, client = make_client(tmp_path)
    register_web(client, "patient", "external-patient@example.com", "External Patient")
    login_web(client, "patient", "external-patient@example.com")
    response = _post_appointment(client, provider_name="Outside Clinic", provider_email="")
    assert response.status_code == 302

    with app.app_context():
        appointment = get_db().execute("SELECT * FROM appointments ORDER BY id DESC LIMIT 1").fetchone()
        assert appointment["provider_id"] is None
        linked = get_db().execute(
            "SELECT id FROM care_actions WHERE service_ref=?",
            (f"zendoc_appointment:{appointment['id']}",),
        ).fetchone()
        assert linked is None


def test_non_linked_provider_cannot_sync_someone_elses_appointment(tmp_path):
    app, client = make_client(tmp_path)
    register_web(client, "doctor", "owner-doctor@example.com", "Owner Doctor")
    client.get("/logout")
    register_web(client, "doctor", "other-doctor@example.com", "Other Doctor")
    client.get("/logout")
    register_web(client, "patient", "secure-patient@example.com", "Secure Patient")
    login_web(client, "patient", "secure-patient@example.com")
    _post_appointment(client, provider_email="owner-doctor@example.com", provider_name="Owner Doctor")
    with app.app_context():
        appointment_id = int(get_db().execute("SELECT id FROM appointments ORDER BY id DESC LIMIT 1").fetchone()["id"])

    client.get("/logout")
    login_web(client, "doctor", "other-doctor@example.com")
    page = client.get("/appointments")
    token = csrf(page.data.decode())
    denied = client.post(
        f"/appointments/{appointment_id}/status",
        data={"csrf_token": token, "status": "confirmed"},
        follow_redirects=False,
    )
    assert denied.status_code == 403
    with app.app_context():
        action = get_db().execute(
            "SELECT status FROM care_actions WHERE service_ref=?",
            (f"zendoc_appointment:{appointment_id}",),
        ).fetchone()
        assert action["status"] == "STAGED"
