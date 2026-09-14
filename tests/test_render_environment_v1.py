from zendoc import create_app


def test_render_runtime_defaults_to_production_security(monkeypatch, tmp_path):
    monkeypatch.delenv("ZENDOC_ENV", raising=False)
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("RENDER_SERVICE_ID", "srv-ci-zendoc")

    app = create_app(
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
