from io import BytesIO

from zendoc import create_app
from zendoc.db import get_db


def make_app(tmp_path):
    return create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "zendoc-test.db"),
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "SECRET_KEY": "test-secret",
            "ADMIN_EMAIL": "admin@example.com",
            "ADMIN_PASSWORD": "AdminStrong123",
            "RATE_LIMIT_PER_MINUTE": 1000,
        }
    )


def make_client(tmp_path):
    app = make_app(tmp_path)
    return app, app.test_client()


def csrf(html):
    return html.split('name="csrf_token" value="')[1].split('"')[0]


def register_web(client, role, email, name="Test User"):
    page = client.get(f"/register/{role}")
    token = csrf(page.data.decode())
    return client.post(
        f"/register/{role}",
        data={"csrf_token": token, "name": name, "email": email, "password": "StrongPass123"},
        follow_redirects=True,
    )


def login_web(client, role, email, password="StrongPass123"):
    page = client.get(f"/login/{role}")
    token = csrf(page.data.decode())
    return client.post(
        f"/login/{role}",
        data={"csrf_token": token, "email": email, "password": password},
        follow_redirects=True,
    )


def api_token(client, email):
    client.post(
        "/api/v1/auth/register",
        json={"name": email, "email": email, "password": "StrongPass123", "role": "patient"},
    )
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongPass123", "role": "patient"},
    )
    return response.json["token"]


def test_registration_login_logout_and_password_hashing(tmp_path):
    app, client = make_client(tmp_path)
    response = register_web(client, "patient", "patient@example.com", "Patient One")
    assert response.status_code == 200
    response = login_web(client, "patient", "patient@example.com")
    assert b"Welcome, Patient One" in response.data
    response = client.get("/logout", follow_redirects=True)
    assert b"Logged out" in response.data
    with app.app_context():
        row = get_db().execute("SELECT password_hash FROM users WHERE email='patient@example.com'").fetchone()
        assert row["password_hash"] != "StrongPass123"


def test_invalid_login_fails(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "patient@example.com")
    response = login_web(client, "patient", "patient@example.com", "wrong-password")
    assert b"Email or password is incorrect." in response.data


def test_admin_route_is_protected(tmp_path):
    _app, client = make_client(tmp_path)
    response = client.get("/admin", follow_redirects=False)
    assert response.status_code == 302
    response = login_web(client, "admin", "admin@example.com", "AdminStrong123")
    assert response.status_code == 200
    assert b"Admin Dashboard" in response.data


def test_api_auth_logout_and_revocation(tmp_path):
    _app, client = make_client(tmp_path)
    token = api_token(client, "mobile@example.com")
    response = client.get("/api/v1/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    response = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    response = client.get("/api/v1/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_api_tokens_are_hashed_at_rest(tmp_path):
    app, client = make_client(tmp_path)
    token = api_token(client, "token-user@example.com")
    with app.app_context():
        row = get_db().execute("SELECT token, token_hash FROM api_tokens LIMIT 1").fetchone()
        assert row["token"] is None
        assert row["token_hash"]
        assert row["token_hash"] != token


def test_appointment_and_provider_authorization(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "patient@example.com", "Patient")
    register_web(client, "doctor", "doctor@example.com", "Doctor")
    login_web(client, "patient", "patient@example.com")
    page = client.get("/appointments")
    token = csrf(page.data.decode())
    response = client.post(
        "/appointments",
        data={
            "csrf_token": token,
            "provider_email": "doctor@example.com",
            "provider_name": "Doctor",
            "scheduled_for": "2026-09-01T10:00",
            "reason": "Follow-up",
        },
        follow_redirects=True,
    )
    assert b"Appointment saved" in response.data
    client.get("/logout")
    login_web(client, "doctor", "doctor@example.com")
    page = client.get("/appointments")
    assert b"Patient" in page.data
    token = csrf(page.data.decode())
    response = client.post(
        "/appointments/1/status",
        data={"csrf_token": token, "status": "confirmed"},
        follow_redirects=True,
    )
    assert b"Appointment status updated" in response.data


def test_patient_record_isolation_and_download(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "one@example.com", "Patient One")
    register_web(client, "patient", "two@example.com", "Patient Two")
    login_web(client, "patient", "one@example.com")
    page = client.get("/records")
    token = csrf(page.data.decode())
    response = client.post(
        "/records",
        data={
            "csrf_token": token,
            "title": "Report",
            "category": "Lab",
            "record_file": (BytesIO(b"hello report"), "report.txt"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"Record uploaded" in response.data
    assert client.get("/records/1/download").status_code == 200
    client.get("/logout")
    login_web(client, "patient", "two@example.com")
    assert client.get("/records/1/download").status_code == 403


def test_health_metric_persists(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "health@example.com")
    login_web(client, "patient", "health@example.com")
    page = client.get("/health")
    token = csrf(page.data.decode())
    response = client.post(
        "/health",
        data={"csrf_token": token, "metric_type": "weight", "metric_value": "70", "unit": "kg"},
        follow_redirects=True,
    )
    assert b"Health metric saved" in response.data
    assert b"weight" in response.data


def test_emergency_ai_uses_visible_emergency_state(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "ai@example.com")
    login_web(client, "patient", "ai@example.com")
    page = client.get("/ai")
    token = csrf(page.data.decode())
    response = client.post(
        "/ai",
        data={"csrf_token": token, "feature": "doctor", "symptoms": "chest pain"},
        follow_redirects=True,
    )
    assert b"Emergency guidance" in response.data
    assert b"Seek urgent care now" in response.data


def test_invalid_api_payload_returns_structured_error(tmp_path):
    _app, client = make_client(tmp_path)
    response = client.post("/api/v1/auth/register", json={"email": "missing@example.com"})
    assert response.status_code == 400
    assert response.json["error"]["code"] == 400


def test_missing_resource_returns_404(tmp_path):
    _app, client = make_client(tmp_path)
    response = client.get("/missing-page")
    assert response.status_code == 404
