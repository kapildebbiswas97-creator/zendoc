from tests.test_milestone1 import login_web, make_client


def test_startup_command_center_is_owner_only(tmp_path):
    _app, client = make_client(tmp_path)

    denied = client.get("/admin/startup", follow_redirects=False)
    assert denied.status_code in {302, 401, 403}

    logged = login_web(client, "admin", "admin@example.com", "AdminStrong123")
    assert logged.status_code == 200

    allowed = client.get("/admin/startup")
    assert allowed.status_code == 200
    assert b"Startup Command Center" in allowed.data
    assert b"India State/UT coverage status" in allowed.data
