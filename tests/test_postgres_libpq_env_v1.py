from scripts import postgres_backup, postgres_restore


def test_backup_and_restore_children_preserve_libpq_credentials(monkeypatch):
    monkeypatch.setenv("PGUSER", "zendoc-operator")
    monkeypatch.setenv("PGPASSWORD", "p@ss:word/%with-reserved")
    monkeypatch.setenv("PGDATABASE", "ignored-by-explicit-url")
    url = "postgresql://db:5432/zendoc"

    for builder in (postgres_backup._child_environment, postgres_restore._child_environment):
        env = builder(url)
        assert env["PGHOST"] == "db"
        assert env["PGPORT"] == "5432"
        assert env["PGDATABASE"] == "zendoc"
        assert env["PGUSER"] == "zendoc-operator"
        assert env["PGPASSWORD"] == "p@ss:word/%with-reserved"


def test_url_credentials_override_ambient_libpq_credentials(monkeypatch):
    monkeypatch.setenv("PGUSER", "ambient-user")
    monkeypatch.setenv("PGPASSWORD", "ambient-password")
    env = postgres_backup._child_environment(
        "postgresql://url-user:url-password@db:5432/zendoc"
    )
    assert env["PGUSER"] == "url-user"
    assert env["PGPASSWORD"] == "url-password"
