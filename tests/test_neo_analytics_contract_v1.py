from tests.test_milestone1 import login_web, make_client, register_web


def test_neo_analytics_contract_is_owner_only(tmp_path):
    _app, client = make_client(tmp_path)

    denied = client.get("/api/v1/admin/neo/analytics", follow_redirects=False)
    assert denied.status_code in {302, 401, 403}

    register_web(client, "patient", "neo-user@example.com", "Neo User")
    login_web(client, "patient", "neo-user@example.com")
    forbidden = client.get("/api/v1/admin/neo/analytics", follow_redirects=False)
    assert forbidden.status_code == 403


def test_neo_analytics_contract_returns_aggregate_truth_bounded_payload(tmp_path):
    _app, client = make_client(tmp_path)
    login_web(client, "admin", "admin@example.com", "AdminStrong123")

    response = client.get(
        "/api/v1/admin/neo/analytics?days=30&provider_days=90",
        follow_redirects=False,
    )
    assert response.status_code == 200

    payload = response.get_json()
    assert payload["status"] == "OK"
    assert payload["contract"] == {
        "name": "zendoc.neo.analytics",
        "version": "1.0",
        "aggregate_only": True,
        "clinical_content": False,
    }
    assert payload["window_days"] == 30
    assert "startup" in payload
    assert "activation" in payload
    assert "coverage" in payload
    assert "retention" in payload
    assert "care_journey" in payload
    assert "provider_onboarding" in payload
    assert "pilot" in payload
    assert "aggregate ZENDOC operational evidence only" in payload["truth_notice"]


def test_neo_analytics_contract_bounds_requested_windows(tmp_path):
    _app, client = make_client(tmp_path)
    login_web(client, "admin", "admin@example.com", "AdminStrong123")

    response = client.get(
        "/api/v1/admin/neo/analytics?days=9999&provider_days=-4",
        follow_redirects=False,
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["window_days"] == 365
    assert payload["provider_onboarding"]["window_days"] == 1
