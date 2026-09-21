from datetime import datetime, timedelta, timezone

from tests.test_milestone1 import csrf, login_web, make_client, register_web
from zendoc.db import get_db


def _future_weekday(days_ahead=14):
    target = datetime.now(timezone.utc).date() + timedelta(days=days_ahead)
    return target, target.weekday()


def test_submission_search_profile_slot_booking_careloop_flow(tmp_path, monkeypatch):
    """Prove the competition demo's patient care path as one connected flow.

    Search discovers only a verified ZENDOC provider, the provider profile exposes
    published availability, and selecting that slot creates both the appointment
    and its internal CareLoop action. External/public listings are intentionally
    not used for connected booking.
    """

    monkeypatch.setenv("ZENDOC_PLACES_PROVIDER", "none")
    app, client = make_client(tmp_path)
    target_date, weekday = _future_weekday()
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

    with app.app_context():
        db = get_db()
        doctor_id = db.execute(
            """
            INSERT INTO users
            (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
            VALUES ('Dr Demo Sen','demo-doctor@example.test','demo-doctor@example.test','unused','doctor',1,?,?)
            """,
            (stamp, stamp),
        ).lastrowid
        profile_id = db.execute(
            """
            INSERT INTO provider_profiles
            (user_id,provider_type,specialty,organization,address,city,state,postal_code,
             verification_status,created_at,updated_at)
            VALUES (?,'doctor','Cardiology','ZENDOC Demo Heart Clinic','Station Road','Kalyani',
                    'West Bengal','741235','verified',?,?)
            """,
            (doctor_id, stamp, stamp),
        ).lastrowid
        db.execute(
            """
            INSERT INTO provider_schedules
            (provider_profile_id,weekday,start_time,end_time,slot_minutes,active,
             organization_id,organization_location_id,created_at,updated_at)
            VALUES (?,?,?,?,30,1,NULL,NULL,?,?)
            """,
            (profile_id, weekday, "09:00", "10:00", stamp, stamp),
        )
        db.commit()

    register_web(client, "patient", "submission-patient@example.com", "Submission Patient")
    login_web(client, "patient", "submission-patient@example.com")

    # 1) Search finds the verified provider and exposes the profile CTA.
    search = client.get("/universal-search?q=Kalyani&category=all")
    assert search.status_code == 200
    assert b"Dr Demo Sen" in search.data
    assert b"Cardiology" in search.data
    assert b"View profile &amp; availability" in search.data
    assert f'href="/providers/{profile_id}"'.encode() in search.data

    # 2) Profile renders provider-published future availability.
    detail = client.get(f"/providers/{profile_id}?date={target_date.isoformat()}")
    assert detail.status_code == 200
    assert b"Choose a date and time" in detail.data
    assert b"Request appointment" in detail.data
    expected_slot = f"{target_date.isoformat()}T09:00"
    assert expected_slot.encode() in detail.data

    # 3) Booking the displayed slot creates the appointment through the same
    # form route used by the real UI.
    token = csrf(detail.data.decode())
    booked = client.post(
        "/appointments",
        data={
            "csrf_token": token,
            "provider_profile_id": str(profile_id),
            "scheduled_for": expected_slot,
            "reason": "Competition demo cardiology consultation",
        },
        follow_redirects=False,
    )
    assert booked.status_code == 302
    assert "requested=1" in booked.headers["Location"]

    # 4) Persisted truth: appointment is linked to the registered provider and
    # CareLoop created a staged internal action; nothing external is fabricated.
    with app.app_context():
        db = get_db()
        appointment = db.execute(
            "SELECT * FROM appointments ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert appointment is not None
        assert int(appointment["provider_profile_id"]) == int(profile_id)
        assert int(appointment["provider_id"]) == int(doctor_id)
        assert appointment["scheduled_for"][:16] == expected_slot
        assert appointment["status"] == "requested"

        action = db.execute(
            "SELECT * FROM care_actions WHERE service_ref=?",
            (f"zendoc_appointment:{appointment['id']}",),
        ).fetchone()
        assert action is not None
        assert action["status"] == "STAGED"
        assert action["provider_name"] in {"Dr Demo Sen", "ZENDOC Demo Heart Clinic"}
