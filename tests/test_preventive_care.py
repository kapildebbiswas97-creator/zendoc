from datetime import datetime, timedelta, timezone

from zendoc.db import get_db
from tests.test_milestone1 import make_client, register_web


def _patient_id(app, email):
    with app.app_context():
        return int(get_db().execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()["id"])


def _iso_in(days):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="seconds")


def _api_headers(client, email, password="StrongPass123"):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password, "role": "patient"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['token']}"}


def test_patient_can_create_list_and_complete_recorded_preventive_plan(tmp_path):
    _app, client = make_client(tmp_path)
    email = "preventive-owner@example.com"
    register_web(client, "patient", email)
    headers = _api_headers(client, email)

    created = client.post(
        "/api/v1/preventive-care/plans",
        headers=headers,
        json={
            "title": "Dental follow-up I already scheduled",
            "category": "dental",
            "due_at": _iso_in(10),
            "source_type": "patient_entered",
            "source_ref": "Patient-entered appointment reminder",
        },
    )
    assert created.status_code == 201
    plan = created.get_json()["plan"]
    assert plan["source_type"] == "patient_entered"
    assert plan["due_state"] == "DUE_SOON"
    assert plan["medical_recommendation"] is False

    listed = client.get("/api/v1/preventive-care/plans?status=ACTIVE", headers=headers)
    assert listed.status_code == 200
    assert [item["plan_uid"] for item in listed.get_json()["plans"]] == [plan["plan_uid"]]

    completed = client.post(f"/api/v1/preventive-care/plans/{plan['id']}/complete", headers=headers)
    assert completed.status_code == 200
    assert completed.get_json()["plan"]["status"] == "COMPLETED"
    assert completed.get_json()["plan"]["due_state"] == "COMPLETED"


def test_preventive_plan_due_state_is_deterministic_not_clinical(tmp_path):
    _app, client = make_client(tmp_path)
    email = "preventive-due@example.com"
    register_web(client, "patient", email)
    headers = _api_headers(client, email)

    overdue = client.post(
        "/api/v1/preventive-care/plans",
        headers=headers,
        json={"title": "User-entered reminder", "category": "other", "due_at": _iso_in(-2)},
    )
    upcoming = client.post(
        "/api/v1/preventive-care/plans",
        headers=headers,
        json={"title": "Later user reminder", "category": "other", "due_at": _iso_in(60)},
    )

    assert overdue.status_code == 201
    assert overdue.get_json()["plan"]["due_state"] == "OVERDUE"
    assert upcoming.status_code == 201
    assert upcoming.get_json()["plan"]["due_state"] == "UPCOMING"
    assert "not an automatically generated clinical recommendation" in overdue.get_json()["plan"]["notice"].lower()


def test_patient_cannot_spoof_provider_provenance(tmp_path):
    _app, client = make_client(tmp_path)
    email = "preventive-spoof@example.com"
    register_web(client, "patient", email)

    response = client.post(
        "/api/v1/preventive-care/plans",
        headers=_api_headers(client, email),
        json={
            "title": "Fake provider plan",
            "category": "screening",
            "due_at": _iso_in(30),
            "source_type": "provider_entered",
        },
    )
    assert response.status_code == 403
    assert "patient-entered" in response.get_json()["error"]["message"].lower()


def test_preventive_plan_blocks_cross_patient_idor(tmp_path):
    app, client = make_client(tmp_path)
    first_email = "preventive-first@example.com"
    second_email = "preventive-second@example.com"
    register_web(client, "patient", first_email)
    client.get("/logout")
    register_web(client, "patient", second_email)
    second_id = _patient_id(app, second_email)
    second_headers = _api_headers(client, second_email)
    created = client.post(
        "/api/v1/preventive-care/plans",
        headers=second_headers,
        json={"title": "Private plan", "category": "other", "due_at": _iso_in(5)},
    )
    assert created.status_code == 201

    denied = client.get(
        f"/api/v1/preventive-care/plans?patient_id={second_id}",
        headers=_api_headers(client, first_email),
    )
    assert denied.status_code == 403
    assert "cannot access another patient" in denied.get_json()["error"]["message"].lower()


def test_preventive_plan_requires_authentication_and_valid_category(tmp_path):
    _app, client = make_client(tmp_path)
    unauthenticated = client.get("/api/v1/preventive-care/plans")
    assert unauthenticated.status_code in {401, 403}

    email = "preventive-validation@example.com"
    register_web(client, "patient", email)
    invalid = client.post(
        "/api/v1/preventive-care/plans",
        headers=_api_headers(client, email),
        json={"title": "Bad category", "category": "diagnose_me", "due_at": _iso_in(20)},
    )
    assert invalid.status_code == 400
