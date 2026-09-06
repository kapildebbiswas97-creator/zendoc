from __future__ import annotations

from pathlib import Path

from zendoc.database_reliability import (
    backup_readiness,
    create_sqlite_backup,
    migration_status,
    readiness_report,
    schema_status,
    sqlite_integrity_status,
)
from zendoc.db import get_db
from tests.test_milestone1 import make_app


def test_health_is_liveness_and_ready_checks_database(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    live = client.get("/api/v1/health")
    assert live.status_code == 200
    assert live.get_json()["check"] == "liveness"

    ready = client.get("/api/v1/ready")
    assert ready.status_code == 200
    payload = ready.get_json()
    assert payload["status"] == "ready"
    assert payload["database"] == "reachable"
    assert payload["migrations"]["ready"] is True
    assert payload["schema"]["ready"] is True


def test_required_migrations_and_tables_are_present(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        migration = migration_status()
        schema = schema_status()
        assert migration["ready"] is True
        assert migration["missing_migrations"] == []
        assert schema["ready"] is True
        assert schema["missing_tables"] == []


def test_sqlite_quick_check_reports_ok(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        status = sqlite_integrity_status()
        assert status["supported"] is True
        assert status["status"] == "ok"


def test_sqlite_backup_creation_is_consistent_and_non_destructive(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        before = db.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        result = create_sqlite_backup(tmp_path / "backups")
        assert result["status"] == "created"
        backup = Path(result["path"])
        assert backup.exists()
        assert backup.stat().st_size > 0
        after = db.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        assert after == before


def test_backup_readiness_is_truthful_for_sqlite(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        result = backup_readiness()
        assert result["engine"] == "sqlite"
        assert result["status"] == "READY"
        assert result["database_path_exists"] is True


def test_readiness_fails_when_required_migration_is_missing(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        db.execute(
            "DELETE FROM schema_migrations WHERE version='post_submission_concurrency_v1'"
        )
        db.commit()

        report = readiness_report()
        assert report["status"] == "not_ready"
        assert "post_submission_concurrency_v1" in report["migrations"]["missing_migrations"]


def test_owner_database_readiness_endpoint_is_protected(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    denied = client.get("/owner/database-readiness")
    assert denied.status_code in {302, 401, 403}
