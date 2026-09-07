from zendoc.scale_readiness import scale_readiness_report
from tests.test_milestone1 import login_web, make_client


def test_scale_readiness_blocks_sqlite_from_large_scale_claim(tmp_path):
    app, _client = make_client(tmp_path)
    with app.app_context():
        report = scale_readiness_report()

    assert report["status"] == "BLOCKED"
    blocker_keys = {item["key"] for item in report["blockers"]}
    assert "database_engine" in blocker_keys
    assert "persistence_verified" in blocker_keys
    assert "specific user count" in report["truth_notice"]


def test_owner_scale_readiness_route_is_owner_only(tmp_path):
    _app, client = make_client(tmp_path)

    denied = client.get("/owner/scale-readiness")
    assert denied.status_code in {302, 401, 403}

    login = login_web(client, "admin", "admin@example.com", "AdminStrong123")
    assert login.status_code == 200

    allowed = client.get("/owner/scale-readiness")
    assert allowed.status_code == 200
    payload = allowed.get_json()
    assert "blockers" in payload
    assert "warnings" in payload
    assert "runtime" in payload
