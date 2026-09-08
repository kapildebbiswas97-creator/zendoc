from zendoc.database_reliability import deployment_identity, readiness_report
from tests.test_milestone1 import make_app


def test_render_deployment_identity_is_non_secret_and_exposes_commit(tmp_path, monkeypatch):
    monkeypatch.setenv("RENDER_SERVICE_NAME", "zendoc")
    monkeypatch.setenv("RENDER_SERVICE_ID", "srv-test")
    monkeypatch.setenv("RENDER_EXTERNAL_HOSTNAME", "zendoc.example.onrender.com")
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abcdef1234567890abcdef1234567890abcdef12")

    app = make_app(tmp_path)
    with app.app_context():
        identity = deployment_identity()
        assert identity["platform"] == "render"
        assert identity["service_name"] == "zendoc"
        assert identity["service_id"] == "srv-test"
        assert identity["external_hostname"] == "zendoc.example.onrender.com"
        assert identity["git_commit"] == "abcdef1234567890abcdef1234567890abcdef12"
        assert identity["git_commit_short"] == "abcdef123456"
        assert "DATABASE_URL" not in identity
        assert "secret" not in str(identity).lower()

        report = readiness_report()
        assert report["deployment"]["git_commit_short"] == "abcdef123456"
        assert report["deployment"]["platform"] == "render"
