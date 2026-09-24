#!/usr/bin/env python3
"""Restore a verified ZENDOC PostgreSQL archive into a deliberate target.

The target URL is read from an environment variable and is never placed in a
process argument. Existing target tables are preserved by default. A reset is
allowed only with an explicit opt-in, which makes this suitable for the
Render-to-OCI cutover without silently destroying a populated database.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

import psycopg

from scripts.postgres_backup import connection_environment
from scripts.verify_postgres_backup import VerificationError, verify_backup


TARGET_ENV = "ZENDOC_POSTGRES_RESTORE_DATABASE_URL"
EXPECTED_DATABASE_ENV = "ZENDOC_POSTGRES_RESTORE_EXPECT_DATABASE"
ALLOW_RESET_ENV = "ZENDOC_POSTGRES_RESTORE_ALLOW_RESET"
SOURCE_GUARD_ENV = "ZENDOC_POSTGRES_RESTORE_SOURCE_DATABASE_URL"


class RestoreError(RuntimeError):
    pass


def database_identity(database_url: str) -> tuple[str, int, str]:
    parsed = urlsplit(str(database_url or "").strip())
    if parsed.scheme not in {"postgresql", "postgres"}:
        raise RestoreError("Restore target must use postgresql:// or postgres://.")
    if not parsed.hostname:
        raise RestoreError("Restore target is missing a PostgreSQL host.")
    database = unquote(parsed.path.lstrip("/"))
    if not database:
        raise RestoreError("Restore target is missing a PostgreSQL database name.")
    return parsed.hostname.lower(), parsed.port or 5432, database


def _child_environment(database_url: str) -> dict[str, str]:
    env = {
        key: value
        for key in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "TEMP", "TMP")
        if (value := os.environ.get(key))
    }
    env.update(connection_environment(database_url))
    return env


def _public_tables(conn) -> list[str]:
    rows = conn.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema='public' AND table_type='BASE TABLE'
        ORDER BY table_name
        """
    ).fetchall()
    tables = []
    for row in rows:
        try:
            tables.append(str(row["table_name"]))
        except (TypeError, KeyError):
            tables.append(str(row[0]))
    return tables


def _reset_public_schema(conn) -> None:
    conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
    conn.execute("CREATE SCHEMA public")
    conn.commit()


def restore_backup(
    archive: Path,
    target_url: str,
    *,
    expected_database: str,
    allow_reset: bool = False,
    source_guard_url: str = "",
    pg_restore: str = "pg_restore",
) -> dict:
    archive = archive.expanduser().resolve()
    if not expected_database.strip():
        raise RestoreError(
            f"{EXPECTED_DATABASE_ENV} is required as a deliberate target-name guard."
        )

    target_identity = database_identity(target_url)
    target_database = target_identity[2]
    if target_database != expected_database.strip():
        raise RestoreError(
            f"Restore target database {target_database!r} does not match "
            f"{EXPECTED_DATABASE_ENV}={expected_database.strip()!r}."
        )

    if source_guard_url:
        if database_identity(source_guard_url) == target_identity:
            raise RestoreError("Source guard and restore target resolve to the same database.")

    try:
        archive_verification = verify_backup(archive, pg_restore=pg_restore)
    except VerificationError as error:
        raise RestoreError(f"Backup archive verification failed: {error}") from error

    executable = shutil.which(pg_restore)
    if not executable:
        raise RestoreError(f"{pg_restore!r} was not found on PATH.")

    reset_performed = False
    with psycopg.connect(target_url, autocommit=False) as target_conn:
        tables_before = _public_tables(target_conn)
        if tables_before and not allow_reset:
            raise RestoreError(
                "Restore target already contains application tables. "
                f"Refusing to overwrite {len(tables_before)} table(s). "
                f"Use {ALLOW_RESET_ENV}=true only for a target you intend to replace."
            )
        if tables_before:
            _reset_public_schema(target_conn)
            reset_performed = True

    command = [
        executable,
        "--no-owner",
        "--no-acl",
        "--exit-on-error",
        "--single-transaction",
        "--dbname",
        target_database,
        str(archive),
    ]
    result = subprocess.run(
        command,
        env=_child_environment(target_url),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or "pg_restore failed").strip().splitlines()[-1]
        raise RestoreError(
            "pg_restore failed. The source archive was not modified; "
            f"the target may require operator recovery. Detail: {detail[:500]}"
        )

    with psycopg.connect(target_url, autocommit=False) as restored_conn:
        restored_conn.execute("SELECT 1").fetchone()
        tables_after = _public_tables(restored_conn)

    if not tables_after:
        raise RestoreError("pg_restore returned success but no public application tables exist.")

    return {
        "status": "restore_completed",
        "archive": archive.name,
        "target_database": target_database,
        "target_tables_before": len(tables_before),
        "target_tables_after": len(tables_after),
        "reset_performed": reset_performed,
        "catalog_entries": archive_verification.get("catalog_entries"),
        "next_step": (
            "Start the reviewed ZENDOC application against this database, let idempotent "
            "migrations run, then verify readiness and representative record parity before cutover."
        ),
    }


def _enabled(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive")
    parser.add_argument("--pg-restore", default="pg_restore")
    args = parser.parse_args()

    target_url = str(os.environ.get(TARGET_ENV) or "").strip()
    expected_database = str(os.environ.get(EXPECTED_DATABASE_ENV) or "").strip()
    source_guard_url = str(os.environ.get(SOURCE_GUARD_ENV) or "").strip()

    if not target_url:
        print(f"Restore FAILED: {TARGET_ENV} is not configured.", file=sys.stderr)
        return 2
    if not expected_database:
        print(f"Restore FAILED: {EXPECTED_DATABASE_ENV} is not configured.", file=sys.stderr)
        return 2

    try:
        result = restore_backup(
            Path(args.archive),
            target_url,
            expected_database=expected_database,
            allow_reset=_enabled(os.environ.get(ALLOW_RESET_ENV, "")),
            source_guard_url=source_guard_url,
            pg_restore=args.pg_restore,
        )
    except RestoreError as error:
        print(f"Restore FAILED: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    print(
        "Restore completed, but cutover is NOT verified yet. Keep the Render source "
        "until OCI readiness, persistence, and representative data checks pass."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
