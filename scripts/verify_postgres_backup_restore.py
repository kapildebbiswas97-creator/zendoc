#!/usr/bin/env python3
"""Perform a destructive-to-scratch PostgreSQL backup/restore smoke test.

This script NEVER resets the source DATABASE_URL. It requires a second,
explicit scratch database URL and an opt-in reset flag. The restored scratch
schema is removed again by default after verification.

Use a scratch database protected to the same standard as production because the
restore briefly contains a copy of production data.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import psycopg


SOURCE_ENV = "DATABASE_URL"
TARGET_ENV = "ZENDOC_BACKUP_VERIFY_DATABASE_URL"
RESET_ENV = "ZENDOC_BACKUP_VERIFY_ALLOW_RESET"
KEEP_ENV = "ZENDOC_BACKUP_VERIFY_KEEP_RESTORE"

CORE_TABLES = (
    "users",
    "appointments",
    "medical_records",
    "health_timeline_events",
    "health_metrics",
)


def _parse_pg_url(value: str, label: str):
    parsed = urlparse(value)
    if parsed.scheme not in {"postgresql", "postgres"}:
        raise RuntimeError(f"{label} must be a PostgreSQL URL.")
    database = unquote((parsed.path or "").lstrip("/"))
    if not parsed.hostname or not database:
        raise RuntimeError(f"{label} must include a host and database name.")
    return parsed, database


def _pg_env(url: str):
    parsed, database = _parse_pg_url(url, "PostgreSQL URL")
    env = os.environ.copy()
    env.update(
        {
            "PGHOST": parsed.hostname or "",
            "PGPORT": str(parsed.port or 5432),
            "PGDATABASE": database,
            "PGUSER": unquote(parsed.username or ""),
            "PGPASSWORD": unquote(parsed.password or ""),
        }
    )
    query = parse_qs(parsed.query or "")
    if query.get("sslmode"):
        env["PGSSLMODE"] = query["sslmode"][0]
    return env


def _table_count(conn, table: str):
    exists = conn.execute(
        """
        SELECT EXISTS(
          SELECT 1 FROM information_schema.tables
          WHERE table_schema='public' AND table_name=%s
        )
        """,
        (table,),
    ).fetchone()[0]
    if not exists:
        return None
    # table is selected from the fixed CORE_TABLES constant, never user input.
    return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]


def _reset_scratch(conn):
    conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
    conn.execute("CREATE SCHEMA public")
    conn.commit()


def main() -> int:
    source_url = str(os.environ.get(SOURCE_ENV) or "").strip()
    target_url = str(os.environ.get(TARGET_ENV) or "").strip()
    allow_reset = str(os.environ.get(RESET_ENV) or "").strip().lower() in {"1", "true", "yes", "on"}
    keep_restore = str(os.environ.get(KEEP_ENV) or "").strip().lower() in {"1", "true", "yes", "on"}

    if not source_url or not target_url:
        print(
            f"FAIL: both {SOURCE_ENV} and {TARGET_ENV} are required.",
            file=sys.stderr,
        )
        return 2
    if not allow_reset:
        print(
            f"FAIL: {RESET_ENV}=true is required because the scratch database will be reset.",
            file=sys.stderr,
        )
        return 2

    source_parsed, source_db = _parse_pg_url(source_url, SOURCE_ENV)
    target_parsed, target_db = _parse_pg_url(target_url, TARGET_ENV)
    if (
        source_parsed.hostname == target_parsed.hostname
        and (source_parsed.port or 5432) == (target_parsed.port or 5432)
        and source_db == target_db
    ):
        print("FAIL: source and scratch database resolve to the same database.", file=sys.stderr)
        return 2
    if "verify" not in target_db.lower() and "scratch" not in target_db.lower():
        print(
            "FAIL: scratch database name must contain 'verify' or 'scratch' as an additional safety guard.",
            file=sys.stderr,
        )
        return 2

    pg_dump = shutil.which("pg_dump")
    pg_restore = shutil.which("pg_restore")
    if not pg_dump or not pg_restore:
        print("FAIL: pg_dump and pg_restore must be installed.", file=sys.stderr)
        return 2

    dump_path = None
    target_conn = None
    try:
        with tempfile.NamedTemporaryFile(prefix="zendoc-backup-", suffix=".dump", delete=False) as handle:
            dump_path = Path(handle.name)

        subprocess.run(
            [pg_dump, "--format=custom", "--no-owner", "--no-acl", "--file", str(dump_path)],
            env=_pg_env(source_url),
            check=True,
        )
        if not dump_path.exists() or dump_path.stat().st_size <= 0:
            raise RuntimeError("pg_dump produced an empty backup file.")

        target_conn = psycopg.connect(target_url, autocommit=False)
        _reset_scratch(target_conn)

        subprocess.run(
            [pg_restore, "--no-owner", "--no-acl", "--exit-on-error", "--dbname", target_db, str(dump_path)],
            env=_pg_env(target_url),
            check=True,
        )

        with psycopg.connect(source_url) as source_conn:
            source_counts = {table: _table_count(source_conn, table) for table in CORE_TABLES}
        with psycopg.connect(target_url) as restored_conn:
            restored_counts = {table: _table_count(restored_conn, table) for table in CORE_TABLES}
            restored_conn.execute("SELECT 1").fetchone()

        if source_counts != restored_counts:
            raise RuntimeError(
                f"Restored core-table counts do not match source: source={source_counts}, restored={restored_counts}"
            )

        print("PASS: PostgreSQL pg_dump -> scratch pg_restore -> core count verification succeeded.")
        print("Verified table counts:", source_counts)
        print(
            "This proves one backup/restore cycle. Also verify your hosting provider's scheduled backup/PITR "
            "retention before setting ZENDOC_BACKUP_VERIFIED=true."
        )
        return 0
    except Exception as exc:
        print(f"FAIL: backup/restore verification failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if target_conn is not None:
            try:
                if not keep_restore:
                    _reset_scratch(target_conn)
            finally:
                target_conn.close()
        if dump_path is not None:
            dump_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
