import os

from zendoc import create_app


def create_hosted_test_app(config):
    try:
        return create_app(config)
    finally:
        # _normalize_hosted_environment sets ZENDOC_ENV for hosted runtimes;
        # keep that process-wide normalization from leaking into later tests.
        os.environ.pop("ZENDOC_ENV", None)


def test_render_runtime_defaults_to_production_security(monkeypatch, tmp_path):
    monkeypatch.delenv("ZENDOC_ENV", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("RENDER_SERVICE_ID", "srv-ci-zendoc")

    app = create_hosted_test_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "render-env.db"),
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "SECRET_KEY": "test-secret",
            "ADMIN_EMAIL": "owner@example.com",
            "ADMIN_PASSWORD": "OwnerPassword123!",
            "RATE_LIMIT_PER_MINUTE": 1000,
        }
    )

    assert app.config["ZENDOC_ENV"] == "production"
    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["ALLOW_LEGACY_GET_LOGOUT"] is False


def test_vercel_preview_runtime_defaults_to_production_security(monkeypatch, tmp_path):
    monkeypatch.delenv("ZENDOC_ENV", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("ZENDOC_REQUIRE_DURABLE_DATABASE", raising=False)
    monkeypatch.setenv("VERCEL", "1")

    app = create_hosted_test_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "vercel-env.db"),
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "SECRET_KEY": "test-secret",
            "ADMIN_EMAIL": "owner@example.com",
            "ADMIN_PASSWORD": "OwnerPassword123!",
            "RATE_LIMIT_PER_MINUTE": 1000,
        }
    )

    assert app.config["ZENDOC_ENV"] == "production"
    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["ALLOW_LEGACY_GET_LOGOUT"] is False
    assert app.config["REQUIRE_DURABLE_DATABASE"] is True
