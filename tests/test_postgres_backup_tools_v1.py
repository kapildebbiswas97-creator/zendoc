from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import postgres_backup
from scripts import verify_postgres_backup


def test_connection_environment_decodes_postgres_url_without_returning_full_url():
    env = postgres_backup.connection_environment(
        "postgresql://zendoc_user:p%40ss@db.internal:5433/zendoc_prod?sslmode=require"
    )

    assert env == {
        "PGHOST": "db.internal",
        "PGPORT": "5433",
        "PGDATABASE": "zendoc_prod",
        "PGUSER": "zendoc_user",
        "PGPASSWORD": "p@ss",
        "PGSSLMODE": "require",
    }


@pytest.mark.parametrize(
    "value",
    ["", "sqlite:///tmp/zendoc.db", "postgresql://user:pass@/zendoc", "postgresql://db.internal"],
)
def test_connection_environment_rejects_invalid_database_urls(value):
    with pytest.raises(postgres_backup.BackupError):
        postgres_backup.connection_environment(value)


def test_backup_does_not_place_database_url_or_password_in_process_arguments(tmp_path, monkeypatch):
    database_url = "postgresql://zendoc_user:super-secret@db.internal:5432/zendoc"
    captured = {}

    monkeypatch.setattr(postgres_backup.shutil, "which", lambda name: f"/usr/bin/{name}")

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs["env"]
        target = Path(command[command.index("--file") + 1])
        target.write_bytes(b"PGDMP-test-archive")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(postgres_backup.subprocess, "run", fake_run)

    result = postgres_backup.create_backup(database_url, tmp_path)

    joined = " ".join(captured["command"])
    assert database_url not in joined
    assert "super-secret" not in joined
    assert captured["env"]["PGPASSWORD"] == "super-secret"
    assert "DATABASE_URL" not in captured["env"]
    assert Path(result["archive"]).is_file()
    assert Path(result["checksum"]).is_file()
    assert Path(result["manifest"]).is_file()
    assert result["off_instance_copy_verified"] is False
    assert result["restore_drill_verified"] is False


def test_verify_backup_checks_checksum_manifest_and_pg_restore_catalog(tmp_path, monkeypatch):
    archive = tmp_path / "zendoc-postgres-test.dump"
    archive.write_bytes(b"PGDMP-test-archive")
    checksum = verify_postgres_backup.sha256(archive)
    archive.with_suffix(".dump.sha256").write_text(
        f"{checksum}  {archive.name}\n",
        encoding="utf-8",
    )
    archive.with_suffix(".dump.json").write_text(
        (
            '{"format":"postgresql_custom","archive":"'
            + archive.name
            + '","sha256":"'
            + checksum
            + '"}'
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(verify_postgres_backup.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        verify_postgres_backup.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="; archive header\n1; 0 0 TABLE public users postgres\n",
            stderr="",
        ),
    )

    result = verify_postgres_backup.verify_backup(archive)

    assert result["status"] == "archive_verified"
    assert result["catalog_entries"] == 1
    assert result["restore_drill_verified"] is False


def test_verify_backup_rejects_checksum_mismatch(tmp_path, monkeypatch):
    archive = tmp_path / "zendoc-postgres-test.dump"
    archive.write_bytes(b"archive")
    archive.with_suffix(".dump.sha256").write_text(
        f"{'0' * 64}  {archive.name}\n",
        encoding="utf-8",
    )
    archive.with_suffix(".dump.json").write_text(
        '{"archive":"zendoc-postgres-test.dump","sha256":"bad"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(verify_postgres_backup.shutil, "which", lambda name: f"/usr/bin/{name}")

    with pytest.raises(verify_postgres_backup.VerificationError, match="checksum mismatch"):
        verify_postgres_backup.verify_backup(archive)
