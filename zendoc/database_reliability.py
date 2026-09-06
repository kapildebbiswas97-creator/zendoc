"""Database reliability, readiness, backup, and migration audit helpers."""
from __future__ import annotations

import os
import time
import shutil
from pathlib import Path

from flask import current_app

from .db import get_db, now_iso


REQUIRED_MIGRATIONS = (
    "post_submission_provider_tenancy_v1",
    "post_submission_provider_resource_tenancy_v1",
    "post_submission_concurrency_v1",
    "post_submission_request_fingerprints_v1",
    "post_submission_observability_v1",
)

REQUIRED_TABLES = (
    "users",
    "appointments",
    "provider_profiles",
    "prescriptions",
    "diagnostic_bookings",
    "medicine_orders",
    "consultation_requests",
    "provider_organizations",
    "organization_memberships",
    "appointment_slot_claims",
    "request_observations",
    "integration_health_checks",
)


def _dialect(db=None):
    db = db or get_db()
    return getattr(db, "dialect", "sqlite")


def database_probe():
    db = get_db()
    started = time.perf_counter()
    row = db.execute("SELECT 1 AS ok").fetchone()
    latency_ms = int((time.perf_counter() - started) * 1000)
    if not row or int(row["ok"]) != 1:
        raise RuntimeError("Database probe failed.")
    return {"ok": True, "latency_ms": max(0, latency_ms)}


def migration_status():
    db = get_db()
    try:
        rows = db.execute("SELECT version, applied_at FROM schema_migrations").fetchall()
    except Exception:
        return {
            "ready": False,
            "missing_migrations": list(REQUIRED_MIGRATIONS),
            "applied_count": 0,
        }
    versions = {str(row["version"]) for row in rows}
    missing = [version for version in REQUIRED_MIGRATIONS if version not in versions]
    return {
        "ready": not missing,
        "missing_migrations": missing,
        "applied_count": len(versions),
    }


def schema_status():
    db = get_db()
    if _dialect(db) == "postgresql":
        rows = db.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema=current_schema()
            """
        ).fetchall()
        tables = {row["table_name"] for row in rows}
    else:
        rows = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        tables = {row["name"] for row in rows}
    missing = [table for table in REQUIRED_TABLES if table not in tables]
    return {"ready": not missing, "missing_tables": missing}


def sqlite_integrity_status():
    db = get_db()
    if _dialect(db) != "sqlite":
        return {
            "supported": False,
            "status": "INTEGRATION_REQUIRED",
            "detail": "Use managed PostgreSQL health/backup tooling in production.",
        }
    row = db.execute("PRAGMA quick_check").fetchone()
    value = str(row[0] if not hasattr(row, "keys") else row["quick_check"]).strip().lower()
    return {
        "supported": True,
        "status": "ok" if value == "ok" else "failed",
        "detail": value,
    }


def readiness_report():
    report = {
        "status": "ready",
        "service": "zendoc",
        "time": now_iso(),
        "database_engine": current_app.config.get("DATABASE_ENGINE", "sqlite"),
        "database_durability": current_app.config.get("DATABASE_DURABILITY"),
        "persistence_verified": bool(current_app.config.get("PERSISTENCE_VERIFIED")),
    }
    try:
        probe = database_probe()
        report["database"] = "reachable"
        report["database_latency_ms"] = probe["latency_ms"]
    except Exception:
        report["database"] = "unreachable"
        report["status"] = "not_ready"
        return report

    migration = migration_status()
    schema = schema_status()
    report["migrations"] = migration
    report["schema"] = schema
    if not migration["ready"] or not schema["ready"]:
        report["status"] = "not_ready"

    if report["database_engine"] == "sqlite":
        integrity = sqlite_integrity_status()
        report["integrity"] = integrity
        if integrity.get("status") != "ok":
            report["status"] = "not_ready"

    if (
        current_app.config.get("ZENDOC_ENV") == "production"
        and current_app.config.get("DATABASE_DURABILITY") == "integration_required"
    ):
        report["status"] = "not_ready"
        report["durability_warning"] = "Production database durability is not verified."
    return report


def create_sqlite_backup(destination_dir=None):
    """Create a consistent SQLite snapshot. PostgreSQL backups are external."""
    db = get_db()
    if _dialect(db) != "sqlite":
        return {
            "status": "INTEGRATION_REQUIRED",
            "engine": "postgresql",
            "detail": "Configure managed backups or pg_dump outside the web process.",
        }

    database_path = Path(str(current_app.config["DATABASE"]))
    if str(database_path) == ":memory:":
        raise RuntimeError("In-memory test databases cannot be backed up.")

    backup_root = Path(destination_dir or current_app.config.get("DATABASE_BACKUP_DIR") or database_path.parent / "backups")
    backup_root.mkdir(parents=True, exist_ok=True)
    timestamp = now_iso().replace(":", "").replace("+", "_")
    target = backup_root / f"zendoc-{timestamp}.db"

    import sqlite3
    destination = sqlite3.connect(target)
    try:
        db.backup(destination)
        destination.execute("PRAGMA quick_check")
        destination.commit()
    finally:
        destination.close()

    return {
        "status": "created",
        "engine": "sqlite",
        "path": str(target),
        "size_bytes": target.stat().st_size,
        "created_at": now_iso(),
    }


def backup_readiness():
    engine = current_app.config.get("DATABASE_ENGINE")
    if engine == "postgresql":
        return {
            "status": "INTEGRATION_REQUIRED",
            "engine": "postgresql",
            "detail": "Use managed automated backups/PITR or secured pg_dump; ZENDOC does not fake backup success.",
        }
    path = Path(str(current_app.config.get("DATABASE") or ""))
    return {
        "status": "READY" if path.exists() else "NOT_READY",
        "engine": "sqlite",
        "database_path_exists": path.exists(),
        "backup_directory": str(Path(current_app.config.get("DATABASE_BACKUP_DIR") or path.parent / "backups")),
    }
