from zendoc import create_app
from tests.test_milestone1 import csrf


def make_client(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "edgecare-admin.db"),
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "SECRET_KEY": "edgecare-admin-test-secret",
            "ADMIN_EMAIL": "owner@zendoc.local",
            "ADMIN_PASSWORD": "OwnerPassword123!",
            "RATE_LIMIT_PER_MINUTE": 1000,
        }
    )
    return app, app.test_client()


def login_owner(client):
    page = client.get("/login")
    token = csrf(page.data.decode())
    response = client.post(
        "/login",
        data={
            "csrf_token": token,
            "email": "owner@zendoc.local",
            "password": "OwnerPassword123!",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200


def test_edgecare_admin_requires_owner_login(tmp_path):
    _app, client = make_client(tmp_path)
    response = client.get("/admin/edgecare", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_owner_can_view_truthful_edgecare_runtime_page(tmp_path, monkeypatch):
    _app, client = make_client(tmp_path)
    login_owner(client)

    monkeypatch.setenv("ZENDOC_EDGECARE_ENABLED", "true")
    monkeypatch.setenv("ZENDOC_LOCAL_AI_ENABLED", "false")
    monkeypatch.setenv("ZENDOC_EDGECARE_ASR_ENABLED", "false")

    response = client.get("/admin/edgecare")
    assert response.status_code == 200
    assert b"ZENDOC EdgeCare AI Runtime" in response.data
    assert b"Benchmark and NPU status" in response.data
    assert b"No real Snapdragon benchmark evidence has been recorded yet" in response.data
    assert b"Not verified ready" in response.data
    assert b"Run local AI smoke test" in response.data
