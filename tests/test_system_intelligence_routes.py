from tests.test_milestone1 import login_web, make_client, register_web


def test_owner_intelligence_manifest_is_owner_only(tmp_path):
    _app, client = make_client(tmp_path)

    register_web(client, "patient", "normal@example.com")
    login_web(client, "patient", "normal@example.com")
    denied = client.get("/owner/intelligence-manifest")
    assert denied.status_code == 403

    client.get("/logout")
    login_web(client, "admin", "admin@example.com", "AdminStrong123")
    allowed = client.get("/owner/intelligence-manifest")
    assert allowed.status_code == 200
    payload = allowed.get_json()
    assert payload["status"] == "ok"
    assert payload["automation"]["agent_count"] >= 10
    assert payload["agents"]
    assert payload["model_roles"]
    assert payload["benefit_sources"]
    assert payload["regulated_domains"]
