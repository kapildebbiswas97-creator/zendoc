from zendoc import create_app
from tests.test_milestone1 import csrf, register_web
from zendoc.auth import INVALID_CREDENTIALS_MESSAGE
from zendoc.db import get_db
from werkzeug.security import generate_password_hash


def make_auth_client(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "zendoc-auth-test.db"),
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "SECRET_KEY": "test-secret",
            "ADMIN_EMAIL": "owner@zendoc.local",
            "ADMIN_PASSWORD": "OwnerPassword123!",
            "RATE_LIMIT_PER_MINUTE": 1000,
        }
    )
    return app, app.test_client()


def test_universal_login_patient_doctor_pharmacy_and_owner(tmp_path):
    app, client = make_auth_client(tmp_path)

    with app.app_context():
        db = get_db()
        # Seed existing accounts with different roles
        db.execute(
            """
            INSERT INTO users (name, email, email_normalized, password_hash, role, active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 1, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
            """,
            ("Patient User", "patient@example.com", "patient@example.com", generate_password_hash("PatientPass123!"), "patient"),
        )
        db.execute(
            """
            INSERT INTO users (name, email, email_normalized, password_hash, role, active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 1, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
            """,
            ("Doctor User", "doctor@example.com", "doctor@example.com", generate_password_hash("DoctorPass123!"), "doctor"),
        )
        db.execute(
            """
            INSERT INTO users (name, email, email_normalized, password_hash, role, active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 1, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
            """,
            ("Pharmacy User", "pharmacy@example.com", "pharmacy@example.com", generate_password_hash("PharmacyPass123!"), "pharmacy"),
        )
        db.commit()

    # 1. Patient signs in at universal /login
    page = client.get("/login")
    token = csrf(page.data.decode())
    res = client.post(
        "/login",
        data={"csrf_token": token, "email": "  Patient@Example.com  ", "password": "PatientPass123!"},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Welcome, Patient User" in res.data
    with client.session_transaction() as sess:
        assert sess["role"] == "patient"
    client.get("/logout")

    # 2. Doctor signs in at universal /login (and at /login/patient)
    page = client.get("/login/patient")
    token = csrf(page.data.decode())
    res = client.post(
        "/login/patient",
        data={"csrf_token": token, "email": "doctor@example.com", "password": "DoctorPass123!"},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Welcome, Doctor User" in res.data
    with client.session_transaction() as sess:
        assert sess["role"] == "doctor"
    client.get("/logout")

    # 3. Pharmacy user signs in at /login
    page = client.get("/login")
    token = csrf(page.data.decode())
    res = client.post(
        "/login",
        data={"csrf_token": token, "email": "pharmacy@example.com", "password": "PharmacyPass123!"},
        follow_redirects=True,
    )
    assert res.status_code == 200
    with client.session_transaction() as sess:
        assert sess["role"] == "pharmacy"
    client.get("/logout")

    # 4. Configured Owner signs in through ordinary /login
    page = client.get("/login")
    token = csrf(page.data.decode())
    res = client.post(
        "/login",
        data={"csrf_token": token, "email": "owner@zendoc.local", "password": "OwnerPassword123!"},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Admin Dashboard" in res.data
    with client.session_transaction() as sess:
        assert sess["role"] == "admin"
    admin_page = client.get("/admin")
    assert admin_page.status_code == 200
    client.get("/logout")

    # 5. Wrong password fails securely
    page = client.get("/login")
    token = csrf(page.data.decode())
    res = client.post(
        "/login",
        data={"csrf_token": token, "email": "patient@example.com", "password": "WrongPassword!"},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert INVALID_CREDENTIALS_MESSAGE.encode() in res.data
    with client.session_transaction() as sess:
        assert "user_id" not in sess

    # 6. Patient cannot access /admin
    page = client.get("/login")
    token = csrf(page.data.decode())
    client.post(
        "/login",
        data={"csrf_token": token, "email": "patient@example.com", "password": "PatientPass123!"},
        follow_redirects=True,
    )
    forbidden = client.get("/admin")
    assert forbidden.status_code == 403


def test_api_login_derives_role_from_persisted_account(tmp_path):
    app, client = make_auth_client(tmp_path)
    register_web(client, "doctor", "doctor-api@example.com", name="API Doctor")

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": " DOCTOR-API@EXAMPLE.COM ",
            "password": "StrongPass123",
            # Legacy clients may send this, but it cannot change auth.
            "role": "patient",
        },
    )
    assert response.status_code == 200
    assert response.json["user"]["role"] == "doctor"

    owner_response = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@zendoc.local", "password": "OwnerPassword123!"},
    )
    assert owner_response.status_code == 200
    assert owner_response.json["user"]["role"] == "admin"


def test_browser_auth_keeps_csrf_rotation_role_security_and_idle_expiry(tmp_path):
    app, client = make_auth_client(tmp_path)
    register_web(client, "patient", "security@example.com", name="Security Patient")

    page = client.get("/login")
    form_token = csrf(page.data.decode())
    with client.session_transaction() as session_state:
        session_state["session_nonce"] = "attacker-controlled"
        old_csrf = session_state["csrf_token"]

    missing_csrf = client.post(
        "/login",
        data={"email": "security@example.com", "password": "StrongPass123"},
    )
    assert missing_csrf.status_code == 400

    logged_in = client.post(
        "/login",
        data={
            "csrf_token": form_token,
            "email": "security@example.com",
            "password": "StrongPass123",
        },
        follow_redirects=True,
    )
    assert logged_in.status_code == 200
    with client.session_transaction() as session_state:
        assert session_state["session_nonce"] != "attacker-controlled"
        assert session_state["csrf_token"] != old_csrf
        session_state["role"] = "admin"

    assert client.get("/admin").status_code == 403
    with client.session_transaction() as session_state:
        session_state["role"] = "patient"
        session_state["last_activity_at"] = "2020-01-01T00:00:00+00:00"

    expired = client.get("/dashboard", follow_redirects=True)
    assert expired.status_code == 200
    assert b"Your session expired. Please log in again." in expired.data
    assert b"Sign in to ZENDOC" in expired.data
    with client.session_transaction() as session_state:
        assert "user_id" not in session_state
