from scripts import verify_postgres_backup_restore


def test_restore_drill_pg_environment_excludes_unrelated_zendoc_secrets(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("ZENDOC_ADMIN_PASSWORD", "admin-secret")
    monkeypatch.setenv("ZENDOC_SMTP_PASSWORD", "smtp-secret")
    monkeypatch.setenv("ZENDOC_AI_API_KEY", "ai-secret")
    monkeypatch.setenv("ZENDOC_S3_SECRET_ACCESS_KEY", "storage-secret")
    monkeypatch.setenv("DATABASE_URL", "must-not-be-inherited")

    env = verify_postgres_backup_restore._pg_env(
        "postgresql://zendoc_user:p%40ss@db.internal:5432/zendoc_verify?sslmode=require"
    )

    assert env["PATH"] == "/usr/bin"
    assert env["PGHOST"] == "db.internal"
    assert env["PGPORT"] == "5432"
    assert env["PGDATABASE"] == "zendoc_verify"
    assert env["PGUSER"] == "zendoc_user"
    assert env["PGPASSWORD"] == "p@ss"
    assert env["PGSSLMODE"] == "require"

    assert "DATABASE_URL" not in env
    assert "ZENDOC_ADMIN_PASSWORD" not in env
    assert "ZENDOC_SMTP_PASSWORD" not in env
    assert "ZENDOC_AI_API_KEY" not in env
    assert "ZENDOC_S3_SECRET_ACCESS_KEY" not in env
