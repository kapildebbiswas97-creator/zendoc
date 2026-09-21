from tests.test_milestone1 import make_client
from zendoc.launch_readiness import software_completion_readiness


def test_repository_owned_software_completion_gate_is_green(tmp_path):
    app, _client = make_client(tmp_path)

    with app.app_context():
        report = software_completion_readiness()

    assert report["status"] == "SOFTWARE_IMPLEMENTATION_COMPLETE", report["blockers"]
    assert report["blockers"] == []
    assert report["route_count"] >= 53
    registered = {str(rule.rule) for rule in app.url_map.iter_rules()}
    assert "/health" in registered
    assert "/healthz" in registered
    assert report["artifact_count"] >= 45
    assert report["regression_file_count"] >= 20
    assert report["validation_status"] == "EXACT_HEAD_CI_STILL_REQUIRED"


def test_software_completion_gate_stays_separate_from_external_launch_configuration(tmp_path):
    app, _client = make_client(tmp_path)

    with app.app_context():
        app.config.update(
            PUBLIC_BASE_URL="",
            EMAIL_PROVIDER="none",
            STORAGE_PROVIDER="local",
            BACKUP_VERIFIED=False,
            ANDROID_PACKAGE_NAME="",
        )
        report = software_completion_readiness()

    assert report["status"] == "SOFTWARE_IMPLEMENTATION_COMPLETE", report["blockers"]
    assert "domain" not in str(report["blockers"]).lower()
    assert "smtp" not in str(report["blockers"]).lower()
    assert "google play" not in str(report["blockers"]).lower()
