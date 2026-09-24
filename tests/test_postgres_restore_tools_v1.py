from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts import postgres_restore


class FakeResult:
    def __init__(self, *, rows=None, one=(1,)):
        self._rows = rows or []
        self._one = one

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._one


class FakeConnection:
    def __init__(self, tables):
        self.tables = list(tables)
        self.statements = []
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.statements.append(str(sql))
        if "information_schema.tables" in str(sql):
            return FakeResult(rows=[(table,) for table in self.tables])
        if str(sql).startswith("DROP SCHEMA"):
            self.tables = []
        return FakeResult()

    def commit(self):
        self.committed = True


def test_database_identity_decodes_database_and_defaults_port():
    assert postgres_restore.database_identity(
        "postgresql://user:p%40ss@DB.Internal/zendoc_prod?sslmode=require"
    ) == ("db.internal", 5432, "zendoc_prod")


def test_restore_command_keeps_target_url_and_password_out_of_argv(tmp_path, monkeypatch):
    archive = tmp_path / "zendoc.dump"
    archive.write_bytes(b"archive")
    connections = iter([FakeConnection([]), FakeConnection(["users"])])

    monkeypatch.setattr(
        postgres_restore,
        "verify_backup",
        lambda *args, **kwargs: {"catalog_entries": 42},
    )
    monkeypatch.setattr(postgres_restore.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        postgres_restore.psycopg,
        "connect",
        lambda *args, **kwargs: next(connections),
    )

    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs["env"]
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(postgres_restore.subprocess, "run", fake_run)

    target_url = "postgresql://zendoc:super-secret@db:5432/zendoc"
    result = postgres_restore.restore_backup(
        archive,
        target_url,
        expected_database="zendoc",
    )

    joined = " ".join(captured["command"])
    assert target_url not in joined
    assert "super-secret" not in joined
    assert captured["env"]["PGPASSWORD"] == "super-secret"
    assert "DATABASE_URL" not in captured["env"]
    assert "--single-transaction" in captured["command"]
    assert captured["command"][captured["command"].index("--dbname") + 1] == "zendoc"
    assert result["status"] == "restore_completed"
    assert result["catalog_entries"] == 42
    assert result["reset_performed"] is False


def test_restore_refuses_to_overwrite_existing_tables_without_explicit_reset(
    tmp_path, monkeypatch
):
    archive = tmp_path / "zendoc.dump"
    archive.write_bytes(b"archive")
    monkeypatch.setattr(
        postgres_restore,
        "verify_backup",
        lambda *args, **kwargs: {"catalog_entries": 1},
    )
    monkeypatch.setattr(postgres_restore.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        postgres_restore.psycopg,
        "connect",
        lambda *args, **kwargs: FakeConnection(["users"]),
    )

    called = {"run": False}

    def fail_if_called(*args, **kwargs):
        called["run"] = True
        raise AssertionError("pg_restore must not run against an occupied target")

    monkeypatch.setattr(postgres_restore.subprocess, "run", fail_if_called)

    with pytest.raises(postgres_restore.RestoreError, match="Refusing to overwrite"):
        postgres_restore.restore_backup(
            archive,
            "postgresql://zendoc:pw@db:5432/zendoc",
            expected_database="zendoc",
            allow_reset=False,
        )

    assert called["run"] is False


def test_restore_reset_requires_explicit_opt_in_and_reports_it(tmp_path, monkeypatch):
    archive = tmp_path / "zendoc.dump"
    archive.write_bytes(b"archive")
    first = FakeConnection(["users", "appointments"])
    second = FakeConnection(["users", "appointments", "medical_records"])
    connections = iter([first, second])

    monkeypatch.setattr(
        postgres_restore,
        "verify_backup",
        lambda *args, **kwargs: {"catalog_entries": 3},
    )
    monkeypatch.setattr(postgres_restore.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        postgres_restore.psycopg,
        "connect",
        lambda *args, **kwargs: next(connections),
    )
    monkeypatch.setattr(
        postgres_restore.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )

    result = postgres_restore.restore_backup(
        archive,
        "postgresql://zendoc:pw@db:5432/zendoc",
        expected_database="zendoc",
        allow_reset=True,
    )

    assert any("DROP SCHEMA IF EXISTS public CASCADE" in sql for sql in first.statements)
    assert first.committed is True
    assert result["reset_performed"] is True
    assert result["target_tables_before"] == 2
    assert result["target_tables_after"] == 3


def test_restore_target_name_and_optional_source_guard_fail_closed(tmp_path):
    archive = tmp_path / "zendoc.dump"
    archive.write_bytes(b"archive")

    with pytest.raises(postgres_restore.RestoreError, match="does not match"):
        postgres_restore.restore_backup(
            archive,
            "postgresql://zendoc:pw@db:5432/zendoc",
            expected_database="wrong",
        )

    with pytest.raises(postgres_restore.RestoreError, match="same database"):
        postgres_restore.restore_backup(
            archive,
            "postgresql://zendoc:pw@db:5432/zendoc",
            expected_database="zendoc",
            source_guard_url="postgres://other:other@DB:5432/zendoc",
        )
