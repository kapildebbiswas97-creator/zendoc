from datetime import datetime, timedelta, timezone

from zendoc.db import get_db
from zendoc.healthcare_finder import HealthcareFinder, normalize_query
from zendoc.intelligence import ZendocIntelligence

from tests.test_milestone1 import api_token, make_client, register_web, login_web, csrf


def register_api(client, email, role):
    response = client.post(
        "/api/v1/auth/register",
        json={"name": email, "email": email, "password": "StrongPass123", "role": role},
    )
    assert response.status_code == 201
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongPass123", "role": role},
    )
    assert response.status_code == 200
    return response.json["token"]


def next_weekday_date(target_weekday):
    today = datetime.now(timezone.utc).date()
    delta = (target_weekday - today.weekday()) % 7
    if delta == 0:
        delta = 7
    return today + timedelta(days=delta)


def create_verified_doctor(app, client):
    doctor_token = register_api(client, "doctor3@example.com", "doctor")
    response = client.post(
        "/api/v1/provider/profile",
        json={
            "specialty": "cardiology",
            "qualifications": "MD",
            "license_identifier": "LIC-123",
            "organization": "Heart Care Clinic",
            "address": "Main Road",
            "city": "Kolkata",
            "state": "WB",
            "postal_code": "700001",
            "public_phone": "1111111111",
        },
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert response.status_code == 200
    with app.app_context():
        profile = get_db().execute("SELECT * FROM provider_profiles WHERE specialty='Cardiology'").fetchone()
        get_db().execute("UPDATE provider_profiles SET verification_status='verified' WHERE id=?", (profile["id"],))
        get_db().commit()
        return doctor_token, profile["id"]


def test_healthcare_finder_query_normalization():
    query = normalize_query("diagnostic centre", "cardiology", "Kolkata", "91", "not-a-number", "100")
    assert query["category"] == "diagnostic_centre"
    assert query["latitude"] is None
    assert query["longitude"] is None
    assert query["radius_km"] == 50


def test_missing_places_key_fallback_has_no_fake_results(tmp_path):
    app, _client = make_client(tmp_path)
    with app.app_context():
        result = HealthcareFinder().search({"category": "hospital", "location": "Kolkata"})
    assert result["external_places"]["available"] is False
    assert result["results"] == []
    assert "unavailable" in result["message"]


def test_patient_cannot_manage_provider_profile(tmp_path):
    _app, client = make_client(tmp_path)
    token = api_token(client, "patient-provider@example.com")
    response = client.post(
        "/api/v1/provider/profile",
        json={"specialty": "Cardiology"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_provider_profile_and_admin_verification(tmp_path):
    app, client = make_client(tmp_path)
    doctor_token = register_api(client, "verifydoc@example.com", "doctor")
    response = client.post(
        "/api/v1/provider/profile",
        json={"specialty": "dermatology", "organization": "Skin Clinic", "city": "Delhi"},
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert response.status_code == 200
    with app.app_context():
        profile = get_db().execute("SELECT * FROM provider_profiles WHERE organization='Skin Clinic'").fetchone()
        assert profile["verification_status"] == "pending"
    login_web(client, "admin", "admin@example.com", "AdminStrong123")
    page = client.get("/admin")
    token = csrf(page.data.decode())
    response = client.post(
        f"/admin/providers/{profile['id']}/status",
        data={"csrf_token": token, "verification_status": "verified"},
        follow_redirects=True,
    )
    assert b"Provider verification status updated" in response.data


def test_schedule_slot_booking_and_double_booking_prevention(tmp_path):
    app, client = make_client(tmp_path)
    _doctor_token, profile_id = create_verified_doctor(app, client)
    date_value = next_weekday_date(0)
    with app.app_context():
        get_db().execute(
            """
            INSERT INTO provider_schedules
            (provider_profile_id, weekday, start_time, end_time, slot_minutes, active, created_at, updated_at)
            VALUES (?, 0, '10:00', '11:00', 30, 1, 'now', 'now')
            """,
            (profile_id,),
        )
        get_db().commit()
    patient_token = api_token(client, "booker@example.com")
    slots = client.get(
        f"/api/v1/providers/{profile_id}/slots?date={date_value.isoformat()}",
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert "10:00" in slots.json["slots"][0]
    response = client.post(
        "/api/v1/appointments",
        json={"provider_profile_id": profile_id, "scheduled_for": slots.json["slots"][0], "reason": "Heart concern"},
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert response.status_code == 201
    second = client.post(
        "/api/v1/appointments",
        json={"provider_profile_id": profile_id, "scheduled_for": slots.json["slots"][0], "reason": "Duplicate"},
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert second.status_code == 400


def test_past_slots_are_not_bookable(tmp_path):
    app, client = make_client(tmp_path)
    _doctor_token, profile_id = create_verified_doctor(app, client)
    patient_token = api_token(client, "past@example.com")
    yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    response = client.post(
        "/api/v1/appointments",
        json={"provider_profile_id": profile_id, "scheduled_for": f"{yesterday}T10:00", "reason": "Past"},
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert response.status_code == 400


def test_cross_user_appointment_isolation(tmp_path):
    app, client = make_client(tmp_path)
    _doctor_token, profile_id = create_verified_doctor(app, client)
    date_value = next_weekday_date(1)
    with app.app_context():
        get_db().execute(
            """
            INSERT INTO provider_schedules
            (provider_profile_id, weekday, start_time, end_time, slot_minutes, active, created_at, updated_at)
            VALUES (?, 1, '10:00', '10:30', 30, 1, 'now', 'now')
            """,
            (profile_id,),
        )
        get_db().commit()
    token_one = api_token(client, "appt-one@example.com")
    token_two = api_token(client, "appt-two@example.com")
    client.post(
        "/api/v1/appointments",
        json={"provider_profile_id": profile_id, "scheduled_for": f"{date_value.isoformat()}T10:00", "reason": "Private"},
        headers={"Authorization": f"Bearer {token_one}"},
    )
    one = client.get("/api/v1/appointments", headers={"Authorization": f"Bearer {token_one}"})
    two = client.get("/api/v1/appointments", headers={"Authorization": f"Bearer {token_two}"})
    assert len(one.json["appointments"]) == 1
    assert two.json["appointments"] == []


def test_healthcare_search_returns_verified_registered_provider(tmp_path):
    app, client = make_client(tmp_path)
    create_verified_doctor(app, client)
    patient_token = api_token(client, "searcher@example.com")
    response = client.get(
        "/api/v1/healthcare/search?category=doctor&specialty=Cardiology&location=Kolkata",
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert response.status_code == 200
    assert response.json["results"][0]["name"] == "Heart Care Clinic"
    assert response.json["results"][0]["verification_status"] == "verified"


def test_ai_provider_intent_routes_to_healthcare_action():
    result, _latency = ZendocIntelligence().respond("I need a cardiologist near me")
    assert result.intent == "doctor"
    assert result.possible_actions[0]["type"] == "find_healthcare"
    assert result.possible_actions[0]["specialty"] == "Cardiology"


def test_emergency_keeps_safety_first_with_finder_handoff():
    result, _latency = ZendocIntelligence().respond("I need emergency care for chest pain")
    assert result.emergency is True
    assert result.intent == "emergency"
    assert any(action["type"] == "future_nearby_emergency" for action in result.possible_actions)


def test_legacy_appointment_compatibility(tmp_path):
    _app, client = make_client(tmp_path)
    token = api_token(client, "legacy-appt@example.com")
    response = client.post(
        "/api/v1/appointments",
        json={"provider_name": "Manual Provider", "scheduled_for": "2099-01-01T10:00", "reason": "Legacy"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
