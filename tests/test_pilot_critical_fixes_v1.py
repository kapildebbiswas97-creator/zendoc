from datetime import datetime, timedelta, timezone

import pytest

from tests.test_milestone1 import csrf, login_web, make_app, make_client, register_web
from zendoc.db import get_db, now_iso
from zendoc.provider_service import available_slots, create_schedule


def _verified_doctor(db, *, active=1):
    now = now_iso()
    user_id = db.execute(
        """
        INSERT INTO users
        (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
        VALUES ('Pilot Doctor','pilot-doctor@example.com','pilot-doctor@example.com','x','doctor',?, ?, ?)
        """,
        (active, now, now),
    ).lastrowid
    profile_id = db.execute(
        """
        INSERT INTO provider_profiles
        (user_id,provider_type,specialty,qualifications,license_identifier,organization,address,city,state,
         postal_code,public_phone,verification_status,created_at,updated_at)
        VALUES (?, 'doctor','Cardiology','MBBS','PILOT-1','Pilot Clinic','1 Road','Kalyani','West Bengal',
                '741235','1234567890','verified',?,?)
        """,
        (user_id, now, now),
    ).lastrowid
    db.commit()
    return int(user_id), int(profile_id)


def test_invalid_schedule_input_is_rejected_without_a_database_row(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        _user_id, profile_id = _verified_doctor(get_db())
        doctor = dict(get_db().execute("SELECT * FROM users WHERE id=?", (_user_id,)).fetchone())
        with pytest.raises(ValueError, match="Weekday"):
            create_schedule(doctor, {"weekday": "monday", "start_time": "09:00", "end_time": "10:00"})
        with pytest.raises(ValueError, match="Schedule end"):
            create_schedule(doctor, {"weekday": 1, "start_time": "9am", "end_time": "10:00"})
        assert get_db().execute(
            "SELECT COUNT(*) c FROM provider_schedules WHERE provider_profile_id=?", (profile_id,)
        ).fetchone()["c"] == 0


def test_available_slots_skip_corrupt_legacy_schedule_and_dedupe_overlap(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        user_id, profile_id = _verified_doctor(get_db())
        db = get_db()
        now = now_iso()
        target = datetime.now(timezone.utc).date() + timedelta(days=7)
        weekday = target.weekday()
        db.execute(
            """
            INSERT INTO provider_schedules (provider_profile_id,weekday,start_time,end_time,slot_minutes,active,created_at,updated_at)
            VALUES (?, ?, '09:00','10:00',30,1,?,?)
            """,
            (profile_id, weekday, now, now),
        )
        db.execute(
            """
            INSERT INTO provider_schedules (provider_profile_id,weekday,start_time,end_time,slot_minutes,active,created_at,updated_at)
            VALUES (?, ?, '09:30','10:30',30,1,?,?)
            """,
            (profile_id, weekday, now, now),
        )
        db.execute(
            """
            INSERT INTO provider_schedules (provider_profile_id,weekday,start_time,end_time,slot_minutes,active,created_at,updated_at)
            VALUES (?, ?, 'bad','10:30',30,1,?,?)
            """,
            (profile_id, weekday, now, now),
        )
        db.commit()
        slots = available_slots(profile_id, target.isoformat())
        assert slots == sorted(set(slots))
        assert len(slots) == 3
        assert all(item.startswith(target.isoformat()) for item in slots)
        assert db.execute("SELECT active FROM users WHERE id=?", (user_id,)).fetchone()["active"] == 1


def test_manual_web_request_does_not_link_an_arbitrary_patient_email(tmp_path):
    app, client = make_client(tmp_path)
    register_web(client, "patient", "requester@example.com", "Requester")
    register_web(client, "patient", "other-patient@example.com", "Other Patient")
    login_web(client, "patient", "requester@example.com")
    page = client.get("/appointments")
    response = client.post(
        "/appointments",
        data={
            "csrf_token": csrf(page.data.decode()),
            "provider_name": "External Clinic",
            "provider_email": "other-patient@example.com",
            "scheduled_for": "2099-01-01T10:00",
            "reason": "Pilot request",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        row = get_db().execute(
            "SELECT provider_id,provider_name FROM appointments ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row["provider_id"] is None
        assert row["provider_name"] == "External Clinic"


def test_ai_page_exposes_reviewable_voice_input_fallback(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "voice-patient@example.com", "Voice Patient")
    login_web(client, "patient", "voice-patient@example.com")
    page = client.get("/ai")
    assert page.status_code == 200
    assert b"voice-input-toggle" in page.data
    assert b"never sent until you press Send" in page.data

