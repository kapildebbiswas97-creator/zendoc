import pytest

from tests.test_milestone1 import csrf, login_web, make_client, register_web
from zendoc.db import get_db, now_iso
from zendoc.email_verification import mark_email_verified
from zendoc.human_operations import create_staff_task
from zendoc.partner_handoffs import list_provider_booking_handoffs
from zendoc.pharmacy_service import list_medicine_orders
from zendoc.provider_service import available_slots, create_schedule, get_provider_profile_for_user, upsert_provider_profile
from zendoc.telehealth import set_doctor_availability


def _doctor_user(app, email="pending-public-doctor@example.com"):
    with app.app_context():
        return get_db().execute(
            "SELECT * FROM users WHERE email_normalized=?",
            (email,),
        ).fetchone()


def _prepare_pending_doctor(app, client, email="pending-public-doctor@example.com"):
    register_web(client, "doctor", email, "Pending Public Doctor")
    with app.app_context():
        db = get_db()
        doctor = db.execute(
            "SELECT * FROM users WHERE email_normalized=?",
            (email,),
        ).fetchone()
        upsert_provider_profile(
            doctor,
            {
                "specialty": "General Medicine",
                "qualifications": "MBBS",
                "license_identifier": "PENDING-PUBLIC-TEST",
                "organization": "Pending Public Clinic",
                "city": "Kalyani",
                "state": "West Bengal",
            },
        )
        mark_email_verified(doctor["id"], email)
        db.commit()
        return int(doctor["id"])


def test_pending_provider_cannot_use_public_operational_capabilities(tmp_path):
    app, client = make_client(tmp_path)
    doctor_id = _prepare_pending_doctor(app, client)

    with app.app_context():
        app.config["PUBLIC_RELEASE_REQUIRED"] = True
        doctor = get_db().execute("SELECT * FROM users WHERE id=?", (doctor_id,)).fetchone()

        with pytest.raises(PermissionError, match="Provider verification is required"):
            set_doctor_availability(
                doctor,
                {"status": "available", "accepts_chat": True},
            )

        create_schedule(
            doctor,
            {
                "weekday": 1,
                "start_time": "09:00",
                "end_time": "12:00",
                "slot_minutes": 30,
            },
        )
        profile = get_provider_profile_for_user(doctor["id"])
        assert profile is not None
        assert get_db().execute(
            "SELECT id FROM provider_schedules WHERE provider_profile_id=?",
            (profile["id"],),
        ).fetchone() is not None
        assert available_slots(profile["id"], "2026-12-15") == []

        with pytest.raises(PermissionError, match="Provider verification is required"):
            create_staff_task(
                doctor,
                {
                    "task_type": "follow_up",
                    "title": "Blocked until verified",
                },
            )

        with pytest.raises(PermissionError, match="Provider verification is required"):
            list_provider_booking_handoffs(doctor)


def test_verified_provider_can_use_public_availability_and_schedule(tmp_path):
    app, client = make_client(tmp_path)
    email = "verified-public-doctor@example.com"
    register_web(client, "doctor", email, "Verified Public Doctor")

    with app.app_context():
        db = get_db()
        doctor = db.execute(
            "SELECT * FROM users WHERE email_normalized=?",
            (email,),
        ).fetchone()
        upsert_provider_profile(
            doctor,
            {
                "specialty": "General Medicine",
                "qualifications": "MBBS",
                "license_identifier": "VERIFIED-PUBLIC-TEST",
                "organization": "Verified Public Clinic",
                "city": "Kalyani",
                "state": "West Bengal",
            },
        )
        db.execute(
            "UPDATE provider_profiles SET verification_status='verified' WHERE user_id=?",
            (doctor["id"],),
        )
        mark_email_verified(doctor["id"], email)
        db.commit()
        app.config["PUBLIC_RELEASE_REQUIRED"] = True

        availability = set_doctor_availability(
            doctor,
            {"status": "available", "accepts_chat": True},
        )
        assert availability["status"] == "available"

        create_schedule(
            doctor,
            {
                "weekday": 1,
                "start_time": "09:00",
                "end_time": "12:00",
                "slot_minutes": 30,
            },
        )
        row = db.execute(
            """
            SELECT id FROM provider_schedules
            WHERE provider_profile_id=(SELECT id FROM provider_profiles WHERE user_id=?)
            """,
            (doctor["id"],),
        ).fetchone()
        assert row is not None


def test_pending_provider_cannot_change_appointment_status_in_public_mode(tmp_path):
    app, client = make_client(tmp_path)
    doctor_email = "pending-status-doctor@example.com"
    doctor_id = _prepare_pending_doctor(app, client, doctor_email)

    client.get("/logout", follow_redirects=False)
    patient_email = "pending-status-patient@example.com"
    register_web(client, "patient", patient_email, "Pending Status Patient")

    with app.app_context():
        db = get_db()
        patient = db.execute(
            "SELECT * FROM users WHERE email_normalized=?",
            (patient_email,),
        ).fetchone()
        stamp = now_iso()
        appointment_id = db.execute(
            """
            INSERT INTO appointments
            (patient_id,provider_id,provider_name,specialty,scheduled_for,reason,status,created_at,updated_at)
            VALUES (?,?,?,?,?,?, 'requested',?,?)
            """,
            (
                patient["id"],
                doctor_id,
                "Pending Public Clinic",
                "General Medicine",
                "2026-12-15T10:00",
                "Verification gate test",
                stamp,
                stamp,
            ),
        ).lastrowid
        mark_email_verified(doctor_id, doctor_email)
        db.commit()
        app.config["PUBLIC_RELEASE_REQUIRED"] = True

    login = client.post(
        "/login/doctor",
        data={
            "csrf_token": client.get("/login/doctor").get_data(as_text=True).split('name="csrf_token" value="', 1)[1].split('"', 1)[0],
            "email": doctor_email,
            "password": "StrongPass123",
        },
        follow_redirects=False,
    )
    assert login.status_code == 302

    page = client.get("/appointments")
    body = page.get_data(as_text=True)
    csrf = body.split('name="csrf_token" value="', 1)[1].split('"', 1)[0]
    response = client.post(
        f"/appointments/{appointment_id}/status",
        data={"csrf_token": csrf, "status": "confirmed"},
        follow_redirects=False,
    )
    assert response.status_code == 403

    with app.app_context():
        row = get_db().execute(
            "SELECT status FROM appointments WHERE id=?",
            (appointment_id,),
        ).fetchone()
        assert row["status"] == "requested"


def test_pending_pharmacy_cannot_read_assigned_orders_in_public_mode(tmp_path):
    app, client = make_client(tmp_path)
    email = "pending-public-pharmacy@example.com"
    register_web(client, "pharmacy", email, "Pending Public Pharmacy")

    with app.app_context():
        db = get_db()
        pharmacy = db.execute(
            "SELECT * FROM users WHERE email_normalized=?",
            (email,),
        ).fetchone()
        upsert_provider_profile(
            pharmacy,
            {
                "organization": "Pending Public Pharmacy",
                "city": "Kalyani",
                "state": "West Bengal",
            },
        )
        mark_email_verified(pharmacy["id"], email)
        db.commit()
        app.config["PUBLIC_RELEASE_REQUIRED"] = True

        with pytest.raises(PermissionError, match="Provider verification is required"):
            list_medicine_orders(pharmacy)


def test_pending_provider_browser_is_quarantined_to_onboarding(tmp_path):
    app, client = make_client(tmp_path)
    email = "pending-browser-doctor@example.com"
    _prepare_pending_doctor(app, client, email)

    with app.app_context():
        app.config["PUBLIC_RELEASE_REQUIRED"] = True

    login = login_web(client, "doctor", email)
    assert login.status_code == 200

    dashboard = client.get("/dashboard", follow_redirects=False)
    assert dashboard.status_code == 302
    assert "/provider/profile" in dashboard.headers["Location"]

    availability = client.get("/doctor/availability", follow_redirects=False)
    assert availability.status_code == 302
    assert "/provider/profile" in availability.headers["Location"]

    profile = client.get("/provider/profile")
    assert profile.status_code == 200
    body = profile.get_data(as_text=True)
    assert "Not patient-visible yet" in body
    assert "Provider operations" not in body
    assert "Complete Verification" in body
    assert "/appointments" not in body
    assert "/doctor/availability" not in body


def test_pending_provider_api_operational_availability_is_forbidden(tmp_path):
    app, client = make_client(tmp_path)
    email = "pending-api-doctor@example.com"
    _prepare_pending_doctor(app, client, email)

    with app.app_context():
        app.config["PUBLIC_RELEASE_REQUIRED"] = True

    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongPass123"},
    )
    assert login.status_code == 200
    access = login.get_json()["access_token"]

    response = client.put(
        "/api/v1/doctor/availability",
        headers={"Authorization": f"Bearer {access}"},
        json={"status": "available", "accepts_chat": True},
    )
    assert response.status_code == 403
    assert "Provider verification is required" in response.get_json()["error"]["message"]


def test_verified_provider_browser_operational_navigation_returns(tmp_path):
    app, client = make_client(tmp_path)
    email = "verified-browser-doctor@example.com"
    register_web(client, "doctor", email, "Verified Browser Doctor")

    with app.app_context():
        db = get_db()
        doctor = db.execute(
            "SELECT * FROM users WHERE email_normalized=?",
            (email,),
        ).fetchone()
        upsert_provider_profile(
            doctor,
            {
                "specialty": "General Medicine",
                "qualifications": "MBBS",
                "license_identifier": "VERIFIED-BROWSER-TEST",
                "organization": "Verified Browser Clinic",
                "city": "Kalyani",
                "state": "West Bengal",
            },
        )
        db.execute(
            "UPDATE provider_profiles SET verification_status='verified' WHERE user_id=?",
            (doctor["id"],),
        )
        mark_email_verified(doctor["id"], email)
        db.commit()
        app.config["PUBLIC_RELEASE_REQUIRED"] = True

    login_web(client, "doctor", email)
    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    body = dashboard.get_data(as_text=True)
    assert "/appointments" in body
    assert "/doctor/availability" in body
