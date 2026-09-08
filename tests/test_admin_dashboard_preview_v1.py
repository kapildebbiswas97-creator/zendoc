from tests.test_milestone1 import make_client, register_web, login_web


def test_owner_can_preview_all_role_dashboards_without_impersonation(tmp_path):
    _app, client = make_client(tmp_path)

    login_web(client, "admin", "admin@example.com", "AdminStrong123")

    expectations = {
        "patient": b"Health command center",
        "doctor": b"Doctor workspace",
        "hospital": b"Hospital workspace",
        "pharmacy": b"Pharmacy workspace",
    }

    for role, expected in expectations.items():
        response = client.get(f"/admin/dashboard-preview/{role}")
        assert response.status_code == 200
        assert expected in response.data
        assert b"Owner QA preview" in response.data
        assert b"no role impersonation" in response.data
        assert b"Back to Admin" in response.data


def test_dashboard_preview_is_owner_only(tmp_path):
    _app, client = make_client(tmp_path)

    denied = client.get("/admin/dashboard-preview/patient", follow_redirects=False)
    assert denied.status_code in {302, 401, 403}

    register_web(client, "patient", "ordinary-preview@example.com", "Ordinary Preview")
    login_web(client, "patient", "ordinary-preview@example.com")
    forbidden = client.get("/admin/dashboard-preview/doctor", follow_redirects=False)
    assert forbidden.status_code == 403


def test_dashboard_preview_rejects_unknown_role(tmp_path):
    _app, client = make_client(tmp_path)
    login_web(client, "admin", "admin@example.com", "AdminStrong123")

    response = client.get("/admin/dashboard-preview/government")
    assert response.status_code == 404


def test_owner_admin_page_exposes_access_center_without_role_bypass(tmp_path):
    _app, client = make_client(tmp_path)
    login_web(client, "admin", "admin@example.com", "AdminStrong123")

    response = client.get("/admin")
    assert response.status_code == 200
    assert b"Owner Access Center" in response.data
    assert b"All appointments" in response.data
    assert b"All records" in response.data
    assert b"Find Care" in response.data
    assert b"ZENDOC AI" in response.data
    assert b"Provider network" in response.data
    assert b"Data freshness" in response.data
    assert b"B2B operations" in response.data
    assert b"Role-specific clinical" in response.data


def test_owner_existing_read_views_remain_available(tmp_path):
    _app, client = make_client(tmp_path)
    login_web(client, "admin", "admin@example.com", "AdminStrong123")

    for path in ("/dashboard", "/appointments", "/records", "/finder", "/ai", "/notifications"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 200, path


def test_owner_preview_contains_only_owner_safe_navigation(tmp_path):
    _app, client = make_client(tmp_path)
    login_web(client, "admin", "admin@example.com", "AdminStrong123")

    for role in ("patient", "doctor", "hospital", "pharmacy"):
        response = client.get(f"/admin/dashboard-preview/{role}")
        assert response.status_code == 200
        assert b"Owner inspection" in response.data
        assert b"All appointments" in response.data
        assert b"All medical records" in response.data
        assert b"Find Care" in response.data
        assert b"ZENDOC AI" in response.data
        assert b"role-specific writes remain protected" in response.data
