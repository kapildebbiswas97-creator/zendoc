from datetime import datetime, timedelta, timezone


def test_first_50_api_users_can_register_login_and_open_dashboard(tmp_path):
    from tests.test_milestone1 import make_client

    _app, client = make_client(tmp_path)

    tokens = []
    for index in range(50):
        email = f"pilot-user-{index:02d}@example.com"
        registration = client.post(
            "/api/v1/auth/register",
            json={
                "name": f"Pilot User {index:02d}",
                "email": email,
                "password": "PilotStrong123",
                "role": "patient",
                "city": "Pilot City",
            },
        )
        assert registration.status_code == 201, (index, registration.get_json())

        login = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "PilotStrong123"},
        )
        assert login.status_code == 200, (index, login.get_json())
        payload = login.get_json()
        assert payload["user"]["role"] == "patient"
        tokens.append(payload["token"])

    for index, token in enumerate(tokens):
        dashboard = client.get(
            "/api/v1/dashboard",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert dashboard.status_code == 200, (index, dashboard.get_json())
        assert "stats" in dashboard.get_json()


def test_first_50_accounts_remain_isolated_during_real_user_actions(tmp_path):
    from tests.test_milestone1 import make_client

    _app, client = make_client(tmp_path)

    tokens = {}
    for index in range(50):
        email = f"isolation-user-{index:02d}@example.com"
        assert client.post(
            "/api/v1/auth/register",
            json={
                "name": f"Isolation User {index:02d}",
                "email": email,
                "password": "IsolationStrong123",
                "role": "patient",
            },
        ).status_code == 201
        login = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "IsolationStrong123"},
        )
        assert login.status_code == 200
        tokens[index] = login.get_json()["token"]

    scheduled = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")
    create = client.post(
        "/api/v1/appointments",
        json={
            "provider_name": "Pilot Provider",
            "scheduled_for": scheduled,
            "reason": "Pilot isolation check",
        },
        headers={"Authorization": f"Bearer {tokens[0]}"},
    )
    assert create.status_code == 201

    owner_view = client.get(
        "/api/v1/appointments",
        headers={"Authorization": f"Bearer {tokens[0]}"},
    )
    assert owner_view.status_code == 200
    assert len(owner_view.get_json()["appointments"]) == 1

    for index in (1, 2, 10, 25, 49):
        other_view = client.get(
            "/api/v1/appointments",
            headers={"Authorization": f"Bearer {tokens[index]}"},
        )
        assert other_view.status_code == 200
        assert other_view.get_json()["appointments"] == []


def test_duplicate_registration_cannot_create_second_identity(tmp_path):
    from tests.test_milestone1 import make_client

    _app, client = make_client(tmp_path)
    body = {
        "name": "Duplicate Pilot",
        "email": "duplicate-pilot@example.com",
        "password": "DuplicateStrong123",
        "role": "patient",
    }

    first = client.post("/api/v1/auth/register", json=body)
    second = client.post("/api/v1/auth/register", json=body)

    assert first.status_code == 201
    assert second.status_code == 409


def test_provider_and_patient_roles_cannot_cross_first_use_boundaries(tmp_path):
    from tests.test_milestone1 import make_client

    _app, client = make_client(tmp_path)

    for role, email in (
        ("patient", "pilot-patient-role@example.com"),
        ("doctor", "pilot-doctor-role@example.com"),
        ("hospital", "pilot-hospital-role@example.com"),
        ("pharmacy", "pilot-pharmacy-role@example.com"),
    ):
        registration = client.post(
            "/api/v1/auth/register",
            json={
                "name": f"Pilot {role.title()}",
                "email": email,
                "password": "RoleStrong123",
                "role": role,
            },
        )
        assert registration.status_code == 201

    doctor_login = client.post(
        "/api/v1/auth/login",
        json={"email": "pilot-doctor-role@example.com", "password": "RoleStrong123"},
    )
    patient_login = client.post(
        "/api/v1/auth/login",
        json={"email": "pilot-patient-role@example.com", "password": "RoleStrong123"},
    )
    assert doctor_login.status_code == 200
    assert patient_login.status_code == 200

    doctor_token = doctor_login.get_json()["token"]
    patient_token = patient_login.get_json()["token"]

    doctor_cannot_book = client.post(
        "/api/v1/appointments",
        json={
            "provider_name": "Another Provider",
            "scheduled_for": "2026-10-01T10:00",
            "reason": "Should be denied",
        },
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert doctor_cannot_book.status_code == 403

    patient_cannot_edit_provider = client.post(
        "/api/v1/provider/profile",
        json={"specialty": "Cardiology"},
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert patient_cannot_edit_provider.status_code == 403
