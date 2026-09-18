from zendoc.edgecare_demo_data import DEMO_PATIENT_EMAIL, seed_edgecare_demo_data
from tests.test_milestone1 import login_web, make_app


DEMO_PASSWORD = "LocalDemoPass123!"


def _assert_demo_page(client, path: str):
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 200, f"{path} returned {response.status_code}"
    body = response.get_data(as_text=True).lower()
    assert "internal server error" not in body
    assert "404 not found" not in body
    return response


def test_dhn_virtual_demo_pages_load_without_404_or_500(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENDOC_ENV", "development")
    monkeypatch.setenv("ZENDOC_PLACES_PROVIDER", "none")
    monkeypatch.setenv("ZENDOC_LOCAL_AI_ENABLED", "false")
    monkeypatch.setenv("ZENDOC_EDGECARE_ASR_ENABLED", "false")

    app = make_app(tmp_path)
    seed_edgecare_demo_data(password=DEMO_PASSWORD, app=app)
    client = app.test_client()

    _assert_demo_page(client, "/showcase")

    logged = login_web(client, "patient", DEMO_PATIENT_EMAIL, DEMO_PASSWORD)
    assert logged.status_code == 200

    for path in (
        "/finder",
        "/appointments",
        "/agent-os",
        "/ai",
        "/health-hub",
        "/records",
        "/messages",
    ):
        _assert_demo_page(client, path)

    client.get("/logout", follow_redirects=True)
    owner_login = login_web(client, "admin", "admin@example.com", "AdminStrong123")
    assert owner_login.status_code == 200

    for path in (
        "/admin/edgecare",
        "/admin/startup",
    ):
        _assert_demo_page(client, path)
