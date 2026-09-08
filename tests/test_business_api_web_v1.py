from tests.test_milestone1 import login_web, make_client


def test_business_api_owner_web_routes_are_protected_and_render_command_center(tmp_path):
    _app, client = make_client(tmp_path)

    denied = client.post(
        "/admin/startup/business-api-clients",
        data={"name": "Denied", "client_type": "hospital"},
        follow_redirects=False,
    )
    assert denied.status_code in {302, 400, 401, 403}

    login_web(client, "admin", "admin@example.com", "AdminStrong123")
    page = client.get("/admin/startup")
    assert page.status_code == 200
    assert b"Create Business API client" in page.data
    assert b"There is no patient-record" in page.data
