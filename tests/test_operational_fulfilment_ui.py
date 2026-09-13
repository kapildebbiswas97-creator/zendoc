from zendoc.db import get_db, now_iso
from tests.test_milestone1 import make_app


def _user(db, name, email, role):
    now = now_iso()
    return int(
        db.execute(
            """
            INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
            VALUES (?,?,?,?,?,1,?,?)
            """,
            (name, email, email, "test-hash", role, now, now),
        ).lastrowid
    )


def _verify_provider(db, provider_id, provider_type):
    now = now_iso()
    db.execute(
        """
        INSERT INTO provider_profiles
        (user_id,provider_type,verification_status,created_at,updated_at)
        VALUES (?,?,?,?,?)
        """,
        (provider_id, provider_type, "verified", now, now),
    )
    db.commit()


def _login_session(client, user_id, role):
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["role"] = role
        session["csrf_token"] = "test-csrf"


def test_patient_can_open_fulfilment_console(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    with app.app_context():
        patient_id = _user(get_db(), "Patient", "ui-patient@example.com", "patient")
        get_db().commit()
    _login_session(client, patient_id, "patient")
    response = client.get("/operations/fulfilment")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Diagnostics &amp; home-health fulfilment" in body
    assert "My diagnostic bookings" in body
    assert "My home-health requests" in body


def test_verified_hospital_can_publish_capability_from_console(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    with app.app_context():
        db = get_db()
        provider_id = _user(db, "Hospital", "ui-hospital@example.com", "hospital")
        _verify_provider(db, provider_id, "hospital")
    _login_session(client, provider_id, "hospital")

    response = client.post(
        "/operations/fulfilment",
        data={
            "csrf_token": "test-csrf",
            "action": "home_capability",
            "service_type": "physiotherapy",
            "active": "1",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Home-health capability updated" in response.get_data(as_text=True)
    with app.app_context():
        row = get_db().execute(
            "SELECT active FROM home_health_provider_services WHERE provider_id=? AND service_type='physiotherapy'",
            (provider_id,),
        ).fetchone()
        assert row is not None and int(row["active"]) == 1


def test_console_post_requires_csrf(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    with app.app_context():
        patient_id = _user(get_db(), "Patient", "ui-csrf@example.com", "patient")
        get_db().commit()
    _login_session(client, patient_id, "patient")
    response = client.post(
        "/operations/fulfilment",
        data={"action": "home_assign", "request_id": "1", "provider_id": "1"},
    )
    assert response.status_code == 400
