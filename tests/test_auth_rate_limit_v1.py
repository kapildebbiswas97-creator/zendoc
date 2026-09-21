from tests.test_milestone1 import csrf, make_client


def test_browser_login_is_rate_limited(tmp_path):
    app, client = make_client(tmp_path)
    app.config["AUTH_RATE_LIMIT_PER_MINUTE"] = 3

    page = client.get("/login")
    token = csrf(page.get_data(as_text=True))

    for _ in range(3):
        response = client.post(
            "/login",
            data={
                "csrf_token": token,
                "email": "missing@example.com",
                "password": "incorrect-password",
            },
        )
        assert response.status_code == 200

    blocked = client.post(
        "/login",
        data={
            "csrf_token": token,
            "email": "missing@example.com",
            "password": "incorrect-password",
        },
    )
    assert blocked.status_code == 429
    assert "Too many requests" in blocked.get_data(as_text=True)


def test_api_auth_is_rate_limited_independently_from_general_api_limit(tmp_path):
    app, client = make_client(tmp_path)
    app.config["AUTH_RATE_LIMIT_PER_MINUTE"] = 3
    app.config["RATE_LIMIT_PER_MINUTE"] = 100

    for _ in range(3):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "missing@example.com", "password": "incorrect-password"},
        )
        assert response.status_code == 401

    blocked = client.post(
        "/api/v1/auth/login",
        json={"email": "missing@example.com", "password": "incorrect-password"},
    )
    assert blocked.status_code == 429
    assert blocked.get_json()["error"]["message"] == "Too many requests"
