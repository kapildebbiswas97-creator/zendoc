from __future__ import annotations

import pytest

from zendoc.db import get_db, now_iso
from zendoc.diagnostic_service import complete_diagnostic_test
from zendoc.human_operations import create_staff_task, list_staff_tasks
from zendoc.order_service import acknowledge_order, update_order_tracking_status
from tests.test_milestone1 import csrf, login_web, make_app, register_web
from tests.test_milestone7 import headers


PASSWORD = "StrongPass123"


def _register_api(client, email, role):
    response = client.post(
        "/api/v1/auth/register",
        json={"name": role.title(), "email": email, "password": PASSWORD, "role": role},
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
        return dict(
            get_db().execute(
                "SELECT * FROM users WHERE email_normalized=?",
                (email.lower(),),
            ).fetchone()
        )


def _seed_verified_provider(app, user_id, provider_type):
    with app.app_context():
        db = get_db()
        now = now_iso()
        profile_id = db.execute(
            """
            INSERT INTO provider_profiles
            (user_id, provider_type, specialty, organization, city, verification_status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'verified', ?, ?)
            """,
            (user_id, provider_type, "General", f"{provider_type.title()} Org", "Kalyani", now, now),
        ).lastrowid
        db.commit()
        return int(profile_id)


def test_non_patient_cannot_create_appointment_api(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    doctor_token = _register_api(client, "doctor-booker@example.com", "doctor")

    response = client.post(
        "/api/v1/appointments",
        json={"provider_name": "Someone Else", "scheduled_for": "2026-12-10T10:00", "reason": "test"},
        headers=headers(doctor_token),
    )
    assert response.status_code == 403


def test_unverified_provider_slots_are_not_discoverable(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    patient_token = _register_api(client, "slot-patient@example.com", "patient")
    _register_api(client, "pending-doctor@example.com", "doctor")
    doctor = _user(app, "pending-doctor@example.com")

    with app.app_context():
        db = get_db()
        now = now_iso()
        profile_id = db.execute(
            """
            INSERT INTO provider_profiles
            (user_id, provider_type, specialty, organization, city, verification_status, created_at, updated_at)
            VALUES (?, 'doctor', 'General', 'Pending Clinic', 'Kalyani', 'pending', ?, ?)
            """,
            (doctor["id"], now, now),
        ).lastrowid
        db.commit()

    response = client.get(
        f"/api/v1/providers/{profile_id}/slots?date=2026-12-10",
        headers=headers(patient_token),
    )
    assert response.status_code == 404


def test_doctor_cannot_change_another_doctors_appointment(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "appointment-patient@example.com", "Appointment Patient")
    register_web(client, "doctor", "doctor-a@example.com", "Doctor A")
    register_web(client, "doctor", "doctor-b@example.com", "Doctor B")

    patient = _user(app, "appointment-patient@example.com")
    doctor_a = _user(app, "doctor-a@example.com")

    with app.app_context():
        db = get_db()
        appointment_id = db.execute(
            """
            INSERT INTO appointments
            (patient_id, provider_id, provider_name, scheduled_for, reason, status, created_at, updated_at)
            VALUES (?, ?, 'Doctor A', '2026-12-10T10:00', 'Follow up', 'requested', ?, ?)
            """,
            (patient["id"], doctor_a["id"], now_iso(), now_iso()),
        ).lastrowid
        db.commit()

    login_web(client, "doctor", "doctor-b@example.com")
    page = client.get("/appointments")
    token = csrf(page.data.decode())
    response = client.post(
        f"/appointments/{appointment_id}/status",
        data={"csrf_token": token, "status": "confirmed"},
        follow_redirects=False,
    )
    assert response.status_code == 403

    with app.app_context():
        status = get_db().execute("SELECT status FROM appointments WHERE id=?", (appointment_id,)).fetchone()["status"]
        assert status == "requested"


def test_provider_staff_task_requires_real_patient_relationship(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    _register_api(client, "ops-doctor@example.com", "doctor")
    _register_api(client, "ops-patient@example.com", "patient")
    doctor = _user(app, "ops-doctor@example.com")
    patient = _user(app, "ops-patient@example.com")

    with app.app_context():
        with pytest.raises(PermissionError):
            create_staff_task(
                doctor,
                {
                    "task_type": "follow_up",
                    "title": "Call patient",
                    "patient_id": patient["id"],
                },
            )


def test_provider_staff_task_allowed_after_appointment_relationship(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    _register_api(client, "linked-doctor@example.com", "doctor")
    _register_api(client, "linked-patient@example.com", "patient")
    doctor = _user(app, "linked-doctor@example.com")
    patient = _user(app, "linked-patient@example.com")

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO appointments
            (patient_id, provider_id, provider_name, scheduled_for, reason, status, created_at, updated_at)
            VALUES (?, ?, 'Linked Doctor', '2026-12-11T10:00', 'Review', 'confirmed', ?, ?)
            """,
            (patient["id"], doctor["id"], now_iso(), now_iso()),
        )
        db.commit()
        task = create_staff_task(
            doctor,
            {"task_type": "follow_up", "title": "Follow-up call", "patient_id": patient["id"]},
        )
        assert task["patient_id"] == patient["id"]


def test_fake_admin_cannot_read_all_staff_tasks(tmp_path):
    app = make_app(tmp_path)
    fake_admin = {
        "id": 999999,
        "role": "admin",
        "email": "fake-admin@example.com",
        "email_normalized": "fake-admin@example.com",
        "active": 1,
    }
    with app.app_context():
        with pytest.raises(PermissionError):
            list_staff_tasks(fake_admin)


def test_owner_cannot_impersonate_pharmacy_inventory_writer(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    owner_login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "AdminStrong123"},
    )
    assert owner_login.status_code == 200
    owner_token = owner_login.get_json()["token"]

    response = client.post(
        "/api/v1/connected-care/inventory",
        json={"sku_id": 1, "quantity": 5, "price_inr": 10},
        headers=headers(owner_token),
    )
    assert response.status_code == 403


def test_wrong_pharmacy_cannot_acknowledge_or_track_order(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    _register_api(client, "order-patient@example.com", "patient")
    _register_api(client, "pharmacy-a@example.com", "pharmacy")
    _register_api(client, "pharmacy-b@example.com", "pharmacy")
    patient = _user(app, "order-patient@example.com")
    pharmacy_a = _user(app, "pharmacy-a@example.com")
    pharmacy_b = _user(app, "pharmacy-b@example.com")

    with app.app_context():
        db = get_db()
        order_id = db.execute(
            """
            INSERT INTO medicine_orders
            (patient_id, ordered_by, pharmacy_id, items_json, delivery_address, status, tracking_status, created_at, updated_at)
            VALUES (?, ?, ?, '[]', 'Test Address', 'pending', 'SUBMITTED', ?, ?)
            """,
            (patient["id"], patient["id"], pharmacy_a["id"], now_iso(), now_iso()),
        ).lastrowid
        db.commit()

        with pytest.raises(PermissionError):
            acknowledge_order(pharmacy_b, order_id, "accept")
        with pytest.raises(PermissionError):
            update_order_tracking_status(pharmacy_b, order_id, "ACCEPTED")


def test_unassigned_lab_cannot_complete_diagnostic_booking(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    _register_api(client, "diag-patient@example.com", "patient")
    _register_api(client, "lab-a@example.com", "hospital")
    _register_api(client, "lab-b@example.com", "hospital")
    patient = _user(app, "diag-patient@example.com")
    lab_a = _user(app, "lab-a@example.com")
    lab_b = _user(app, "lab-b@example.com")
    _seed_verified_provider(app, lab_a["id"], "diagnostic_centre")
    _seed_verified_provider(app, lab_b["id"], "diagnostic_centre")

    with app.app_context():
        db = get_db()
        test_id = db.execute(
            """
            INSERT INTO diagnostic_catalog
            (code, name, category, fasting_required, sample_type, tat_hours, standard_price_inr, created_at)
            VALUES ('SEC-T1', 'Security Test', 'general', 0, 'blood', 24, 100, ?)
            """,
            (now_iso(),),
        ).lastrowid
        booking_id = db.execute(
            """
            INSERT INTO diagnostic_bookings
            (booking_uid, patient_id, booked_by, lab_id, test_id, collection_type, scheduled_date, address, status, price_inr, created_at, updated_at)
            VALUES ('diag-sec-1', ?, ?, ?, ?, 'lab_visit', '2026-12-12', 'Lab A', 'requested', 100, ?, ?)
            """,
            (patient["id"], patient["id"], lab_a["id"], test_id, now_iso(), now_iso()),
        ).lastrowid
        db.commit()

        with pytest.raises(PermissionError):
            complete_diagnostic_test(lab_b, booking_id, "Completed")


def test_fake_admin_cannot_globally_read_telehealth_consultations(tmp_path):
    app = make_app(tmp_path)
    fake_admin = {
        "id": 999998,
        "role": "admin",
        "email": "fake-tele-admin@example.com",
        "email_normalized": "fake-tele-admin@example.com",
        "active": 1,
    }
    from zendoc.telehealth import list_consultations

    with app.app_context():
        with pytest.raises(PermissionError):
            list_consultations(fake_admin)


def test_fake_admin_cannot_read_global_dashboard_stats(tmp_path):
    app = make_app(tmp_path)
    from zendoc.routes import stats_for

    fake_admin = {
        "id": 999997,
        "role": "admin",
        "email": "fake-stats-admin@example.com",
        "email_normalized": "fake-stats-admin@example.com",
        "active": 1,
    }
    with app.app_context():
        with pytest.raises(PermissionError):
            stats_for(fake_admin)


def test_provider_cannot_directly_assign_global_staff_account(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    _register_api(client, "assign-doctor@example.com", "doctor")
    _register_api(client, "assign-patient@example.com", "patient")
    _register_api(client, "assign-staff@example.com", "hospital")
    doctor = _user(app, "assign-doctor@example.com")
    patient = _user(app, "assign-patient@example.com")
    staff_user = _user(app, "assign-staff@example.com")

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO appointments
            (patient_id, provider_id, provider_name, scheduled_for, reason, status, created_at, updated_at)
            VALUES (?, ?, 'Assign Doctor', '2026-12-15T10:00', 'Review', 'confirmed', ?, ?)
            """,
            (patient["id"], doctor["id"], now_iso(), now_iso()),
        )
        db.execute(
            """
            INSERT INTO staff_profiles
            (user_id, staff_type, service_area, status, verified, created_at, updated_at)
            VALUES (?, 'care_coordinator', 'Kalyani', 'available', 1, ?, ?)
            """,
            (staff_user["id"], now_iso(), now_iso()),
        )
        db.commit()

        with pytest.raises(PermissionError):
            create_staff_task(
                doctor,
                {
                    "task_type": "follow_up",
                    "title": "Assign globally",
                    "patient_id": patient["id"],
                    "assigned_staff_id": staff_user["id"],
                },
            )
