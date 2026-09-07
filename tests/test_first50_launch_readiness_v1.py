from zendoc.launch_readiness import first50_launch_readiness
from tests.test_milestone1 import api_token, login_web, make_client


def test_first50_readiness_empty_pilot_is_truthful_not_fake_green(tmp_path):
    app, _client = make_client(tmp_path)
    with app.app_context():
        report = first50_launch_readiness()

    assert report["target"] == "first_50_users"
    assert report["status"] in {"PILOT_READY_WITH_WARNINGS", "PILOT_READY"}
    warning_keys = {item["key"] for item in report["warnings"]}
    assert "verified_provider_coverage" in warning_keys
    assert "geography_west_bengal" in warning_keys
    assert "geography_assam" in warning_keys
    assert "geography_uttar_pradesh" in warning_keys
    assert "every locality" in report["truth_notice"]


def test_first50_readiness_database_failure_is_blocker(tmp_path, monkeypatch):
    app, _client = make_client(tmp_path)
    with app.app_context():
        import zendoc.launch_readiness as launch_readiness

        monkeypatch.setattr(
            launch_readiness,
            "readiness_report",
            lambda: {"status": "not_ready", "database": "unreachable"},
        )
        report = first50_launch_readiness()

    assert report["status"] == "BLOCKED"
    blocker_keys = {item["key"] for item in report["blockers"]}
    assert "database_readiness" in blocker_keys


def test_owner_first50_readiness_route_is_owner_only(tmp_path):
    _app, client = make_client(tmp_path)

    token = api_token(client, "first50-normal@example.com")
    denied = client.get(
        "/owner/first50-readiness",
        headers={"Authorization": f"Bearer {token}"},
    )
    # Owner web routes use the authenticated web session, not bearer elevation.
    assert denied.status_code in {302, 403}

    login = login_web(client, "admin", "admin@example.com", "AdminStrong123")
    assert login.status_code == 200
    allowed = client.get("/owner/first50-readiness")
    assert allowed.status_code == 200
    payload = allowed.get_json()
    assert payload["target"] == "first_50_users"
    assert "blockers" in payload
    assert "warnings" in payload
