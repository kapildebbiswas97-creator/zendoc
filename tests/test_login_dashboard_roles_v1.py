from tests.test_milestone1 import make_client, register_web, login_web


ROLE_EXPECTATIONS = {
    "patient": b"Health command center",
    "doctor": b"Doctor workspace",
    "hospital": b"Hospital workspace",
    "pharmacy": b"Pharmacy workspace",
}


def test_registered_roles_can_login_and_render_role_dashboard(tmp_path):
    _app, client = make_client(tmp_path)

    for role, expected in ROLE_EXPECTATIONS.items():
        email = f"{role}-dashboard@example.com"
        name = f"{role.title()} Dashboard User"

        register_web(client, role, email, name)
        login_web(client, role, email)

        response = client.get("/dashboard", follow_redirects=True)
        assert response.status_code == 200
        assert expected in response.data
        assert b"ZENDOC" in response.data

        logout = client.get("/logout", follow_redirects=True)
        assert logout.status_code == 200
        assert b"Logged out" in logout.data


def test_login_redirect_lands_on_dashboard_not_login_loop(tmp_path):
    _app, client = make_client(tmp_path)

    register_web(client, "patient", "loop-check@example.com", "Loop Check")
    page = client.get("/login/patient")
    token = page.data.decode().split('name="csrf_token" value="')[1].split('"')[0]
    response = client.post(
        "/login/patient",
        data={
            "csrf_token": token,
            "email": "loop-check@example.com",
            "password": "StrongPass123",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")

    dashboard = client.get(response.headers["Location"], follow_redirects=False)
    assert dashboard.status_code == 200
    assert b"Health command center" in dashboard.data
