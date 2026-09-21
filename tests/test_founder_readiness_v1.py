from zendoc.db import get_db
from zendoc.founder_readiness import founder_readiness_snapshot
from tests.test_milestone1 import login_web, make_client


def test_founder_readiness_is_owner_only_and_has_safe_fallback_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENDOC_LOCAL_AI_ENABLED", "false")
    monkeypatch.setenv("ZENDOC_EDGECARE_ASR_ENABLED", "false")
    app, client = make_client(tmp_path)

    denied = client.get("/admin/founder-readiness", follow_redirects=False)
    assert denied.status_code in {302, 401, 403}

    logged = login_web(client, "admin", "admin@example.com", "AdminStrong123")
    assert logged.status_code == 200

    response = client.get("/admin/founder-readiness?runtime=0")
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "Founder Readiness" in text
    assert "SAFE FALLBACK DEMO MODE" in text
    assert "Fundraising evidence" in text
    assert "Synthetic DEMO ONLY records never count as traction" in text
    assert "Open Public Showcase" in text
    assert "Export Investor Evidence" in text

    with app.app_context():
        owner = dict(
            get_db().execute(
                "SELECT * FROM users WHERE email_normalized='admin@example.com'"
            ).fetchone()
        )
        snapshot = founder_readiness_snapshot(owner, check_runtime=False, days=30)

    assert snapshot["meeting_mode"] == "SAFE_FALLBACK_DEMO_MODE"
    assert snapshot["demo"]["route_contract"]["missing"] == []
    assert snapshot["demo"]["route_contract"]["contract_present"] is True
    assert snapshot["demo"]["runtime_health_checked"] is False
    assert snapshot["funding"]["status"] == "EARLY_EVIDENCE_COLLECTION"
    assert snapshot["funding"]["present_count"] == 0
    assert snapshot["claims"]["synthetic_demo_fixture_counts_as_traction"] is False
    assert snapshot["claims"]["runtime_configuration_proves_snapdragon_npu"] is False
    assert snapshot["claims"]["software_implementation_proves_provider_fulfilment"] is False


def test_owner_navigation_exposes_founder_readiness(tmp_path):
    _app, client = make_client(tmp_path)
    login_web(client, "admin", "admin@example.com", "AdminStrong123")
    page = client.get("/admin")
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert "Founder Readiness" in body
    assert "/admin/founder-readiness" in body
