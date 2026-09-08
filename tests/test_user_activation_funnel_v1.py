from datetime import datetime, timezone

from zendoc.db import get_db, now_iso
from zendoc.startup_analytics import (
    record_finder_search,
    record_product_activity,
    submit_finder_feedback,
    user_activation_funnel,
)
from tests.test_milestone1 import csrf, login_web, make_app, make_client, register_web


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def create_patient(db, email):
    now = now_iso()
    user_id = db.execute(
        """
        INSERT INTO users
        (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
        VALUES (?,?,?,?, 'patient',1,?,?)
        """,
        (email, email, email, "x", now, now),
    ).lastrowid
    return dict(db.execute("SELECT * FROM users WHERE id=?", (int(user_id),)).fetchone())


def create_verified_provider(db):
    now = now_iso()
    user_id = db.execute(
        """
        INSERT INTO users
        (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
        VALUES ('Dr Activation','activation-doctor@example.com','activation-doctor@example.com','x','doctor',1,?,?)
        """,
        (now, now),
    ).lastrowid
    profile_id = db.execute(
        """
        INSERT INTO provider_profiles
        (user_id,provider_type,specialty,qualifications,license_identifier,organization,address,city,state,
         postal_code,public_phone,verification_status,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,'verified',?,?)
        """,
        (
            user_id, "doctor", "Cardiology", "MBBS", "REG-ACTIVATION", "Activation Clinic",
            "1 Road", "Kalyani", "West Bengal", "741235", "1234567890", now, now,
        ),
    ).lastrowid
    db.commit()
    return int(profile_id)


def stage_counts(funnel):
    return {item["stage"]: item["patient_count"] for item in funnel["stages"]}


def test_activation_funnel_counts_only_observed_patient_progress(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        first = create_patient(db, "activation-first@example.com")
        second = create_patient(db, "activation-second@example.com")

        record_product_activity(first, event_type="session_login")
        first_search_id = record_finder_search(
            first,
            category="doctor",
            location="Kalyani",
            result_count=2,
            source_tiers={"zendoc_verified": 1},
        )
        record_product_activity(first, event_type="provider_view")
        record_product_activity(first, event_type="appointment_requested")
        submit_finder_feedback(
            first,
            analytics_event_id=first_search_id,
            helpful=True,
            reason_code=None,
        )

        record_product_activity(second, event_type="session_login")
        record_finder_search(
            second,
            category="hospital",
            location="Nadia",
            result_count=0,
            source_tiers={},
        )
        db.commit()

        funnel = user_activation_funnel(owner_actor(), days=30)
        counts = stage_counts(funnel)

        assert counts["registered"] == 2
        assert counts["logged_in"] == 2
        assert counts["healthcare_search"] == 2
        assert counts["useful_search"] == 1
        assert counts["provider_view"] == 1
        assert counts["appointment_requested"] == 1
        assert counts["finder_feedback"] == 1
        assert "synthetic" in funnel["truth_notice"].lower()


def test_web_registration_provider_view_and_appointment_emit_activation_events(tmp_path):
    app, client = make_client(tmp_path)
    register_web(client, "patient", "activation-web@example.com", "Activation Patient")
    login_web(client, "patient", "activation-web@example.com")

    with app.app_context():
        profile_id = create_verified_provider(get_db())

    provider_page = client.get(f"/providers/{profile_id}")
    assert provider_page.status_code == 200

    page = client.get("/appointments")
    token = csrf(page.data.decode())
    response = client.post(
        "/appointments",
        data={
            "csrf_token": token,
            "provider_name": "Dr Activation",
            "scheduled_for": "2026-09-20T10:00",
            "reason": "General consultation",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    with app.app_context():
        user_id = get_db().execute(
            "SELECT id FROM users WHERE email='activation-web@example.com'"
        ).fetchone()["id"]
        rows = get_db().execute(
            """
            SELECT event_type FROM product_analytics_events
            WHERE user_id=?
            ORDER BY id
            """,
            (int(user_id),),
        ).fetchall()
        events = [row["event_type"] for row in rows]
        assert "account_registered" in events
        assert "session_login" in events
        assert "provider_view" in events
        assert "appointment_requested" in events


def test_api_registration_login_search_and_appointment_emit_activation_events(tmp_path):
    app, client = make_client(tmp_path)

    created = client.post(
        "/api/v1/auth/register",
        json={
            "name": "API Activation",
            "email": "activation-api@example.com",
            "password": "StrongPass123",
            "role": "patient",
        },
    )
    assert created.status_code == 201

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "activation-api@example.com", "password": "StrongPass123"},
    )
    assert login.status_code == 200
    token = login.get_json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    search = client.get(
        "/api/v1/healthcare/search?category=doctor&location=Kalyani",
        headers=headers,
    )
    assert search.status_code == 200

    appointment = client.post(
        "/api/v1/appointments",
        headers=headers,
        json={
            "provider_name": "API Provider",
            "scheduled_for": "2026-09-21T10:00",
            "reason": "General consultation",
        },
    )
    assert appointment.status_code == 201

    with app.app_context():
        user_id = get_db().execute(
            "SELECT id FROM users WHERE email='activation-api@example.com'"
        ).fetchone()["id"]
        rows = get_db().execute(
            """
            SELECT event_type FROM product_analytics_events
            WHERE user_id=?
            ORDER BY id
            """,
            (int(user_id),),
        ).fetchall()
        events = [row["event_type"] for row in rows]
        assert "account_registered" in events
        assert "session_login" in events
        assert "healthcare_search" in events
        assert "appointment_requested" in events
