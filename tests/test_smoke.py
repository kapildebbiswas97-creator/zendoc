from tests.test_milestone1 import api_token, make_client, register_web, login_web, csrf


def test_existing_smoke_web_and_api_flows(tmp_path):
    _app, client = make_client(tmp_path)
    assert client.get("/").status_code == 200
    register_web(client, "patient", "smoke@example.com", "Smoke Patient")
    login = login_web(client, "patient", "smoke@example.com")
    assert b"Welcome, Smoke Patient" in login.data
    page = client.get("/ai")
    token = csrf(page.data.decode())
    response = client.post(
        "/ai",
        data={"csrf_token": token, "feature": "doctor", "symptoms": "fever and cough"},
        follow_redirects=True,
    )
    assert b"Possible respiratory infection" in response.data

    token = api_token(client, "smoke-mobile@example.com")
    response = client.get("/api/v1/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
