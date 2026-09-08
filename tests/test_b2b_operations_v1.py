from tests.test_milestone1 import login_web, make_client


def test_b2b_operations_dashboard_is_owner_only(tmp_path):
    _app, client = make_client(tmp_path)

    denied = client.get("/admin/startup/b2b-operations", follow_redirects=False)
    assert denied.status_code in {302, 401, 403}

    login_web(client, "admin", "admin@example.com", "AdminStrong123")
    page = client.get("/admin/startup/b2b-operations")
    assert page.status_code == 200
    assert b"B2B Operations" in page.data
    assert b"Partner API health" in page.data
    assert b"Privacy boundary" in page.data


def test_b2b_operations_api_is_owner_only(tmp_path):
    _app, client = make_client(tmp_path)

    denied = client.get("/api/v1/admin/startup/b2b-operations")
    assert denied.status_code in {302, 401, 403}

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "AdminStrong123"},
    )
    token = login.get_json()["token"]
    response = client.get(
        "/api/v1/admin/startup/b2b-operations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert "business_api" in payload
    assert "handoffs" in payload
    assert "audit" in payload
