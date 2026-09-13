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
    assert payload["medical_knowledge_sources"]
    assert payload["ai_runtime"]["routing_policy"]["model_output_can_execute_tools"] is False
    assert payload["tool_governance"]["registered_tools"] > 0
    assert payload["tool_governance"]["model_output_can_execute_tools"] is False


def test_owner_ai_runtime_is_truthful_and_owner_only(tmp_path):
    _app, client = make_client(tmp_path)

    register_web(client, "patient", "runtime-normal@example.com")
    login_web(client, "patient", "runtime-normal@example.com")
    denied = client.get("/owner/ai-runtime")
    assert denied.status_code == 403

    client.get("/logout")
    login_web(client, "admin", "admin@example.com", "AdminStrong123")
    allowed = client.get("/owner/ai-runtime")
    assert allowed.status_code == 200
    payload = allowed.get_json()
    runtime = payload["ai_runtime"]
    tools = payload["tool_governance"]

    assert payload["status"] == "ok"
    assert runtime["deterministic_safety"]["status"] == "working"
    assert runtime["local_fallback"]["status"] == "working"
    assert runtime["routing_mode"]
    assert "externally reachable" in runtime["truth_boundary"]
    assert tools["registered_tools"] >= 10
    assert tools["risk_class_counts"]["CRITICAL_BLOCKED"] >= 1
    assert "autonomous_prescribe" in tools["critical_blocked_tools"]
    assert "dispatch_emergency" in tools["critical_blocked_tools"]
    assert tools["model_output_can_execute_tools"] is False
    assert "Server-side policy" in tools["execution_boundary"]


def test_capability_registry_uses_only_truthful_statuses(tmp_path):
    from zendoc.capability_registry import get_capability_registry

    app, _client = make_client(tmp_path)
    with app.app_context():
        statuses = {item["status"] for item in get_capability_registry().values()}
    assert statuses <= {"WORKING", "BETA", "INTEGRATION_REQUIRED", "DISABLED", "FUTURE"}


def test_owner_manifest_exposes_no_capital_readiness(tmp_path):
    _app, client = make_client(tmp_path)
    login_web(client, "admin", "admin@example.com", "AdminStrong123")
    response = client.get("/owner/intelligence-manifest")
    assert response.status_code == 200
    payload = response.get_json()
    report = payload["no_capital_progress"]
    scope = report["software_no_capital_scope"]
    assert scope["total"] > 0
    assert 0 <= scope["working_percent"] <= 100
    assert scope["measurement_rule"]
    assert report["partner_dependencies"]
    assert report["physical_capital_dependencies"]


def test_owner_manifest_exposes_public_ingestion_sources(tmp_path):
    _app, client = make_client(tmp_path)
    login_web(client, "admin", "admin@example.com", "AdminStrong123")
    response = client.get("/owner/intelligence-manifest")
    assert response.status_code == 200
    payload = response.get_json()
    sources = {item["source_id"]: item for item in payload["public_ingestion_sources"]}
    assert "lgd" in sources
    assert "data_gov_hospitals" in sources
    assert "abdm_hfr" in sources
    assert sources["abdm_hfr"]["live_fetch_status"] == "ONBOARDING_OR_AUTHORIZED_ACCESS_REQUIRED"


def test_owner_medical_knowledge_sources_are_review_only_and_owner_only(tmp_path):
    _app, client = make_client(tmp_path)

    register_web(client, "patient", "knowledge-normal@example.com")
    login_web(client, "patient", "knowledge-normal@example.com")
    denied = client.get("/owner/medical-knowledge-sources")
    assert denied.status_code == 403

    client.get("/logout")
    login_web(client, "admin", "admin@example.com", "AdminStrong123")
    allowed = client.get("/owner/medical-knowledge-sources")
    assert allowed.status_code == 200
    payload = allowed.get_json()
    assert payload["status"] == "ok"
    assert payload["sources"]
    assert all(item["ingestion_status"] == "REVIEW_REQUIRED" for item in payload["sources"])
    assert all(item["allowed_for_answering_without_snapshot"] is False for item in payload["sources"])
    assert "no source is automatically approved" in payload["notice"].lower()


def test_owner_pilot_scorecard_is_real_and_owner_only(tmp_path):
    _app, client = make_client(tmp_path)

    register_web(client, "patient", "pilot-score-normal@example.com")
    login_web(client, "patient", "pilot-score-normal@example.com")
    denied = client.get("/owner/pilot-scorecard")
    assert denied.status_code == 403

    client.get("/logout")
    login_web(client, "admin", "admin@example.com", "AdminStrong123")
    allowed = client.get("/owner/pilot-scorecard")
    assert allowed.status_code == 200
    payload = allowed.get_json()
    assert payload["status"] == "OK"
    assert "providers" in payload
    assert "care_journeys" in payload
    assert "carefin" in payload
    assert "fulfilment" in payload
    assert "diagnostics" in payload
    assert "data_coverage" in payload
    assert "operations" in payload
    assert payload["measurement_boundary"]
    assert payload["carefin"]["confirmed_savings_inr"] is None


def test_pilot_scorecard_zero_denominator_is_not_faked(tmp_path):
    from zendoc.pilot_analytics import pilot_scorecard

    app, _client = make_client(tmp_path)
    with app.app_context():
        payload = pilot_scorecard()
    assert payload["providers"]["verified_rate_percent"] is None
    assert payload["care_journeys"]["completion_rate_percent"] is None
    assert payload["fulfilment"]["plan_to_order_conversion_percent"] is None
    assert payload["diagnostics"]["completion_rate_percent"] is None


def test_owner_observability_exposes_pilot_signals(tmp_path):
    _app, client = make_client(tmp_path)
    login_web(client, "admin", "admin@example.com", "AdminStrong123")

    response = client.get("/owner/observability")
    assert response.status_code == 200
    payload = response.get_json()

    assert "pilot_signals" in payload
    assert "provider_responsiveness" in payload
    assert "data_freshness" in payload
    assert "engagement" in payload
