from tests.test_milestone1 import make_client


def test_public_web_self_registration_is_patient_only(tmp_path):
    app, client = make_client(tmp_path)
    app.config["PUBLIC_RELEASE_REQUIRED"] = True

    assert client.get("/register/patient").status_code == 200
    for role in ("doctor", "hospital", "pharmacy", "government", "admin"):
        response = client.get(f"/register/{role}", follow_redirects=False)
        assert response.status_code == 403


def test_public_api_self_registration_rejects_provider_and_institution_roles(tmp_path):
    app, client = make_client(tmp_path)
    app.config["PUBLIC_RELEASE_REQUIRED"] = True

    for role in ("doctor", "hospital", "pharmacy", "government"):
        response = client.post(
            "/api/v1/auth/register",
            json={
                "name": f"Public {role}",
                "email": f"public-{role}@example.com",
                "password": "StrongPass123",
                "role": role,
                "accept_privacy": True,
                "accept_terms": True,
            },
        )
        assert response.status_code == 403
        assert "patient-only" in response.get_json()["error"]["message"]


def test_non_public_controlled_environment_preserves_provider_registration_flow(tmp_path):
    app, client = make_client(tmp_path)
    app.config["PUBLIC_RELEASE_REQUIRED"] = False

    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Pilot Doctor",
            "email": "pilot-doctor@example.com",
            "password": "StrongPass123",
            "role": "doctor",
            "accept_privacy": True,
            "accept_terms": True,
        },
    )
    assert response.status_code == 201
    assert response.get_json()["email_verification_required"] is False


def test_public_home_and_provider_login_do_not_offer_provider_self_registration(tmp_path):
    app, client = make_client(tmp_path)
    app.config["PUBLIC_RELEASE_REQUIRED"] = True

    home = client.get("/")
    assert home.status_code == 200
    home_body = home.get_data(as_text=True)
    assert "/register/patient" in home_body
    assert "/register/doctor" not in home_body
    assert "/register/hospital" not in home_body
    assert "/register/pharmacy" not in home_body
    assert "invitation-only" in home_body

    provider_login = client.get("/login/doctor")
    assert provider_login.status_code == 200
    body = provider_login.get_data(as_text=True)
    assert "/register/doctor" not in body
    assert "Provider accounts are invitation-only" in body
