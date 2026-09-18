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
    assert b"End-to-end care chain" in response.data
    assert b"Agent OS bounded execution" in response.data
    assert b"Provider/service confirmation" in response.data
    assert b"Demo runtime gate: LOCAL RUNTIME REQUIRED" in response.data
    assert b"implemented software is not the same as a live local runtime" in response.data.lower()


def test_edgecare_runtime_api_separates_software_runtime_and_provider_truth(tmp_path, monkeypatch):
    app, client = make_client(tmp_path)
    login_owner(client)

    monkeypatch.setenv("ZENDOC_EDGECARE_ENABLED", "true")
    monkeypatch.setenv("ZENDOC_LOCAL_AI_ENABLED", "false")
    monkeypatch.setenv("ZENDOC_EDGECARE_ASR_ENABLED", "false")

    with app.app_context():
        owner = app.extensions.get("zendoc_owner")
        if owner is None:
            from zendoc.db import get_db
            owner = get_db().execute(
                "SELECT * FROM users WHERE email_normalized='owner@zendoc.local'"
            ).fetchone()

    # Browser owner auth is sufficient to prove the same snapshot shape via the
    # rendered page; the API contract is exercised through the internal helper
    # because the API route additionally requires token auth.
    from zendoc.edgecare_routes import _runtime_snapshot

    with app.app_context():
        snapshot = _runtime_snapshot(check_health=False)
    chain = snapshot["care_chain"]
    assert chain["software_chain_present"] is True
    assert chain["demo_runtime_ready"] is False
    assert chain["runtime_gate"] == "LOCAL_RUNTIME_REQUIRED"
    stages = {item["key"]: item for item in chain["stages"]}
    assert stages["agent_os"]["status"] == "IMPLEMENTED"
    assert stages["health_memory"]["status"] == "IMPLEMENTED"
    assert stages["provider_confirmation"]["status"] == "EVIDENCE_DRIVEN"
    assert stages["outcome"]["status"] == "EVIDENCE_DRIVEN"
    assert chain["truth"]["runtime_config_means_snapdragon_npu_proven"] is False
    assert chain["truth"]["model_output_means_provider_confirmation"] is False
